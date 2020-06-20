import logging

import tornado.gen

from common.base_handler import TMBaseReqHandler
from common.msg_field import *
from common.receipt_ship_state import ReturnEpcState


class ReturnTrackHandlerTM(TMBaseReqHandler):
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
        return
