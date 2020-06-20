# -*- coding: utf-8 -*-

from datetime import datetime

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from tornado.gen import coroutine

from common.base_handler import WMSBaseReqHandler
from common.msg_field import *
from common.receipt_ship_state import *
from models.models import *

__author__ = 'Ennis'


class OrderSyncHandlerTM(WMSBaseReqHandler):
    """
    wms发货订单同步接口，包含发货订单和工单清点订单两种

    """
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.sync_handler = {
            OrderSyncStrType.SHIP_ORDER.value: self.handle_ship_order_sync,
            OrderSyncStrType.COUNT_ORDER.value: self.handle_count_order_sync,
        }

    @coroutine
    def post(self):
        try:
            msg_info = self.msg_info

            if msg_info[URL_TYPE] not in self.sync_handler:
                self.write({
                    MSG_BODY: response_desc[ResponseStatus.WRONG_ORDER_SYNC_TYPE],
                    MSG_SUCCESS: False,
                    MSG_TS: ""
                })
                self.finish()
                return

            yield self.sync_handler[msg_info[URL_TYPE]](msg_info)

        except Exception as err_info:
            self.error("handle order sync failed: %s", err_info)
            self.write({MSG_BODY: response_desc[ResponseStatus.SYSTEM_ERROR], MSG_SUCCESS: False, MSG_TS: ""})
            self.finish()

    @coroutine
    def handle_ship_order_sync(self, msg_info):
        """
        处理发货订单同步
        
        :param msg_info: 
        :return: 
        """
        try:
            self.info("handle ship order sync")

            success, reason = self.add_order_info_if_not_existed(msg_info)
            if not success:
                self.write({MSG_BODY: response_desc[reason], MSG_SUCCESS: False, MSG_TS: ""})
                self.finish()
                return

            self.write({MSG_BODY: response_desc[ResponseStatus.SUCCESS], MSG_SUCCESS: True, MSG_TS: ""})
            self.finish()

        except Exception as err_info:
            self.error("handle ship order sync failed: %s", err_info)
            self.write({MSG_BODY: response_desc[ResponseStatus.SYSTEM_ERROR], MSG_SUCCESS: False, MSG_TS: ""})
            self.finish()

    @coroutine
    def handle_count_order_sync(self, msg_info):
        """
        处理工单清单同步
        
        :param msg_info: 
        :return: 
        """
        try:
            self.info("handle count order sync")

            success, reason = self.add_order_info_if_not_existed(msg_info)
            if not success:
                self.write({MSG_BODY: response_desc[reason], MSG_SUCCESS: False, MSG_TS: ""})
                self.finish()
                return

            self.write({MSG_BODY: response_desc[ResponseStatus.SUCCESS], MSG_SUCCESS: True, MSG_TS: ""})
            self.finish()

        except Exception as err_info:
            self.error("handle count order sync failed: %s", err_info)
            self.write({MSG_BODY: response_desc[ResponseStatus.SYSTEM_ERROR], MSG_SUCCESS: False, MSG_TS: ""})
            self.finish()

    def add_order_info_if_not_existed(self, msg_info):
        """
        插入发货订单数据
        
        :param msg_info: 
        :return: 
        """
        try:
            result = self.db.query(TShipOrder).filter(TShipOrder.ship_id == msg_info[URL_ORDER_CODE]).all()
            if len(result) >= 1:
                self.error("the ship order[%s] have existed", msg_info[URL_ORDER_CODE])
                return False, ResponseStatus.ORDER_EXISTED

            ship_order = TShipOrder()
            ship_order.ship_id = msg_info[URL_ORDER_CODE]
            ship_order.status = ShipOrderState.INIT_STATE.value
            ship_order.ship_quantity = 0
            ship_order.client_id = ""
            ship_order.type = int(msg_info[URL_TYPE]) - 1
            ship_order.ship_date = datetime.now()

            for item in msg_info[URL_ITEMS]:
                sku_info = self.query_sku_info(item[URL_SKU])
                if sku_info is None:
                    return False, ResponseStatus.INVALID_SKU

                order_detail_info = TShipOrderDetail()
                order_detail_info.ship_id = msg_info[URL_ORDER_CODE]
                order_detail_info.sku = item[URL_SKU]
                order_detail_info.size = sku_info.size
                order_detail_info.color = sku_info.color
                order_detail_info.ship_quantity = int(item[URL_SQTY])
                self.db.add(order_detail_info)

                ship_order.ship_quantity += order_detail_info.ship_quantity

            self.db.add(ship_order)

            return True, None

        except Exception as err_info:
            self.error("add order info if not existed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR

    def query_sku_info(self, sku):
        try:
            result = self.db.query(TSkuInfo).filter(TSkuInfo.sku == sku).one()
            return result

        except NoResultFound:
            self.error("have no sku info: %s", sku)
            return None

        except MultipleResultsFound:
            self.error("sku[%s] have multi init record", sku)
            return None

        except Exception as err_info:
            self.error("query sku info failed: %s", err_info)
            return None

    def fields_valid_check(self):
        try:
            if URL_ORDER_CODE not in self.msg_info:
                return False, ResponseStatus.LACK_ORDER_CODE_FIELD

            if URL_TYPE not in self.msg_info:
                return False, ResponseStatus.LACK_ORDER_SYNC_TYPE

            if URL_ITEMS not in self.msg_info:
                return False, ResponseStatus.LACK_ITEMS_FIELD

            for item in self.msg_info[URL_ITEMS]:
                if URL_SKU not in item:
                    return False, ResponseStatus.LACK_SKU_FIELD

                if URL_SQTY not in item:
                    return False, ResponseStatus.LACK_SQTY_FIELD

            return True, None

        except Exception as err_info:
            self.error("check content validation failed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR
