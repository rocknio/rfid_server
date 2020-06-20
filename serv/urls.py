# -*- coding: utf-8 -*-

from serv.tm.deliver_confirm_handler import DeliverConfirmHandlerTM
from serv.tm.epc_sync_handler import EpcSyncHandlerTM
from serv.wms.order_sync_handler import OrderSyncHandlerTM
from serv.tm.task_query_handler import TaskQueryHandlerTM
from serv.tm.batch_ship_notify_handler import BatchShipNotifyHandlerTM
from serv.tm.list_count_notify_handler import ListCountNotifyHandlerTM
from serv.tm.return_track_handler import ReturnTrackHandlerTM

__author__ = 'Ennis'

app_handlers = [
    (r'/deliverconfirm', DeliverConfirmHandlerTM),
    (r'/epcsync', EpcSyncHandlerTM),  # 对接隧道机接口
    (r'/ordersync', OrderSyncHandlerTM),
    (r'/taskquery', TaskQueryHandlerTM),
    (r'/sendrequest', BatchShipNotifyHandlerTM),
    (r'/listcountrequest', ListCountNotifyHandlerTM),
    (r'/returnconfirm', ReturnTrackHandlerTM),  # 对接手持机接口

]


# 2019-04-24 增加returnconfirm文件夹 MK
