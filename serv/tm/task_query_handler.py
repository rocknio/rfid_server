# !/usr/bin/python3
# -*- coding: utf-8 -*-

from tornado.gen import coroutine

from common.base_handler import TMBaseReqHandler
from common.msg_field import *
from models.models import *
from common.receipt_ship_state import ShipOrderState

__author__ = "jxh"


class TaskQueryHandlerTM(TMBaseReqHandler):
    @coroutine
    def post(self):
        """
        查询任务清单
        
        :return: 
        """
        try:
            order_infos = self.db.query(TShipOrder).filter(TShipOrder.status != ShipOrderState.DONE_STATE.value).all()

            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TASKS: []
            }

            for order_info in order_infos:
                task_info = {
                    "no": order_info.ship_id,
                    MSG_ORDER_TYPE: wms_order_type[order_info.type],
                    MSG_OPERATOR: "",
                    MSG_PARAM: "",
                    MSG_TASK_DESC: "",
                    MSG_TASK_CREATE_TIME: ('' if order_info.ship_date is None
                                           else order_info.ship_date.strftime("%Y-%m-%d %H:%M:%S"))
                }

                response_msg[MSG_TASKS].append(task_info)

            self.write(response_msg)
            self.finish()

        except Exception as err_info:
            self.error("handle task query request failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    def fields_valid_check(self):
        try:
            if MSG_DEVICE_ID not in self.msg_info:
                return False, ResponseStatus.LACK_DEVICE_ID_FIELD

            return True, None

        except Exception as err_info:
            self.error("epc sync handler check fields valid failed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR
