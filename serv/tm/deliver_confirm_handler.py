# !/usr/bin/python3
# -*- coding: utf-8 -*-

import logging

import tornado.gen

from common.base_handler import TMBaseReqHandler
from common.msg_field import *
from models.models import *
from common.receipt_ship_state import *

__author__ = "Ennis"


class DeliverConfirmHandlerTM(TMBaseReqHandler):
    @tornado.gen.coroutine
    def post(self):
        """
        :return:
        """
        try:
            device_id = self.msg_info[MSG_DEVICE_ID]
            if device_id in self.ship_count_transaction:
                self.confirm_ship_count_transaction()
            else:
                self.confirm_receipt_transaction()

        except Exception as err_info:
            logging.error("DeliverConfirmHandler post catch exception =%s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def confirm_ship_count_transaction(self):
        try:
            self.info("handle ship count confirm")
            device_id = self.msg_info[MSG_DEVICE_ID]
            ship_id = self.ship_count_transaction[device_id][0]
            self.un_register_ship_count_transaction()

            success = self.move_ship_detail_to_his(ship_id)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.update_ship_order_state(ship_id, ShipOrderState.DONE_STATE)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            self.write({MSG_STATUS: ResponseStatus.SUCCESS.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS]})
            self.finish()

        except Exception as err_info:
            self.error("confirm ship count transaction faile: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def confirm_receipt_transaction(self):
        try:
            self.info("handle receipt confirm")
            data_info = self.msg_info

            transid = data_info[MSG_TRANS_ID]

            result = self.db.query(TReceiptScanLog).filter(TReceiptScanLog.trans_id == transid)
            if result.count() == 0:
                self.error("no this transid[%s] in dict executing_transaction" % transid)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.TRANSACTION_NOT_EXISTED.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.TRANSACTION_NOT_EXISTED]})
                self.finish()
                return
            if result.count() > 1:
                self.error("transid[%s] need unpack, cannot confirm" % transid)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SKU_NOT_SAME.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SKU_NOT_SAME]})
                self.finish()
                return

            transaction_info = result.one()
            if transaction_info.status >= ReceiptScanState.TO_CHECK.value:
                self.error("this transaction[%s] have confirmed" % transid)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.TRANSACTION_CONFIRMED.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.TRANSACTION_CONFIRMED]})
                self.finish()
                return

            # 搬迁历史数据
            success = self.pre_receipt(transid)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.update_receipt_scan_state(transid, ReceiptScanState.TO_CHECK)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.update_pre_receipt_num(transaction_info.case_id, transaction_info.sku)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.update_receipt_sku_state(transaction_info.case_id, transaction_info.sku,
                                                    ReceiptSkuState.TO_CHECK)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            self.write({MSG_STATUS: ResponseStatus.SUCCESS.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS]})
            self.finish()

        except Exception as err_info:
            logging.error("confirm receipt transaction failed:", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()
            return

    def pre_receipt(self, trans_id):
        """
        更新状态

        :return:
        """
        try:
            self.info("pre_receipt by trans_id = %s", trans_id)
            # handle the detail
            result = self.db.query(TReceiptScanDetail.epc).filter(TReceiptScanDetail.trans_id == trans_id).all()
            epcs = []
            for one_record in result:
                epcs.append(one_record.epc)

            self.db.query(TReceiptDetail).filter(TReceiptDetail.epc.in_(epcs)).update({
                TReceiptDetail.status: ReceiptEpcState.PRE_RECEIPT.value
            }, synchronize_session=False)

            return True

        except Exception as ex:
            self.error("pre_receipt catch exception ex=%s", ex)
            return False

    def move_ship_detail_to_his(self, order_id):
        """
        move 收货表信息到收货历史表
        
        : param order_id:
        :return:
        """
        try:
            self.info("move ship detail info to history table by order_id:", order_id)
            # handle the detail
            detail_info = self.db.query(TShipDetail).filter(TShipDetail.ship_id == order_id)
            for one_detail in detail_info.all():
                detail_history = TShipDetailHistory()
                detail_history.ship_id = one_detail.ship_id
                detail_history.sku = one_detail.sku
                detail_history.epc = one_detail.epc
                self.db.add(detail_history)
            detail_info.delete()

            return True

        except Exception as ex:
            self.error("move ship detail info to history failed: %s", ex)
            return False

    def fields_valid_check(self):
        try:
            if MSG_TRANS_ID not in self.msg_info:
                return False, ResponseStatus.Lack

            if MSG_DEVICE_ID not in self.msg_info:
                return False, ResponseStatus.LACK_DEVICE_ID_FIELD

            if MSG_CONFIRM_TYPE not in self.msg_info:
                return False, ResponseStatus.LACK_CONFIRM_TYPE

            return True, None

        except Exception as err_info:
            self.error("epc sync handler check fields valid failed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR
