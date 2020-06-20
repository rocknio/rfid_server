# !/usr/bin/python3
# -*- coding: utf-8 -*-

from tornado.gen import coroutine

from common.base_handler import TMBaseReqHandler
from common.msg_field import *
from models.models import *
from common.receipt_ship_state import *

__author__ = "jxh"


class ListCountNotifyHandlerTM(TMBaseReqHandler):
    @coroutine
    def post(self):
        """
        处理开始批量发货请求

        :return: 
        """
        try:
            msg_info = self.msg_info

            if msg_info[MSG_DEVICE_ID] in self.ship_count_transaction:
                self.un_register_ship_count_transaction()

            query = self.db.query(TShipOrder).filter(TShipOrder.ship_id == self.msg_info[MSG_TASK_NO],
                                                     TShipOrder.type == OrderSyncDBType.COUNT_ORDER.value)

            if query.count() == 0 or query.count() > 1:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.INVALID_TASKNO.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.INVALID_TASKNO]})
                self.finish()
                return

            success = self.update_ship_order_state(self.msg_info[MSG_TASK_NO], ShipOrderState.SHIPPING_STATE)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            order_infos = self.db.query(TShipOrderDetail).\
                filter(TShipOrderDetail.ship_id == self.msg_info[MSG_TASK_NO]).all()

            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_SKUS: []
            }

            for order_info in order_infos:
                sku_info = {
                    MSG_SKU_NO: order_info.sku,
                    MSG_QUANTITY: order_info.ship_quantity
                }

                response_msg[MSG_SKUS].append(sku_info)

            self.write(response_msg)
            self.finish()

            self.register_ship_count_transaction(msg_info[MSG_TASK_NO], EpcSyncType.LISTCOUNT.value)

        except Exception as err_info:
            self.error("handle list count start request failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def fields_valid_check(self):
        try:
            if MSG_DEVICE_ID not in self.msg_info:
                return False, ResponseStatus.LACK_DEVICE_ID_FIELD

            if MSG_TASK_NO not in self.msg_info:
                return False, ResponseStatus.LACK_TASK_NO_FIELD

            return True, None

        except Exception as err_info:
            self.error("epc sync handler check fields valid failed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR
