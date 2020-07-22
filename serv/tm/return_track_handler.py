import logging
import json
import tornado.gen

from common.base_handler import TMBaseReqHandler
from common.msg_field import *
from common.receipt_ship_state import ReturnEpcState
from models.models import *
from common.settings import *
from datetime import datetime
import hashlib
from urllib.parse import urlencode
from common.http_request import http_client_request


class ReturnTrackHandlerTM(TMBaseReqHandler):
    # TODO only for test
    @tornado.gen.coroutine
    def get(self):
        self.sync_returned_info_to_scm('trans_id', ['43391810167401FF02052111', '43391810167401FF02052113',
                                                    '43391810167401FF02052115',
                                                    '43391840002406FF01939477', '43391840002406FF01939509'])
        self.write("ok")
        self.finish()

    @tornado.gen.coroutine
    def post(self):
        """
        2019-04-24 货发运操作 MK
        :return:
        """
        try:
            self.confirm_return_transaction()
        except Exception as err_info:
            logging.error("ReturnTrackHandlerTM post catch exception =%s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def confirm_return_transaction(self):
        self.info("handle return confirm")
        data_info = self.msg_info

        # 取运单号 和 EPC数据
        trackno = data_info[TRACK_NO]
        device_id = data_info[MSG_DEVICE_ID]
        trans_id = data_info[MSG_TRANS_ID]
        epc_return = self.return_track_transaction.pop(device_id + trans_id, None)

        # 判断当前transid 是否与 内存transid 一致,一致则更新，不一致则并提示错误
        if epc_return is None:
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.TRANSACTION_NOT_EXISTED.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.TRANSACTION_NOT_EXISTED]})
            self.finish()
            return

        lst_count = []
        for epc in epc_return:
            success = self.udpate_return_trackno_status(epc, ReturnEpcState.RETURN_AL, trackno)
            # 失败时将失败的标签写入list
            if not success:
                lst_count.append(epc)
        # 成功
        if len(lst_count) == 0:
            self.write({MSG_STATUS: ResponseStatus.SUCCESS.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS]})
            self.finish()
        # 失败
        elif len(lst_count) > 0:
            strfail = " ".join(lst_count)

            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR] + ECP_RET_FAIL.replace("X", strfail)
                        })
            self.finish()

        # 增加同步scm接口
        self.sync_returned_info_to_scm(trans_id, epc_return)
        return

    @tornado.gen.coroutine
    def sync_returned_info_to_scm(self, trans_id, epc_return):
        try:
            logging.info("sync returned info to scm, epcs = {}".format(epc_return))
            return_infos = self.db.query(TReturnInfo.sku, TReturnInfo.epc).filter(TReturnInfo.epc.in_(epc_return)).all()

            return_info_dict = {}
            for one_return_info in return_infos:
                return_info_dict[one_return_info[0]] = []

            for one_return_info in return_infos:
                return_info_dict[one_return_info[0]].append(one_return_info[1])
            logging.info("select return info = {}".format(return_info_dict))

            sync_msg = {
                'transid': trans_id,
                'operate_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'items': []
            }

            for k, v in return_info_dict.items():
                try:
                    purchase_order_code = self.db.query(TEpcDetail.order_id).filter(TEpcDetail.epc == v[0]).one()
                except Exception as err_info:
                    logging.warning("can't find purchase_order_code from t_epc_detail, epc = {}".format(err_info))
                    purchase_order_code = [""]

                tmp = {'item_code': k, 'actual_qty': len(v), 'purchase_order_code': purchase_order_code[0]}
                sync_msg['items'].append(tmp)

            param = {
                'method': 'stockout.confirm',
                'sign': hashlib.md5((SCM_SIGN_STRING + sync_msg['operate_time']).encode('utf8')).hexdigest(),
                'timestamp': sync_msg['operate_time'],
            }

            url = SCM_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, sync_msg, self.trans_identity)
            if success:
                logging.info("sync return info to scm SUCCESS! url = {}, content = {}".format(url, sync_msg))
            else:
                logging.error("sync return info to scm FAILED! url = {}, content = {}, resp = {}".format(url, sync_msg, body))

            scm_sync_log = TScmSyncLog()
            scm_sync_log.transid = trans_id
            scm_sync_log.operate_time = sync_msg['operate_time']
            scm_sync_log.type = 'return'
            if success:
                scm_sync_log.status = 1
            else:
                scm_sync_log.status = 0
            scm_sync_log.req_body = json.dumps(sync_msg)
            scm_sync_log.res_body = "" if body is None else body

            self.db.add(scm_sync_log)
            self.db.commit()
        except Exception as err_info:
            logging.error("sync returned info to scm failed! err = {}".format(err_info))
