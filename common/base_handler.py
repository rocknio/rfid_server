# -*- coding: utf-8 -*-

import base64
import json
import uuid
from collections import defaultdict
from datetime import datetime
from os.path import exists
from urllib.parse import urlencode

# import collections
from sqlalchemy import func
from tornado.gen import coroutine
from tornado.web import RequestHandler

from common.dbutils import db_session
from common.http_request import http_client_request
from common.msg_field import *
from common.receipt_ship_state import *
from common.settings import *
from models.models import *
from abc import ABCMeta, abstractclassmethod
import hashlib

__author__ = 'Ennis'


class TMBaseReqHandler(RequestHandler):
    ship_count_transaction = {}
    return_track_transaction = {}  # 保存隧道机上传的标签，以供后续退货确认使用

    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.statistics_info = None
        self.db = db_session
        self.msg_info = None
        self.request_transid = None
        self.trans_identity = {}

    def data_received(self, chunk):
        pass

    def fields_valid_check(self):
        return True, None

    @coroutine
    def prepare(self):
        """
        解析报文中是否有transid,字段，如果没有直接返回

        :return:
        """
        try:
            # 生成当次请求的事务号
            self.request_transid = str(uuid.uuid1()).replace("-", "")
            self.trans_identity["request_transid"] = self.request_transid

            if self.request.method == 'GET':
                return True, None

            message = self.request.body.decode('utf-8')
            self.info("receive request: %s", message)
            if message != "":
                self.msg_info = json.loads(message)

            valid, reason = self.fields_valid_check()
            if not valid:
                self.set_status(500)
                self.write({MSG_STATUS: reason.value,
                            MSG_STATUS_TEXT: response_desc[reason]})
                self.finish()

        except Exception as err_info:
            logging.error("prepare failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def write(self, chunk):
        try:
            # 如果返回状态不是200，回滚数据库
            if self.get_status() != 200:
                self.db.rollback()
            else:
                self.db.commit()

            self.info("response data: %s", chunk)
            super().write(chunk)

        except Exception as err_info:
            logging.error("write response data back to client failed: %s", err_info)
            self.set_status(500)
            self.db.rollback()
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})

    def debug(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.debug(msg, *args, extra=self.trans_identity, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.info(msg, *args, extra=self.trans_identity, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.warning(msg, *args, extra=self.trans_identity, **kwargs)

    def error(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.error(msg, *args, extra=self.trans_identity, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.critical(msg, *args, extra=self.trans_identity, **kwargs)

    def log(self, lvl, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param lvl:
        :param args:
        :param kwargs:
        :return:
        """
        logging.log(lvl, msg, *args, extra=self.trans_identity, **kwargs)

    @classmethod
    def load_transaction_data(cls):
        try:
            if exists("ship_count.json"):
                with open("ship_count.json") as ship_count_file:
                    TMBaseReqHandler.ship_count_transaction = json.load(ship_count_file)

        except Exception as err_info:
            logging.error("load transaction data failed: $", err_info)

    def register_ship_count_transaction(self, order_id, scene_type):
        try:
            self.info("register transaction[%s] order_id[%s] type[%s]", self.msg_info[MSG_DEVICE_ID], order_id,
                      scene_type)
            with open("ship_count.json", "w") as receipt_file:
                TMBaseReqHandler.ship_count_transaction[self.msg_info[MSG_DEVICE_ID]] = [order_id, scene_type]
                json.dump(TMBaseReqHandler.ship_count_transaction, receipt_file)

        except Exception as err_info:
            self.error("register ship count transaction failed: %s", err_info)

    def un_register_ship_count_transaction(self):
        try:
            self.info("un register device[%s] transaction", self.msg_info[MSG_DEVICE_ID])
            with open("ship_count.json", "w") as receipt_file:
                del TMBaseReqHandler.ship_count_transaction[self.msg_info[MSG_DEVICE_ID]]
                json.dump(TMBaseReqHandler.ship_count_transaction, receipt_file)

        except Exception as err_info:
            self.error("un register ship count  transaction failed: %s", err_info)

    def query_receipt_case_sku_info_by_box(self, box_id):
        """
        通过箱号查询sku的相关信息

        :param box_id:
        :return:
        """
        try:
            result = self.db.query(TReceiptBatchCaseSkuStatistic). \
                filter(TReceiptBatchCaseSkuStatistic.case_id == box_id).all()

            return result

        except Exception as err_info:
            self.error("query sku infos by box failed: %s", err_info)
            return None

    def query_receipt_epc_detail_info_by_box(self, trans_id):
        try:
            result = self.db.query(TReceiptScanDetail.epc, TReceiptScanDetail.sku, TEpcDetail.order_id).\
                join(TEpcDetail, TReceiptScanDetail.epc == TEpcDetail.epc).\
                filter(TReceiptScanDetail.trans_id == trans_id).all()

            return result

        except Exception as err_info:
            self.error("query receipt epc detail info by box failed: %s", err_info)
            return None

    def query_receipt_order_info_by_box(self, box_id):
        """
        通过箱号查询订单信息

        :param box_id:
        :return:
        """
        try:
            result = self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id,
                TReceiptBatchCase.status != ReceiptCaseState.CANCEL_STATE.value
            ).one()
            return result

        except Exception as err_info:
            self.error("query order info by box failed: %s", err_info)
            return None

    def sku_ship_quantity_in_box(self, box_id, sku):
        """
        查找箱标里面的sku相关信息

        :param box_id:
        :param sku:
        :return:
        """
        try:
            result = self.db.query(TReceiptBatchCaseSkuStatistic.ship_quantity).filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.sku == sku
            )

            if result.count() == 0:
                receipt_info = TReceiptBatchCaseSkuStatistic()
                receipt_info.case_id = box_id
                receipt_info.sku = sku
                receipt_info.ship_quantity = 0
                receipt_info.status = 0
                receipt_info.received_date = datetime.now()
                self.db.add(receipt_info)
                return True, 0
            elif result.count() > 1:
                return False, 0

            return True, result.one().ship_quantity

        except Exception as err_info:
            self.error("query box sku info failed: %s", err_info)
            return False, 0

    def sku_pre_receipt_quantity_in_box(self, box_id, sku):
        try:
            result = self.db.query(TReceiptBatchCaseSkuStatistic.pre_receipt_quantity).filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.sku == sku
            ).one()

            return True, result.pre_receipt_quantity

        except Exception as err_info:
            self.error("query pre receipt info failed: %s", err_info)
            return False, 0

    @coroutine
    def sync_receipt_msg_to_wms(self, box_id, trans_id):
        """
        同步信息到wms收货接口

        :param box_id:
        :param trans_id:
        :return:
        """
        try:
            sku_info = self.statistics_order_info(trans_id)
            if sku_info is None:
                return

            sync_msg = []
            for sku in sku_info:
                epc_info = sku_info[sku]

                order_sync_msg = {

                    URL_ORDER_CODE: None,
                    URL_SKU: sku,
                    URL_BOX_ID: box_id,
                    URL_QTY: len(epc_info),
                    URL_ITEMS: []
                }
                items = []
                for epc in epc_info:
                    items.append({URL_EPC: epc})
                    if order_sync_msg[URL_ORDER_CODE] is None:
                        success, order_id = self.query_order_id_by_epc(epc)
                        if success:
                            order_id = order_id + "-" + box_id[2:] + "-" + datetime.now().strftime("%m%d%H%M%S")
                            order_sync_msg[URL_ORDER_CODE] = order_id
                order_sync_msg[URL_ITEMS] = items
                sync_msg.append(order_sync_msg)

            self.info("sync to wms order info:%s", json.dumps(sync_msg))
            content = base64.b64encode(json.dumps(sync_msg).encode()).decode()

            param = {
                URL_APPKEY_PARAM: APP_KEY,
                URL_SERVICE_PARAM: RECEIPT_INTERFACE,
                URL_SECRET_PARAM: "app_wms",
                URL_FORMAT_PARAM: "JSON",
                URL_CONTENT_PARAM: content,
                "encrypt": 1
            }
            url = WMS_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, {}, self.trans_identity)

            sync_log = TWmsSyncLog()
            sync_log.type = EpcSyncType.RECEIPT.value
            sync_log.optime = datetime.now()
            sync_log.case_id = box_id
            sync_log.status = 0
            sync_log.unit_id = box_id
            sync_log.trans_id = trans_id
            if success:
                sync_log.status = 1
                self.update_receipt_scan_state(trans_id, ReceiptScanState.SYNC_SUCCESS)
            else:
                sync_log.status = 0
                self.update_receipt_scan_state(trans_id, ReceiptScanState.SYNC_FAILED)

            sync_log.req_body = json.dumps(param)
            sync_log.res_body = "" if body is None else body

            self.db.add(sync_log)
            self.db.commit()

            # 20200621 增加scm同步
            self.sync_receipt_msg_to_scm(trans_id, sync_msg)
        except Exception as err_info:
            self.error("sync message to wms failed: %s", err_info)
            self.db.rollback()
            return False

    @coroutine
    def sync_receipt_msg_to_scm(self, trans_id, wms_sync_msg):
        self.info("sync receipt to scm, tranid = {}, wms_sync_msg = {}".format(trans_id, wms_sync_msg))

        try:
            sync_msg = {
                'transid': trans_id,
                'entry_order_code': wms_sync_msg[0][URL_ORDER_CODE],
                'supplier_code': self.query_supplier_id_by_epc(wms_sync_msg[0][URL_ITEMS][0][URL_EPC]),
                'operate_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'items': []
            }

            for sku_info in wms_sync_msg:
                items = {
                    'item_code': sku_info[URL_SKU],
                    'actual_qty': sku_info['qty']
                }
                sync_msg['items'].append(items)

            param = {
                'method': 'entryorder.confirm',
                'sign': hashlib.md5((SCM_SIGN_STRING+sync_msg['operate_time']).encode('utf8')).hexdigest(),
                'timestamp': sync_msg['operate_time'],
            }

            url = SCM_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, sync_msg, self.trans_identity)
            if success:
                self.info("sync receipt to scm SUCCESS! url = {}, content = {}".format(url, sync_msg))
            else:
                self.error("sync receipt to scm FAILED! url = {}, content = {}, resp = {}".format(url, sync_msg, body))

            scm_sync_log = TScmSyncLog()
            scm_sync_log.trans_id = trans_id
            scm_sync_log.entry_order_code = sync_msg['entry_order_code']
            scm_sync_log.operate_time = sync_msg['operate_time']
            scm_sync_log.supplier_code = sync_msg['supplier_code']
            if success:
                scm_sync_log.status = 1
            else:
                scm_sync_log.status = 0
            scm_sync_log.req_body = json.dumps(sync_msg)
            scm_sync_log.res_body = "" if body is None else body

            self.db.commit()

        except Exception as err_info:
            self.error("sync msg to scm failed: %s", err_info)
            self.db.rollback()
            return

    @coroutine
    def sync_ship_msg_to_wms(self, statistics_info, trans_id=None):
        """
        同步信息到wms收货接口

        :param statistics_info:
        :param trans_id:
        :return:
        """
        try:
            device_id = self.msg_info[MSG_DEVICE_ID]
            ship_id = self.ship_count_transaction[device_id][0]

            sku_infos = statistics_info[REPORTED_EPC]
            for sku in statistics_info[UNREPORTED_EPC]:
                sku_infos.setdefault(sku, [])
                sku_infos[sku].extend(statistics_info[UNREPORTED_EPC][sku])

            sync_msg = []
            for sku in sku_infos:
                epc_info = sku_infos[sku]

                order_sync_msg = {
                    URL_ORDER_CODE: ship_id,
                    URL_SKU: sku,
                    URL_QTY: len(epc_info),
                    URL_ITEMS: []
                }
                items = []
                for epc in epc_info:
                    items.append({URL_EPC: epc})

                order_sync_msg[URL_ITEMS] = items

                sync_msg.append(order_sync_msg)

            content = base64.b64encode(json.dumps(sync_msg).encode()).decode()
            # secret = content + SESSION_KEY

            param = {
                URL_APPKEY_PARAM: APP_KEY,
                URL_SERVICE_PARAM: SHIP_COUNT_INTERFACE,
                URL_SECRET_PARAM: "app_wms",
                URL_FORMAT_PARAM: "JSON",
                URL_CONTENT_PARAM: content,
                "encrypt": 1
            }
            url = WMS_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, {}, self.trans_identity)

            sync_log = TWmsSyncLog()
            sync_log.optime = datetime.now()
            sync_log.unit_id = ship_id
            sync_log.type = "SEND"
            if trans_id is None:
                sync_log.trans_id = self.request_transid
            else:
                sync_log.trans_id = trans_id

            if success:
                sync_log.status = 1
            else:
                sync_log.status = 0

            sync_log.req_body = json.dumps(param)
            sync_log.res_body = "" if body is None else body

            self.db.add(sync_log)
            self.db.commit()

        except Exception as err_info:
            self.error("sync message to wms failed: %s", err_info)
            self.db.rollback()
            return False

    @coroutine
    def sync_list_count_msg_to_wms(self, statistics_info, trans_id=None):
        """
        同步信息到wms收货接口

        :param statistics_info:
        :param trans_id:
        :return:
        """
        try:
            device_id = self.msg_info[MSG_DEVICE_ID]
            ship_id = self.ship_count_transaction[device_id][0]

            sku_infos = statistics_info[SKU_INFO]
            sync_msg = []
            for sku in sku_infos:
                epc_info = sku_infos[sku]

                order_sync_msg = {
                    URL_ORDER_CODE: ship_id,
                    URL_SKU: sku,
                    URL_QTY: len(epc_info),
                    URL_ITEMS: []
                }
                items = []
                for epc in epc_info:
                    items.append({URL_EPC: epc})

                order_sync_msg[URL_ITEMS] = items

                sync_msg.append(order_sync_msg)

            content = base64.b64encode(json.dumps(sync_msg).encode()).decode()
            # secret = content + SESSION_KEY

            param = {
                URL_APPKEY_PARAM: APP_KEY,
                URL_SERVICE_PARAM: SHIP_COUNT_INTERFACE,
                URL_SECRET_PARAM: "app_wms",
                URL_FORMAT_PARAM: "JSON",
                URL_CONTENT_PARAM: content,
                "encrypt": 1
            }
            url = WMS_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, {}, self.trans_identity)

            sync_log = TWmsSyncLog()
            sync_log.optime = datetime.now()
            sync_log.unit_id = ship_id
            sync_log.type = "LIST"
            if trans_id is None:
                sync_log.trans_id = self.request_transid
            else:
                sync_log.trans_id = trans_id
            if success:
                sync_log.status = 1
            else:
                sync_log.status = 0

            sync_log.req_body = json.dumps(param)
            sync_log.res_body = "" if body is None else body

            self.db.add(sync_log)
            self.db.commit()

        except Exception as err_info:
            self.error("sync message to wms failed: %s", err_info)
            self.db.rollback()
            return False

    def statistics_order_info(self, trans_id):
        """
        根据箱标，统计这箱标签对应的订单号及其sku

        :param trans_id:
        :return: 订单中包含的sku和sku中包含的衣标
        """
        try:
            epc_infos = self.query_receipt_epc_detail_info_by_box(trans_id)
            if epc_infos is None:
                return None, None

            sku_info = defaultdict(set)
            for epc_info in epc_infos:
                sku_info[epc_info.sku].add(epc_info.epc)

            return sku_info

        except Exception as err_info:
            self.error("statistics order info failed: %s", err_info)
            return None, None

    def update_receipt_scan_state(self, trans_id, state):
        """
        更新扫描记录状态

        :param trans_id:
        :param state:
        :return:
        """
        try:
            self.info("update scan transaction[%s]  to state[%s]", trans_id, state)
            self.db.query(TReceiptScanLog).filter(
                TReceiptScanLog.trans_id == trans_id,
            ).update({
                TReceiptScanLog.status: state.value
            })

            return True

        except Exception as err_info:
            self.error("update receipt order state failed: %s", err_info)
            return False

    def update_receipt_sku_state(self, box_id, sku, state):
        """
        更新收货状态

        :param box_id:
        :param sku:
        :param state:
        :return:
        """
        try:
            self.info("update case[%s] sku[%s] to state[%s]", box_id, sku, state)
            self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.sku == sku
            ).update({
                TReceiptBatchCaseSkuStatistic.status: state.value
            })

            to_sync_num = self.db.query(TReceiptBatchCaseSkuStatistic). \
                filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.status == ReceiptSkuState.DONE_STATE.value
            ).count()

            ship_sku_num = self.db.query(TReceiptBatchCaseSkuStatistic). \
                filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
            ).count()

            # 这个箱子中所有sku已确认，直接更新这个箱子状态为已完成
            if to_sync_num == ship_sku_num:
                return self.update_receipt_order_state(box_id, ReceiptCaseState.DONE_STATE)

            to_confirm_num = self.db.query(TReceiptBatchCaseSkuStatistic). \
                filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.status >= ReceiptSkuState.TO_CONFIRM.value
            ).count()

            # 只有第一个sku开始收货时，才需要更新批次状态
            if to_confirm_num == 1:
                return self.update_receipt_order_state(box_id, ReceiptCaseState.RECEIPTING_STATE)

            return True

        except Exception as err_info:
            self.error("update receipt order state failed: %s", err_info)
            return False

    def update_pre_receipt_num(self, box_id, sku):
        """
        更新收货信息中对应sku的预收货数量

        :param box_id:
        :param sku:
        :return:
        """
        try:

            epc_count = self.db.query(TReceiptDetail).filter(
                TReceiptDetail.case_id == box_id,
                TReceiptDetail.sku == sku,
                TReceiptDetail.status == ReceiptEpcState.PRE_RECEIPT.value
            ).count()

            result = self.db.query(TReceiptBatchCaseSkuStatistic).filter(TReceiptBatchCaseSkuStatistic.sku == sku,
                                                                         TReceiptBatchCaseSkuStatistic.case_id == box_id).update(
               {
                   TReceiptBatchCaseSkuStatistic.pre_receipt_quantity: epc_count,
                   TReceiptBatchCaseSkuStatistic.received_date: datetime.now()
               }
            )

            print(result)
            return True

        except Exception as err_info:
            self.error("update pre receipt sku number failed: %s", err_info)
            return False

    def update_storage_num(self, box_id, sku):
        """
        更新收货信息中对应sku收货的实际数量

        :param box_id:
        :param sku:
        :return:
        """
        try:

            epc_count = self.db.query(TReceiptDetailHistory).filter(
                TReceiptDetailHistory.case_id == box_id,
                TReceiptDetailHistory.sku == sku).count()

            self.db.query(TReceiptBatchCaseSkuStatistic).filter(TReceiptBatchCaseSkuStatistic.sku == sku,
                                                                TReceiptBatchCaseSkuStatistic.case_id == box_id
                                                                ).update(
               {
                   TReceiptBatchCaseSkuStatistic.storage_quantity: epc_count,
                   TReceiptBatchCaseSkuStatistic.received_date: datetime.now()
               }
            )

            return True, epc_count

        except Exception as err_info:
            self.error("update storage sku number failed: %s", err_info)
            return False, 0

    def update_receipt_order_state(self, box_id, state):
        """
        更新收货状态

        :param box_id:
        :param state:
        :return:
        """
        try:
            self.info("update case[%s] to state[%s]", box_id, state)
            self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id,
            ).update({
                TReceiptBatchCase.status: state.value
            })

            batch_case_info = self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id,
                TReceiptBatchCase.status != ReceiptCaseState.CANCEL_STATE.value
            ).one()

            done_num = self.db.query(TReceiptBatchCase). \
                filter(
                TReceiptBatchCase.batch_id == batch_case_info.batch_id,
                TReceiptBatchCase.status == ReceiptCaseState.DONE_STATE.value
            ).count()

            ship_case_num = self.db.query(TReceiptBatchCase). \
                filter(
                TReceiptBatchCase.batch_id == batch_case_info.batch_id,
            ).count()

            # 该批次所有订单已确认，直接更新批次状态为已完成
            if done_num == ship_case_num:
                self.db.query(TReceiptInfo).filter(
                    TReceiptInfo.batch_id == batch_case_info.batch_id,
                ).update({
                    TReceiptInfo.status: ReceiptOrderState.DONE_STATE.value
                })
                return True

            receipting_num = self.db.query(TReceiptBatchCase). \
                filter(
                TReceiptBatchCase.batch_id == batch_case_info.batch_id,
                TReceiptBatchCase.status >= ReceiptCaseState.RECEIPTING_STATE.value
            ).count()

            # 只有第一箱开始收货时，才需要更新批次状态
            if receipting_num == 1:
                self.db.query(TReceiptInfo).filter(
                    TReceiptInfo.batch_id == batch_case_info.batch_id,
                ).update({
                    TReceiptInfo.status: ReceiptOrderState.RECEIPTING_STATE.value
                })

            return True

        except Exception as err_info:
            self.error("update receipt order state failed: %s", err_info)
            return False

    def update_ship_order_state(self, ship_id, state):
        """
        更新收货状态

        :param ship_id:
        :param state:
        :return:
        """
        try:
            self.info("update ship[%s] to state[%s]", ship_id, state)
            self.db.query(TShipOrder).filter(TShipOrder.ship_id == ship_id).update({
                TShipOrder.status: state.value
            })

            return True

        except Exception as err_info:
            self.error("update ship order state failed: %s", err_info)
            return False

    def udpate_return_trackno_status(self, epc, state, track):
        """
                更新退货状态

                :param epc:
                :param state:
                :param track:
                :return:
                """
        try:
            sb = [epc, state.value, track]
            self.info("update return param：%s", sb)
            self.db.query(TReturnInfo).filter(
                TReturnInfo.epc == epc,
                TReturnInfo.return_status == ReturnEpcState.PRE_RETURN.value
            ).update(
                {
                    TReturnInfo.return_status: state.value,
                    TReturnInfo.postnumber: track,
                    TReturnInfo.exit_time: datetime.now()
                }, synchronize_session=False)
            self.db.commit()
            return True

        except Exception as err_info:
            self.error("update return status failed: %s", err_info)
            return False

    def restart_transaction(self, box_id):
        """

        :param box_id:
        :return:
        """
        try:
            self.db.query(TReceiptDetail).filter(TReceiptDetail.case_id == box_id).delete()
            self.db.query(TReceiptBatchCaseSkuStatistic).\
                filter(TReceiptBatchCaseSkuStatistic.case_id == box_id).update({TReceiptBatchCaseSkuStatistic.received_quantity: 0})
            self.db.commit()

        except Exception as err_info:
            self.error("restart transaction failed: %s", err_info)
            return False

    def get_order_info_by_box_sku(self, box_id, sku):
        try:
            result = self.db.query(TEpcDetail.order_id, func.count("*").label('count')).join(
                TEpcDetail, TEpcDetail.epc == TReceiptDetailHistory.epc).filter(
                TReceiptDetailHistory.case_id == box_id,
                TReceiptDetailHistory.sku == sku
            ).group_by(TEpcDetail.order_id).all()

            return result

        except Exception as err_info:
            self.error("get order info by box sku failed: %s", err_info)

    def query_order_id_by_epc(self, epc):
        try:
            result = self.db.query(TEpcDetail.order_id).filter(TEpcDetail.epc == epc).one()
            return True, result.order_id

        except Exception as err_info:
            self.error("get order id exception: %s", err_info)
            return False, None

    def query_supplier_id_by_epc(self, epc):
        try:
            result = self.db.query(TEpcDetail.supplier_id).filter(TEpcDetail.epc == epc).one()
            return result.supplier_id

        except Exception as err_info:
            self.error("get supplier_id exception: %s", err_info)
            return ""


class WMSBaseReqHandler(RequestHandler, metaclass=ABCMeta):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.db = db_session
        self.msg_info = None
        self.request_transid = None
        self.trans_identity = {}

    def data_received(self, chunk):
        pass

    # @abstractclassmethod
    # def fields_valid_check(self):
    #     return True, None

    @coroutine
    def prepare(self):
        """
        解析报文中是否有transid,字段，如果没有直接返回

        :return:
        """
        try:
            # 生成当次请求的事务号
            self.request_transid = str(uuid.uuid1()).replace("-", "")
            self.trans_identity["request_transid"] = self.request_transid

            content = self.get_argument(URL_CONTENT_PARAM)
            # content = base64.b64decode(content.encode()).decode()
            self.info("order sync content: %s", content)
            self.msg_info = json.loads(content)

            # valid, reason = self.fields_valid_check()
            # if not valid:
            #     self.set_status(500)
            #     self.write({MSG_STATUS: reason.value,
            #                 MSG_STATUS_TEXT: response_desc[reason]})
            #     self.finish()

        except Exception as err_info:
            logging.error("prepare failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_BODY: response_desc[ResponseStatus.SYSTEM_ERROR], MSG_SUCCESS: False, MSG_TS: ""})
            self.finish()

    def write(self, chunk):
        try:
            # 如果返回状态不是200，回滚数据库
            if not chunk[MSG_SUCCESS]:
                self.db.rollback()
            else:
                self.db.commit()

            self.info("response data: %s", chunk)
            super().write(chunk)

        except Exception as err_info:
            logging.error("write response data back to client failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_BODY: response_desc[ResponseStatus.SYSTEM_ERROR], MSG_SUCCESS: False, MSG_TS: ""})

    def debug(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.debug(msg, *args, extra=self.trans_identity, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.info(msg, *args, extra=self.trans_identity, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.warning(msg, *args, extra=self.trans_identity, **kwargs)

    def error(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.error(msg, *args, extra=self.trans_identity, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param args:
        :param kwargs:
        :return:
        """
        logging.critical(msg, *args, extra=self.trans_identity, **kwargs)

    def log(self, lvl, msg, *args, **kwargs):
        """
        子类日志代理，传入额外参数trans_identity

        :param msg:
        :param lvl:
        :param args:
        :param kwargs:
        :return:
        """
        logging.log(lvl, msg, *args, extra=self.trans_identity, **kwargs)
