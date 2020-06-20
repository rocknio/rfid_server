# !/usr/bin/python3
# -*- coding: utf-8 -*-

from collections import Counter
from collections import defaultdict
from datetime import datetime
from itertools import chain

from sqlalchemy import func, inspect, and_
from sqlalchemy import distinct
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from tornado.gen import coroutine

from common.base_handler import TMBaseReqHandler
from common.epc_scene import EpcScene
from common.msg_field import *
from common.receipt_ship_state import *
from common.settings import RETURN_EXPIRED_DURATION
from models.models import *

__author__ = "jxh"


class EpcSyncHandlerTM(TMBaseReqHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.epc_scene_handler = {
            EpcScene.RECEIPT_SINGLE_SKU: self.handle_single_sku_scene,
            EpcScene.RECEIPT_MULTI_SKU: self.handle_multi_sku_scene,
            EpcScene.SIMPLE_COUNT: self.handle_simple_count_scene,
            EpcScene.SHIP: self.handle_ship_scene,
            EpcScene.LIST_COUNT: self.handle_list_count_scene,
            EpcScene.UNKNOWN_SCENE: self.handle_unknown_scene,
            EpcScene.RETURN: self.handle_return_scence   # 2019-04-12 增加退货场景 MK
        }

    def write(self, chunk):
        try:
            super().write(chunk)

            if INVALID_EPC in chunk:
                if len(self.statistics_info[BOX_ID]) == 1:
                    box_id = self.statistics_info[BOX_ID][0]
                elif len(self.statistics_info[REPORTED_EPC][BOX_ID]) == 1:
                    box_id = self.statistics_info[REPORTED_EPC][BOX_ID][0]
                else:
                    box_id = None

                if box_id is None:
                    return
                err_code = ResponseStatus.INVALID_EPC.value
                err_desc = response_desc[ResponseStatus.INVALID_EPC]

                self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                    TReceiptBatchCaseSkuStatistic.case_id == box_id
                ).update({
                    TReceiptBatchCaseSkuStatistic.remark: "%s:%s" % (err_code, err_desc)
                })

                self.db.commit()
                return

            if self.get_status() != 200 and self.msg_info is not None and \
                    self.msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.RECEIPT.value and self.statistics_info is not None:
                err_code = chunk[MSG_STATUS]
                err_desc = chunk[MSG_STATUS_TEXT]
                if len(self.statistics_info[BOX_ID]) == 1:
                    box_id = self.statistics_info[BOX_ID][0]
                elif len(self.statistics_info[REPORTED_EPC][BOX_ID]) == 1:
                    box_id = self.statistics_info[REPORTED_EPC][BOX_ID][0]
                else:
                    box_id = None

                if box_id is None:
                    return

                self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                    TReceiptBatchCaseSkuStatistic.case_id == box_id
                ).update({
                    TReceiptBatchCaseSkuStatistic.remark: "%s:%s" % (err_code, err_desc)
                })

                self.db.commit()

        except Exception as err_info:
            self.error("record  receipt remark failed: %s", err_info)

    @coroutine
    def post(self):
        """
        隧道机同步epc数据到服务器， 根据上报epc鉴别所属场景，然后调用相应处理方法
       
        :return: 
        """
        try:
            msg_info = self.msg_info
            scene, box_info = yield self.identify_epc_scene()
            if scene not in self.epc_scene_handler:
                self.error("not support this scene[%s]", scene)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()

            # 由于批量发货和工单清单的不可打断性，如果在这两个任务期间有其他任务上报，直接返回设备繁忙
            if msg_info[MSG_DEVICE_ID] in self.ship_count_transaction \
                    and msg_info[MSG_EPC_SYNC_TYPE] != self.ship_count_transaction[msg_info[MSG_DEVICE_ID]][1]:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.DEVICE_BUSY.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.DEVICE_BUSY]})
                self.finish()
                return

            yield self.epc_scene_handler[scene](box_info)

        except Exception as err_info:
            self.error("handle tm epc sync failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()
            
    @coroutine
    def identify_epc_scene(self):
        """
        根据epc同步类型，调用相应类型的鉴别方法
        
        :return: 返回所属场景，如果场景有效则返回对应的箱子信息，否则返回错误编码
        """
        try:
            self.info("identify epc scene")
            msg_info = self.msg_info

            if msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.RECEIPT.value:
                # 收货时上报的epc所属场景
                scene, info_or_reason = yield self.identify_receipt_epc_scene()
            elif msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.SHIP.value:
                # 发货时上报的epc所属场景
                scene, info_or_reason = yield self.identify_ship_epc_scene()
            elif msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.COUNT.value:
                scene, info_or_reason = yield self.identify_simple_count_scene()
            elif msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.LISTCOUNT.value:
                scene, info_or_reason = yield self.identify_list_count_scene()
            elif msg_info[MSG_EPC_SYNC_TYPE] == EpcSyncType.RETURN.value:
                # 2019-04-12 增加退货场景 MK
                scene, info_or_reason = yield self.identify_return_epc_scene()
            else:
                self.error("unknown epc sync type: %s", msg_info[MSG_EPC_SYNC_TYPE])
                scene = EpcScene.UNKNOWN_SCENE
                info_or_reason = ResponseStatus.WRONG_EPC_SYNC_TYPE

            return scene, info_or_reason

        except Exception as err_info:
            self.error("identify epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def handle_single_sku_scene(self, statistics_info):
        """
        处理上报数据中只有一个sku的情况

        :param statistics_info: 
        :return: 
        """
        try:
            self.info("handle single sku scene: %s", statistics_info)

            box_id = statistics_info[REPORTED_EPC][BOX_ID][0] if len(statistics_info[REPORTED_EPC][BOX_ID]) > 0 \
                else statistics_info[BOX_ID][0]

            order_sku = list(statistics_info[UNREPORTED_EPC].keys())[0] if len(statistics_info[UNREPORTED_EPC]) > 0 \
                else list(statistics_info[REPORTED_EPC][SKU_INFO].keys())[0]

            sku_states = self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.sku == order_sku)

            if sku_states.count() == 0:
                self.warning("box[%s] sku[%s] have finished", box_id, order_sku)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.EXTRA_SKU.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.EXTRA_SKU]})
                self.finish()
                return
            sku_state = sku_states.one()

            if sku_state.status == ReceiptSkuState.DONE_STATE.value:
                self.warning("box[%s] sku[%s] have finished", box_id, order_sku)
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.TRANSACTION_CONFIRMED.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.TRANSACTION_CONFIRMED]})
                self.finish()
                return

            un_report_epcs = statistics_info[UNREPORTED_EPC][order_sku] \
                if order_sku in statistics_info[UNREPORTED_EPC] else []
            reported_epcs = statistics_info[REPORTED_EPC][SKU_INFO][order_sku] \
                if order_sku in statistics_info[REPORTED_EPC][SKU_INFO] else []

            received_epcs = un_report_epcs + reported_epcs

            pre_receipted_count = self.db.query(TReceiptDetail).filter(
                TReceiptDetail.epc.in_(received_epcs),
                TReceiptDetail.status == ReceiptEpcState.PRE_RECEIPT.value).count()

            # 只要有一个没有预收货的商品，都当做没有预收货场景处理
            if pre_receipted_count == len(received_epcs) and len(statistics_info[INVALID_EPC]) == 0:
                yield self.handle_pre_receipted_scene(statistics_info)
            else:
                yield self.handle_un_pre_receipted_scene(statistics_info)

        except Exception as err_info:
            self.error("handle single sku scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_pre_receipted_scene(self, statistics_info):
        try:
            self.info("handle pre receipt scene")
            # 取出订单中这个箱子包含的sku
            box_id = statistics_info[REPORTED_EPC][BOX_ID][0] if len(statistics_info[REPORTED_EPC][BOX_ID]) > 0 \
                else statistics_info[BOX_ID][0]

            un_report_sku_info = {sku: len(statistics_info[UNREPORTED_EPC][sku])
                                  for sku in statistics_info[UNREPORTED_EPC]}
            reported_sku_info = {sku: len(statistics_info[REPORTED_EPC][SKU_INFO][sku])
                                 for sku in statistics_info[REPORTED_EPC][SKU_INFO]}

            received_sku_info = dict(Counter(un_report_sku_info) + Counter(reported_sku_info))

            order_sku = list(received_sku_info.keys())[0]

            success = self.record_receipt_scan_info(box_id, statistics_info, ReceiptScanState.SYNC_FAILED)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            epcs = statistics_info[REPORTED_EPC][SKU_INFO][order_sku]
            cloth_epcs = []
            cloth_epcs.extend(statistics_info[UNREPORTED_EPC][order_sku])
            cloth_epcs.extend(statistics_info[REPORTED_EPC][SKU_INFO][order_sku])
            customer_name = self.get_customer_id(cloth_epcs)

            # 组装反馈给隧道机的数据
            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: self.request_transid,
                MSG_CUSTOMER_ID: customer_name,
                MSG_BOX_NO: box_id,
                MSG_SKUS: []
            }

            # 统计满足退货条件数量MK 2019-04-24
            if not self.list_receipt_return_count(cloth_epcs, response_msg):
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.RETURN_DELAY.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.RETURN_DELAY]})
                self.finish()
                return

            success = self.db.query(TReceiptDetail).filter(TReceiptDetail.epc.in_(epcs)).update({
                TReceiptDetail.status: ReceiptEpcState.CHECKED.value
            }, synchronize_session='fetch')
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.move_receipt_detail_to_his(self.request_transid)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            # 更新实际收货数量
            success, storage_num = self.update_storage_num(box_id, order_sku)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.check_if_done(box_id, order_sku)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            for sku in received_sku_info:
                if sku == order_sku:
                    sku_info = {
                        MSG_SKU_NO: sku,
                        MSG_RECV_COUNT: received_sku_info[sku],
                        MSG_ORDER_COUNT: received_sku_info[sku],
                    }
                else:
                    sku_info = {
                        MSG_SKU_NO: sku,
                        MSG_RECV_COUNT: received_sku_info[sku],
                        MSG_ORDER_COUNT: 0
                    }
                response_msg[MSG_SKUS].append(sku_info)

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC]),
                    MSG_ORDER_COUNT: 0
                }
                response_msg[MSG_SKUS].append(sku_info)

            self.write(response_msg)
            self.sync_receipt_msg_to_wms(box_id, self.request_transid)

        except Exception as err_info:
            self.error("handle pre receipted scene exception: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_un_pre_receipted_scene(self, statistics_info):
        try:
            self.info("handle un_pre receipted scene")
            # 取出订单中这个箱子包含的sku
            box_id = statistics_info[REPORTED_EPC][BOX_ID][0] if len(statistics_info[REPORTED_EPC][BOX_ID]) > 0 \
                else statistics_info[BOX_ID][0]

            un_report_sku_info = {sku: len(statistics_info[UNREPORTED_EPC][sku])
                                  for sku in statistics_info[UNREPORTED_EPC]}
            reported_sku_info = {sku: len(statistics_info[REPORTED_EPC][SKU_INFO][sku])
                                 for sku in statistics_info[REPORTED_EPC][SKU_INFO]}

            received_sku_info = dict(Counter(un_report_sku_info) + Counter(reported_sku_info))

            order_sku = list(received_sku_info.keys())[0]

            success, ship_quantity = self.sku_ship_quantity_in_box(box_id, order_sku)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            received_quantity = received_sku_info[order_sku]

            self.info("received quantity[%s], ship quantity[%s]", received_quantity, ship_quantity)

            # 记录扫描流水
            if ship_quantity == received_quantity and len(statistics_info[INVALID_EPC]) == 0:
                success = self.record_receipt_scan_info(box_id, statistics_info, ReceiptScanState.TO_CHECK)
            else:
                success = self.record_receipt_scan_info(box_id, statistics_info, ReceiptScanState.TO_CONFIRM)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            # 更新订单信息
            if ship_quantity == received_quantity and len(statistics_info[INVALID_EPC]) == 0:
                success = self.update_receipt_sku_state(box_id, order_sku, ReceiptSkuState.TO_CHECK)
                if not success:
                    self.set_status(500)
                    self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                                MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                    self.finish()
                    return

            # 在写入收货信息前做退货检查
            cloth_epcs = []
            cloth_epcs.extend(statistics_info[UNREPORTED_EPC][order_sku])
            cloth_epcs.extend(statistics_info[REPORTED_EPC][SKU_INFO][order_sku])
            customer_name = self.get_customer_id(cloth_epcs)

            # 组装反馈给隧道机的数据
            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: self.request_transid,
                MSG_CUSTOMER_ID: customer_name,
                MSG_BOX_NO: box_id,
                MSG_SKUS: []
            }

            # 统计满足退货条件数量MK 2019-04-24
            if not self.list_receipt_return_count(cloth_epcs, response_msg):
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.RETURN_DELAY.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.RETURN_DELAY]})
                self.finish()
                return

            if ship_quantity == received_quantity and len(statistics_info[INVALID_EPC]) == 0:
                success = self.record_receipt_detail(statistics_info, ReceiptEpcState.PRE_RECEIPT)
            else:
                success = self.record_receipt_detail(statistics_info, ReceiptEpcState.SCANNED)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            if ship_quantity == received_quantity and len(statistics_info[INVALID_EPC]) == 0:
                # 更新sku收到的数量
                success = self.update_pre_receipt_num(box_id, order_sku)
                if not success:
                    self.set_status(500)
                    self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                                MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                    self.finish()
                    return

            for sku in received_sku_info:
                if sku == order_sku:
                    sku_info = {
                        MSG_SKU_NO: sku,
                        MSG_RECV_COUNT: received_sku_info[sku],
                        MSG_ORDER_COUNT: ship_quantity
                    }
                else:
                    sku_info = {
                        MSG_SKU_NO: sku,
                        MSG_RECV_COUNT: received_sku_info[sku],
                        MSG_ORDER_COUNT: 0
                    }
                response_msg[MSG_SKUS].append(sku_info)

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC]),
                    MSG_ORDER_COUNT: 0
                }
                response_msg[MSG_SKUS].append(sku_info)

            self.write(response_msg)

        except Exception as err_info:
            self.error("handle un_pre receipted scene exception: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_multi_sku_scene(self, statistics_info):
        """
        处理一箱中有多个sku的情况
        
        直接返回给隧道机 
        :param statistics_info:
        :return: 
        """
        try:
            self.info("handle multi sku scene: %s", statistics_info)
            box_id = statistics_info[BOX_ID][0] if len(statistics_info[BOX_ID]) > 0 \
                else statistics_info[REPORTED_EPC][BOX_ID][0]

            total_epcs = set()

            for epcs in chain( statistics_info[UNREPORTED_EPC].values(), statistics_info[REPORTED_EPC][SKU_INFO].values()):
                total_epcs = total_epcs.union(epcs)

            pre_receipted_count = self.db.query(TReceiptDetail).filter(
                TReceiptDetail.epc.in_(total_epcs),
                TReceiptDetail.status == ReceiptEpcState.PRE_RECEIPT.value).count()

            # 只要有一个没有预收货的商品，都当做没有预收货场景处理
            if pre_receipted_count == len(total_epcs) and len(statistics_info[INVALID_EPC]) == 0:
                is_pre_receipt = True
            else:
                is_pre_receipt = False

            state = ReceiptScanState.TO_UNPACK if is_pre_receipt else ReceiptScanState.TO_CHECK
            success = self.record_receipt_scan_info(box_id, statistics_info, state)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            # 在写入收货信息前做退货检查
            cloth_epcs = []
            for sku, epcs in chain(statistics_info[UNREPORTED_EPC].items(),
                                   statistics_info[REPORTED_EPC][SKU_INFO].items()):
                cloth_epcs.extend(epcs)

            customer_name = self.get_customer_id(cloth_epcs)

            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: self.request_transid,
                MSG_BOX_NO: box_id,
                MSG_CUSTOMER_ID: customer_name,
                MSG_SKUS: []
            }
            # 统计满足退货条件数量MK 2019-04-24
            if not self.list_receipt_return_count(cloth_epcs, response_msg):
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.RETURN_DELAY.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.RETURN_DELAY]})
                self.finish()
                return

            if not is_pre_receipt:
                success = self.record_receipt_detail(statistics_info, ReceiptEpcState.PRE_RECEIPT)
                if not success:
                    self.set_status(500)
                    self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                                MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                    self.finish()
                    return

                received_skus = set(statistics_info[UNREPORTED_EPC].keys()).union(statistics_info[REPORTED_EPC][SKU_INFO].keys())
                for sku in received_skus:
                    success = self.update_pre_receipt_num(box_id, sku)
                    if not success:
                        self.set_status(500)
                        self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                                    MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                        self.finish()
                        return
            else:
                self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                    TReceiptBatchCaseSkuStatistic.case_id == box_id
                ).update({
                    TReceiptBatchCaseSkuStatistic.remark: "%s:%s" % ("0000", "待拆箱")
                })

            success = self.update_receipt_order_state(box_id, ReceiptCaseState.RECEIPTING_STATE)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            sku_infos = self.pack_receipt_multi_sku_response_msg(statistics_info)
            if sku_infos is None:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return
            response_msg[MSG_SKUS] = sku_infos

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC]),
                    MSG_ORDER_COUNT: 0
                }
                response_msg[MSG_SKUS].append(sku_info)

            self.write(response_msg)

        except Exception as err_info:
            self.error("handle order multi sku scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_simple_count_scene(self, statistics_info):
        """
        处理简单清点场景
        
        :param statistics_info: 
        :return: 
        """
        try:
            self.info("handle simple count scene: %s", statistics_info)

            cloth_epcs = []
            for sku, epcs in statistics_info[SKU_INFO].items():
                cloth_epcs.extend(epcs)

            customer_name = self.get_customer_id(cloth_epcs)

            response_info = {
                MSG_BOX_NO: "",
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: "",
                MSG_CUSTOMER_ID: customer_name,
                MSG_SKUS: []
            }

            for sku in statistics_info[SKU_INFO]:
                sku_info = {
                    MSG_SKU_NO: sku,
                    MSG_ORDER_COUNT: 0,
                    MSG_RECV_COUNT: len(statistics_info[SKU_INFO][sku])
                }
                response_info[MSG_SKUS].append(sku_info)

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_ORDER_COUNT: 0,
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC])
                }
                response_info[MSG_SKUS].append(sku_info)

            self.write(response_info)

        except Exception as err_info:
            self.error("handle simple count scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})

    @coroutine
    def handle_ship_scene(self, statistics_info):
        """
        处理发货场景
        
        :param statistics_info: 
        :return: 
        """
        try:
            self.info("handle ship scene: %s", statistics_info)

            device_id = self.msg_info[MSG_DEVICE_ID]
            ship_id = self.ship_count_transaction[device_id][0]

            success = self.record_ship_detail(ship_id, statistics_info)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            success = self.update_ship_num(ship_id)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            cloth_epcs = []
            for sku, epcs in chain(statistics_info[UNREPORTED_EPC].items(), statistics_info[REPORTED_EPC].items()):
                cloth_epcs.extend(epcs)

            customer_name = self.get_customer_id(cloth_epcs)

            response_info = {
                MSG_BOX_NO: "",
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: "",
                MSG_CUSTOMER_ID: customer_name,
                MSG_SKUS: []
            }

            sku_infos = self.pack_ship_response_msg(ship_id, statistics_info)
            if sku_infos is None:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return
            response_info[MSG_SKUS] = sku_infos

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC]),
                    MSG_ORDER_COUNT: 0
                }
                response_info[MSG_SKUS].append(sku_info)

            self.write(response_info)
            self.finish()

            self.sync_ship_msg_to_wms(statistics_info)
        except Exception as err_info:
            self.error("handle ship scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_list_count_scene(self, statistics_info):
        """
        处理工单清点

        :param statistics_info:
        :return:
        """
        try:
            self.info("handle list count scene: %s", statistics_info)

            device_id = self.msg_info[MSG_DEVICE_ID]
            ship_id = self.ship_count_transaction[device_id][0]

            success = self.record_list_count_log(ship_id, statistics_info)
            if not success:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            cloth_epcs = []
            for sku, epcs in statistics_info[SKU_INFO].items():
                cloth_epcs.extend(epcs)

            customer_name = self.get_customer_id(cloth_epcs)

            response_info = {
                MSG_BOX_NO: "",
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: "",
                MSG_CUSTOMER_ID: customer_name,
                MSG_SKUS: []
            }

            sku_infos = self.pack_list_count_response_msg(ship_id, statistics_info)
            if sku_infos is None:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            response_info[MSG_SKUS] = sku_infos

            if len(statistics_info[INVALID_EPC]) > 0:
                sku_info = {
                    MSG_SKU_NO: "无效芯片",
                    MSG_ORDER_COUNT: 0,
                    MSG_RECV_COUNT: len(statistics_info[INVALID_EPC])
                }
                response_info[MSG_SKUS].append(sku_info)

            self.write(response_info)
            self.finish()

            self.sync_list_count_msg_to_wms(statistics_info)

        except Exception as err_info:
            self.error("handle list count scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_unknown_scene(self, status):
        """
        处理区分不出场景的情况
        
        :param status: 
        :return: 
        """
        try:
            self.info("handle unknown scene")
            self.set_status(500)
            if status not in response_desc:
                self.error("status not in response description")
                self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
                self.finish()
                return

            self.write({MSG_STATUS: status.value, MSG_STATUS_TEXT: response_desc[status]})
            self.finish()

        except Exception as err_info:
            self.error("handle unknown scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def handle_return_scence(self, statistics_info):
        """
            2019-04-24 MK
            退货发运
            :param statistics_info:
            :return:
        """
        try:
            self.info("handle return scene: %s", statistics_info)
            box_id = statistics_info[BOX_ID]

            total_epcs = set(statistics_info[RETURN_EPC])

            # 查找不满足预退货的退货信息
            valid_epc_count = self.db.query(TReturnInfo).filter(
                TReturnInfo.epc.in_(total_epcs),
                TReturnInfo.return_status == ReturnEpcState.PRE_RETURN.value
            ).group_by(TReturnInfo.epc).count()

            # 标签没在退货表里面则返回错误提醒信息
            if valid_epc_count == (len(set(self.msg_info[MSG_EPCS])) - len(box_id)):
                valid_return = True
            else:
                valid_return = False

            # 如果标签没在退货表里面，提示需首先进行质检预退货
            if valid_return is False:
                self.set_status(500)
                self.write({MSG_STATUS: ResponseStatus.NEED_INSPECT.value,
                            MSG_STATUS_TEXT: response_desc[ResponseStatus.NEED_INSPECT]})
                self.finish()
                return

            # 获取供货商编号
            customer_name = self.get_customer_id(total_epcs)

            # 将tranid和EPC写入return_track_transaction
            request_transid = self.request_transid
            device_id = self.msg_info[MSG_DEVICE_ID]
            TMBaseReqHandler.return_track_transaction[device_id + request_transid] = statistics_info[RETURN_EPC]

            # 初始化返回数据格式
            response_msg = {
                MSG_STATUS: ResponseStatus.SUCCESS.value,
                MSG_STATUS_TEXT: response_desc[ResponseStatus.SUCCESS],
                MSG_TRANS_ID: request_transid,
                MSG_BOX_NO: "",
                MSG_CUSTOMER_ID: customer_name,
                MSG_SKUS: []
            }

            # 退货详情信息
            sku_infos = []
            sku_no = []
            returninfo = self.db.query(TReturnInfo.sku).filter(
                TReturnInfo.epc.in_(total_epcs),
                TReturnInfo.return_status == ReturnEpcState.PRE_RETURN.value
            ).group_by(TReturnInfo.epc)

            # 返回退货信息，等待填写运单
            c = Counter(returninfo)
            returninfo = list(set(returninfo))
            for sku_info in returninfo:
                info = {
                    MSG_SKU_NO: sku_info.sku,
                    MSG_RECV_COUNT: c[sku_info],
                    MSG_ORDER_COUNT: 0
                }

                sku_infos.append(info)

            response_msg[MSG_SKUS] = sku_infos
            self.write(response_msg)
            self.finish()

        except Exception as err_info:
            self.error("handle return scene failed: %s", err_info)
            self.set_status(500)
            self.write({MSG_STATUS: ResponseStatus.SYSTEM_ERROR.value,
                        MSG_STATUS_TEXT: response_desc[ResponseStatus.SYSTEM_ERROR]})
            self.finish()

    @coroutine
    def identify_receipt_epc_scene(self):
        """
        ，除了正常场景外，其余场景都属于unknown,

        :return: 返回场景，如果场景属于正常场景并附带统计数据，否则携带错误码
        """
        try:
            self.info("identify receipt epc scene")

            # 分析标签数据
            statistics_info = yield self.statistics_receipt_epc_data()
            self.statistics_info = statistics_info
            if statistics_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            if statistics_info[COMMITTED_EPC]:
                self.error("have cloth epc already committed")
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.CLOTH_ALREADY_COMMITTED

            received_sku = set(statistics_info[REPORTED_EPC][SKU_INFO]).union(statistics_info[UNREPORTED_EPC])
            if len(received_sku) == 0:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.INVALID_EPC

            # 有未上报的标签，必须有箱标
            if len(statistics_info[UNREPORTED_EPC]) > 0 and len(statistics_info[BOX_ID]) == 0:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.NO_BOX_ID

            # 统计二次收货的数量
            epcs = set()
            for epc_list in chain(statistics_info[UNREPORTED_EPC].values(),
                                  statistics_info[REPORTED_EPC][SKU_INFO].values()):
                epcs = epcs.union(epc_list)

            pre_receipted_count = self.db.query(TReceiptDetail).filter(
                TReceiptDetail.epc.in_(epcs),
                TReceiptDetail.status == ReceiptEpcState.PRE_RECEIPT.value).count()

            if len(epcs) == pre_receipted_count:
                statistics_info[BOX_ID].clear()

            if len(statistics_info[BOX_ID]) == 0 and len(statistics_info[REPORTED_EPC][BOX_ID]) == 0:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.NO_BOX_ID
            elif len(statistics_info[BOX_ID]) > 1 or len(statistics_info[REPORTED_EPC][BOX_ID]) > 1:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.MULTI_BOX_ID
            elif len(statistics_info[BOX_ID]) == 1 and len(statistics_info[REPORTED_EPC][BOX_ID]) == 1 \
                    and statistics_info[BOX_ID][0] != statistics_info[REPORTED_EPC][BOX_ID][0]:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.CLOTH_BELONG_OTHER_BOX

            box_id = statistics_info[REPORTED_EPC][BOX_ID][0] if len(statistics_info[REPORTED_EPC][BOX_ID]) > 0 \
                else statistics_info[BOX_ID][0]
            order_info = self.query_receipt_sku_info_in_box(box_id)

            if len(order_info) == 0:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.INVALID_BOX_ID

            # if not received_sku.issubset(order_info):
            #     return EpcScene.UNKNOWN_SCENE, ResponseStatus.EXTRA_SKU

            if len(received_sku) == 1:
                return EpcScene.RECEIPT_SINGLE_SKU, statistics_info
            else:
                return EpcScene.RECEIPT_MULTI_SKU, statistics_info

        except Exception as err_info:
            self.error("identify receipt epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def identify_ship_epc_scene(self):
        try:
            device_id = self.msg_info[MSG_DEVICE_ID]
            if device_id not in self.ship_count_transaction:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.TASK_NOT_STARTED

            statistics_info = yield self.statistics_ship_epc_data()
            if statistics_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            if statistics_info[COMMITTED_EPC]:
                self.error("have cloth epc already committed")
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.CLOTH_ALREADY_COMMITTED

            order_id = self.ship_count_transaction[device_id][0]
            order_sku_info = self.query_ship_sku_info_in_order(order_id)
            if order_sku_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            received_sku = set(statistics_info[REPORTED_EPC].keys()).union(statistics_info[UNREPORTED_EPC].keys())
            statistics_info[EXTRA_SKU] = list(received_sku - order_sku_info)

            return EpcScene.SHIP, statistics_info

        except Exception as err_info:
            self.error("identify receipt epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def identify_simple_count_scene(self):
        try:
            statistics_info = yield self.statistics_count_epc_data()
            if statistics_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            return EpcScene.SIMPLE_COUNT, statistics_info

        except Exception as err_info:
            self.error("identify simple count epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def identify_list_count_scene(self):
        try:
            device_id = self.msg_info[MSG_DEVICE_ID]
            if device_id not in self.ship_count_transaction:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.TASK_NOT_STARTED

            statistics_info = yield self.statistics_count_epc_data()
            if statistics_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            order_id = self.ship_count_transaction[device_id][0]
            order_sku_info = self.query_ship_sku_info_in_order(order_id)
            if order_sku_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            received_sku = set(statistics_info[SKU_INFO])
            statistics_info[EXTRA_SKU] = list(received_sku - order_sku_info)

            return EpcScene.LIST_COUNT, statistics_info

        except Exception as err_info:
            self.error("identify list count epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def identify_return_epc_scene(self):
        """
        ，除了正常场景外，其余场景都属于unknown,
        2019-04-24 MK
        :return: 返回场景，如果场景属于正常场景并附带统计数据，否则携带错误码
        """
        try:
            self.info("identify return epc scene")

            # 分析标签数据
            statistics_info = yield self.statistics_return_epc_data()

            self.statistics_info = statistics_info
            if statistics_info is None:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

            # 无EPC 直接返回
            returned_ecp = set(statistics_info[RETURN_EPC])
            if len(returned_ecp) == 0:
                return EpcScene.UNKNOWN_SCENE, ResponseStatus.INVALID_EPC

            # 退货时
            return EpcScene.RETURN, statistics_info

        except Exception as err_info:
            self.error("identify return epc scene failed: %s", err_info)
            return EpcScene.UNKNOWN_SCENE, ResponseStatus.SYSTEM_ERROR

    @coroutine
    def statistics_return_epc_data(self):
        """
           只统计退货标签数据，不做区分
        """
        try:
            msg_info = self.msg_info
            statistics = {
                RETURN_EPC: [],
                BOX_ID: []
            }

            for epc in msg_info[MSG_EPCS]:
                # 取出标签类型
                if len(epc) < 12:
                    continue

                success, epc_type, sku, order_id = self.query_epc_detail_info(epc)
                if not success:
                    continue

                # 判断标签类型
                if epc_type == BOX_EPC_PREIX:
                    # statistics[BOX_ID] = epc
                    if epc not in statistics[BOX_ID]:
                        statistics[BOX_ID].append(epc)
                else:
                    statistics[RETURN_EPC].append(epc)

            return statistics
        except Exception as err_info:
            self.error("statistics return epc scene failed: %s", err_info)
            return None


    @coroutine
    def statistics_receipt_epc_data(self):
        """
        统计标签数据
        
        把标签数据分为已上报、未上报、非法标签三种，并检查箱标标签，统计衣服标签属于哪种sku
        
        :return: 统计成功，则返回统计数据，失败返回None
        """
        try:
            msg_info = self.msg_info
            statistics = {
                REPORTED_EPC: {
                    BOX_ID: set(),
                    SKU_INFO: defaultdict(set)
                },
                COMMITTED_EPC: False,
                UNREPORTED_EPC: defaultdict(set),
                INVALID_EPC: [],
                BOX_ID: set(),
                ORDER_INFO: defaultdict(set)
            }

            order_info = defaultdict(set)

            for epc in msg_info[MSG_EPCS]:
                # 取出标签类型
                if len(epc) < 12:
                    statistics[INVALID_EPC].append(epc)
                    continue

                success, epc_type, sku, order_id = self.query_epc_detail_info(epc)
                if not success:
                    statistics[INVALID_EPC].append(epc)
                    continue

                # 判断标签类型
                if epc_type == BOX_EPC_PREIX:
                    statistics[BOX_ID].add(epc)
                elif epc_type == CLOTH_EPC_PREFIX:
                    state, previous_box_id = self.receipt_epc_state(epc)
                    if state == EpcState.UN_COMMITTED:
                        statistics[REPORTED_EPC][BOX_ID].add(previous_box_id)
                        statistics[REPORTED_EPC][SKU_INFO][sku].add(epc)
                        order_info[order_id].add(sku)

                    elif state == EpcState.UN_REPORTED:
                        statistics[UNREPORTED_EPC][sku].add(epc)

                        order_info[order_id].add(sku)
                    elif state == EpcState.COMMITTED:
                        # 兼容2018/6/11之前的处理流程，如果在这之前的订单，直接把收货数据删掉，然后重新收货
                        order_count = self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                            TReceiptBatchCaseSkuStatistic.case_id == previous_box_id,
                            TReceiptBatchCaseSkuStatistic.sku == sku,
                            TReceiptBatchCaseSkuStatistic.received_date < datetime(year=2018, month=6, day=11)
                        ).count()

                        if order_count > 0:
                            self.db.query(TReceiptDetailHistory).filter(
                                TReceiptDetailHistory.epc == epc).delete(synchronize_session='fetch')
                            statistics[UNREPORTED_EPC][sku].add(epc)
                            order_info[order_id].add(sku)
                            continue

                        # 已经提交过的数据再次上报，直接返回错误
                        statistics[COMMITTED_EPC] = True
                        order_info[order_id].add(sku)
                        break

                    else:
                        statistics[INVALID_EPC].append(epc)
                else:
                    statistics[INVALID_EPC].append(epc)

            statistics[ORDER_INFO] = order_info
            statistics[REPORTED_EPC][BOX_ID] = list(statistics[REPORTED_EPC][BOX_ID])
            for sku in statistics[REPORTED_EPC][SKU_INFO].keys():
                statistics[REPORTED_EPC][SKU_INFO][sku] = list(statistics[REPORTED_EPC][SKU_INFO][sku])

            for sku in statistics[UNREPORTED_EPC].keys():
                statistics[UNREPORTED_EPC][sku] = list(statistics[UNREPORTED_EPC][sku])

            statistics[BOX_ID] = list(statistics[BOX_ID])
            for order_id in statistics[ORDER_INFO].keys():
                statistics[ORDER_INFO][order_id] = list(statistics[ORDER_INFO][order_id])

            return statistics

        except Exception as err_info:
            self.error("statistics trading epc scene failed: %s", err_info)
            return None

    @coroutine
    def statistics_ship_epc_data(self):
        """
        统计发货epc数据
        
        :return: 
        """
        try:
            msg_info = self.msg_info
            statistics = {
                REPORTED_EPC: defaultdict(set),
                COMMITTED_EPC: False,
                UNREPORTED_EPC: defaultdict(set),
                INVALID_EPC: [],
                BOX_ID: set()
            }

            for epc in msg_info[MSG_EPCS]:
                # 取出标签类型
                if len(epc) < 12:
                    statistics[INVALID_EPC].append(epc)
                    continue

                success, epc_type, sku, order_id = self.query_epc_detail_info(epc)
                if not success:
                    statistics[INVALID_EPC].append(epc)

                # 判断标签类型
                if epc_type == BOX_EPC_PREIX:statistics[BOX_ID].add(epc)

                elif epc_type == CLOTH_EPC_PREFIX:
                    state = self.ship_epc_state(epc)
                    if state == EpcState.UN_COMMITTED:
                        statistics[REPORTED_EPC][sku].add(epc)

                    elif state == EpcState.UN_REPORTED:
                        statistics[UNREPORTED_EPC][sku].add(epc)

                    elif state == EpcState.COMMITTED:
                        # 已经提交过的数据再次上报，直接返回错误
                        statistics[COMMITTED_EPC] = True
                        break
                    else:
                        statistics[INVALID_EPC].append(epc)
                else:
                    statistics[INVALID_EPC].append(epc)

            for sku in statistics[UNREPORTED_EPC].keys():
                statistics[UNREPORTED_EPC][sku] = list(statistics[UNREPORTED_EPC][sku])

            for sku in statistics[REPORTED_EPC].keys():
                statistics[REPORTED_EPC][sku] = list(statistics[REPORTED_EPC][sku])

            return statistics

        except Exception as err_info:
            self.error("statistics trading epc scene failed: %s", err_info)
            return None

    def query_epc_detail_info(self, epc):
        try:
            result = self.db.query(TTagPrintResult).filter(TTagPrintResult.epc == epc).one()
            if result.result != 1:
                self.db.query(TTagPrintResult).filter(TTagPrintResult.epc == epc).update(
                    {
                        TTagPrintResult.result: 1
                    }
                )

                if result.tag_type[:1].upper() == BOX_EPC_PREIX:
                    self.db.query(TCaseInfo).filter(TCaseInfo.case_id == epc).update(
                        {
                            TCaseInfo.print_result: 1
                        }
                    )
                else:
                    self.db.query(TEpcDetail).filter(TEpcDetail.epc == epc).update(
                        {
                            TEpcDetail.print_result: 1
                        }
                    )

            return True, result.tag_type[:1].upper(), result.sku, result.order_no

        except Exception as err_info:
            self.error("query epc detail info exception: %", err_info)
            return False, None, None, None

    @coroutine
    def statistics_count_epc_data(self):
        """
        统计清点epc数据
        
        :return: 
        """
        try:
            msg_info = self.msg_info
            statistics = {
                BOX_ID: set(),
                SKU_INFO: defaultdict(set),
                INVALID_EPC: set(),
            }

            for epc in msg_info[MSG_EPCS]:
                # 取出标签类型
                if len(epc) < 12:
                    statistics[INVALID_EPC].add(epc)
                    continue

                success, epc_type, sku, order_id = self.query_epc_detail_info(epc)
                if not success:
                    statistics[INVALID_EPC].add(epc)

                # 判断标签类型
                if epc_type == BOX_EPC_PREIX:
                    statistics[BOX_ID].add(epc)
                elif epc_type == CLOTH_EPC_PREFIX:
                    statistics[SKU_INFO][sku].add(epc)
                else:
                    statistics[INVALID_EPC].add(epc)

            statistics[BOX_ID] = list(statistics[BOX_ID])
            for sku in statistics[SKU_INFO]:
                statistics[SKU_INFO][sku] = list(statistics[SKU_INFO][sku])
            return statistics

        except Exception as err_info:
            self.error("statistics count epc scene failed: %s", err_info)
            return None

    def receipt_epc_state(self, epc):
        """
        查询收货epc是否已经上报过，上报过的都会在detail表中记录一条数据
        
        :param epc: 
        :return: 
        """
        try:
            result = self.db.query(TReceiptDetailHistory).filter(
                TReceiptDetailHistory.epc == epc,
                TReceiptDetailHistory.status == ReceiptEpcState.CHECKED.value).one()
            self.debug("receipt epc[%s] have committed", epc)
            return EpcState.COMMITTED, result.case_id

        except NoResultFound:
            self.debug("receipt epc[%s] not in detail history table ", epc)
        except MultipleResultsFound:
            self.debug("receipt epc[%s] already in detail history table", epc)
            result = self.db.query(TReceiptDetailHistory).filter(TReceiptDetailHistory.epc == epc).all()[0]
            return EpcState.COMMITTED, result.case_id
        except Exception as err_info:
            self.error("check receipt epc whether reported failed: %s", err_info)
            return EpcState.UN_REPORTED, None

        try:
            result = self.db.query(TReceiptDetail).filter(TReceiptDetail.epc == epc).one()
            self.debug("receipt epc[%s] have reported", epc)
            return EpcState.UN_COMMITTED, result.case_id

        except NoResultFound:
            self.debug("receipt epc[%s] not in detail table", epc)
            return EpcState.UN_REPORTED, None
        except MultipleResultsFound:
            self.debug("receipt epc[%s] have reported", epc)
            result = self.db.query(TReceiptDetail).filter(TReceiptDetail.epc == epc).all()[0]
            return EpcState.UN_COMMITTED, result.case_id
        except Exception as err_info:
            self.error("check receipt epc whether reported failed: %s", err_info)
            return EpcState.UN_REPORTED, None

    def ship_epc_state(self, epc):
        """
        查询收货epc是否已经上报过，上报过的都会在detail表中记录一条数据

        :param epc: 
        :return: 
        """
        try:
            self.db.query(TShipDetailHistory).filter(TShipDetailHistory.epc == epc).one()
            self.debug("ship epc[%s] have committed", epc)
            return EpcState.COMMITTED

        except NoResultFound:
            self.debug("ship epc[%s] not in detail history table ", epc)
        except MultipleResultsFound:
            self.debug("ship epc[%s] already in detail history table", epc)
            return EpcState.COMMITTED
        except Exception as err_info:
            self.error("check ship epc whether reported failed: %s", err_info)
            return EpcState.UN_REPORTED

        try:
            self.db.query(TShipDetail).filter(TShipDetail.epc == epc).one()
            self.debug("receipt epc[%s] have reported", epc)
            return EpcState.UN_COMMITTED

        except NoResultFound:
            self.debug("receipt epc[%s] not in detail table", epc)
            return EpcState.UN_REPORTED
        except MultipleResultsFound:
            self.debug("receipt epc[%s] have reported", epc)
            return EpcState.UN_COMMITTED
        except Exception as err_info:
            self.error("check receipt epc whether reported failed: %s", err_info)
            return EpcState.UN_REPORTED

    def query_receipt_sku_info_in_box(self, box_epc):
        """
        查询箱子的打包情况
        
        :param box_epc: 
        :return: 
        """
        try:
            sku_infos = self.db.query(
                TReceiptBatchCaseSkuStatistic).\
                filter(TReceiptBatchCaseSkuStatistic.case_id == box_epc).all()

            order_sku = set()
            for sku_info in sku_infos:
                order_sku.add(sku_info.sku)

            return order_sku

        except Exception as err_info:
            self.error("query box package info failed: %s", err_info)
            return None

    def record_receipt_detail(self, statistics_info, state):
        """
        记录上报的数据
        
        :param statistics_info:
        :param state:
        :return: 
        """
        try:
            box_id = statistics_info[BOX_ID][0] if len(statistics_info[BOX_ID]) > 0 \
                else statistics_info[REPORTED_EPC][BOX_ID][0]

            batch_case_info = self.db.query(TReceiptBatchCase).filter(TReceiptBatchCase.case_id == box_id).one()
            order_skus = self.query_receipt_sku_info_in_box(box_id)

            if order_skus is None:
                return False

            for sku, epcs in statistics_info[UNREPORTED_EPC].items():
                if sku not in order_skus:
                    continue

                for epc in epcs:
                    receipt_info = TReceiptDetail()
                    receipt_info.batch_id = batch_case_info.batch_id
                    receipt_info.order_id = ""
                    receipt_info.case_id = box_id
                    receipt_info.sku = sku
                    receipt_info.epc = epc
                    receipt_info.status = state.value
                    self.db.add(receipt_info)

            for sku, epcs in statistics_info[REPORTED_EPC][SKU_INFO].items():
                if sku not in order_skus:
                    continue

                for epc in epcs:
                    self.db.query(TReceiptDetail).filter(
                        TReceiptDetail.epc == epc,
                        TReceiptDetail.case_id == box_id
                    ).update({
                        TReceiptDetail.status: state.value
                    })

            return True

        except Exception as err_info:
            self.error("record receipt detail info failed: %s", err_info)
            return False

    def record_receipt_detail_his(self, statistics_info):
        """
        收货详细信息的历史记录

        :param statistics_info:
        :return: 
        """
        try:
            self.info("record receipt detail history")
            box_id = statistics_info[BOX_ID][0] if len(statistics_info[BOX_ID]) > 0 \
                else statistics_info[REPORTED_EPC][BOX_ID][0]

            batch_case_info = self.db.query(TReceiptBatchCase).filter(TReceiptBatchCase.case_id == box_id).one()

            for sku, epcs in chain(statistics_info[REPORTED_EPC][SKU_INFO].items(),statistics_info[UNREPORTED_EPC].items()):
                for epc in epcs:
                    receipt_info = TReceiptDetailHistory()
                    receipt_info.batch_id = batch_case_info.batch_id
                    receipt_info.order_id = ""
                    receipt_info.case_id = box_id
                    receipt_info.sku = sku
                    receipt_info.epc = epc
                    self.db.add(receipt_info)

            # 删除detail表中数据
            if box_id in self.msg_info[MSG_EPCS]:
                self.msg_info[MSG_EPCS].remove(box_id)
                
            result = self.db.query(TReceiptDetail).filter(TReceiptDetail.epc.in_(self.msg_info[MSG_EPCS]))
            result.delete(synchronize_session='fetch')

            return True

        except Exception as err_info:
            self.error("record receipt detail history info failed: %s", err_info)
            return False

    def record_ship_detail(self, order_id, statistics_info):
        """
        记录上报的数据

        :param order_id:
        :param statistics_info:
        :return: 
        """
        try:
            for sku in statistics_info[UNREPORTED_EPC]:
                for epc in statistics_info[UNREPORTED_EPC][sku]:
                    ship_detail = TShipDetail()
                    ship_detail.ship_id = order_id
                    ship_detail.sku = sku
                    ship_detail.epc = epc
                    self.db.add(ship_detail)

            return True

        except Exception as err_info:
            self.error("record ship detail info failed: %s", err_info)
            return False

    def record_list_count_log(self, ship_id, statistics_info):
        """
        记录工单清单历史记录

        :param ship_id:
        :param statistics_info:
        :return:
        """
        try:
            order_sku_infos = self.db.query(TShipOrderDetail).filter(TShipOrderDetail.ship_id == ship_id).all()

            for order_sku_info in order_sku_infos:
                if order_sku_info.sku in statistics_info[SKU_INFO]:
                    count_log = TListCountLog()
                    count_log.sku = order_sku_info.sku
                    count_log.ship_id = ship_id
                    count_log.count_date = datetime.now()
                    count_log.ship_quantity = order_sku_info.ship_quantity
                    count_log.counted_quantity = len(statistics_info[SKU_INFO][order_sku_info.sku])
                    self.db.add(count_log)

            return True

        except Exception as err_info:
            self.error("record list count log failed: %s", err_info)
            return False

    def update_ship_num(self, ship_id):
        """
        更新收货信息中对应sku收货的实际数量

        :param ship_id: 
        :return: 
        """
        try:

            result = self.db.query(TShipDetail.sku, func.count("*").label('received_quantity')).\
                filter(TShipDetail.ship_id == ship_id).group_by(TShipDetail.sku).all()

            for sku, quantity in result:
                self.db.query(TShipOrderDetail).filter(
                    TShipOrderDetail.ship_id == ship_id,
                    TShipOrderDetail.sku == sku,
                    TShipOrderDetail.shipped_quantity == 0
                ).\
                    update(
                    {
                        TShipOrderDetail.ship_date: datetime.now()
                    })

            for sku, quantity in result:
                self.db.query(TShipOrderDetail).filter(
                    TShipOrderDetail.ship_id == ship_id,
                    TShipOrderDetail.sku == sku).\
                    update(
                    {
                        TShipOrderDetail.shipped_quantity: int(quantity)
                    })
            return True

        except Exception as err_info:
            self.error("update receipt sku number failed: %s", err_info)
            return False

    def update_receipt_order_num(self, box_id):
        """
        在对一箱货品确认时，更新这箱的实际收货数量，还有这箱所属批次的实际收货数量
        
        :param box_id: 
        :return: 
        """
        try:
            case_receive_num = self.db.query(func.sum(TReceiptBatchCaseSkuStatistic.received_quantity).
                                             label('received_quantity')).\
                filter(TReceiptBatchCaseSkuStatistic.case_id == box_id).one()

            self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id,
                TReceiptBatchCase.status != ReceiptCaseState.CANCEL_STATE.value
            ).update(
                {
                    TReceiptBatchCase.received_quantity: case_receive_num.received_quantity
                }
            )

            batch_case_info = self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id,
                TReceiptBatchCase.status != ReceiptCaseState.CANCEL_STATE.value
            ).one()

            self.db.query(TReceiptInfo).filter(TReceiptInfo.order_id == batch_case_info.order_id).update(
                {
                    TReceiptInfo.received_quantity: TReceiptInfo.received_quantity + case_receive_num.received_quantity
                }
            )
            return True

        except Exception as err_info:
            self.error("update receipt order number failed: %s", err_info)
            return False

    def pack_receipt_multi_sku_response_msg(self, statistics_info):
        """
        组装多sku的反馈信息
        
        :param statistics_info: 
        :return: 
        """
        try:
            box_id = statistics_info[BOX_ID][0] if len(statistics_info[BOX_ID]) > 0 \
                else statistics_info[REPORTED_EPC][BOX_ID][0]
            order_sku_infos = self.query_receipt_case_sku_info_by_box(box_id)
            if order_sku_infos is None:
                return None

            un_report_sku_info = {sku: len(statistics_info[UNREPORTED_EPC][sku])
                                  for sku in statistics_info[UNREPORTED_EPC]}
            reported_sku_info = {sku: len(statistics_info[REPORTED_EPC][SKU_INFO][sku])
                                 for sku in statistics_info[REPORTED_EPC][SKU_INFO]}

            received_sku_infos = dict(Counter(un_report_sku_info) +
                                      Counter(reported_sku_info))
            response_info = []
            for sku_info in order_sku_infos:
                if sku_info.sku in received_sku_infos:
                    info = {
                        MSG_SKU_NO: sku_info.sku,
                        MSG_RECV_COUNT: received_sku_infos[sku_info.sku],
                        MSG_ORDER_COUNT: sku_info.ship_quantity
                    }
                    response_info.append(info)
                    del received_sku_infos[sku_info.sku]

                else:
                    info = {
                        MSG_SKU_NO: sku_info.sku,
                        MSG_RECV_COUNT: 0,
                        MSG_ORDER_COUNT: sku_info.ship_quantity
                    }
                    response_info.append(info)

            for sku in received_sku_infos:
                info = {
                    MSG_SKU_NO: sku,
                    MSG_RECV_COUNT: received_sku_infos[sku],
                    MSG_ORDER_COUNT: 0
                }
                response_info.append(info)

            return response_info

        except Exception as err_info:
            self.error("pack multi sku response msg: %s", err_info)
            return None

    def pack_ship_response_msg(self, ship_id, statistics_info):
        """
        组装发货的消息

        :param ship_id:
        :param statistics_info:
        :return:
        """
        try:
            order_sku_infos = self.db.query(TShipOrderDetail).filter(TShipOrderDetail.ship_id == ship_id).all()

            reported_sku = {sku: len(statistics_info[REPORTED_EPC][sku]) for sku in statistics_info[REPORTED_EPC]}
            un_reported_sku = {sku: len(statistics_info[UNREPORTED_EPC][sku])
                               for sku in statistics_info[UNREPORTED_EPC]}

            received_sku_infos = dict(Counter(reported_sku) + Counter(un_reported_sku))

            response_info = []
            for sku_info in order_sku_infos:
                if sku_info.sku in received_sku_infos:
                    info = {
                        MSG_SKU_NO: sku_info.sku,
                        MSG_RECV_COUNT: received_sku_infos[sku_info.sku],
                        MSG_ORDER_COUNT: sku_info.ship_quantity
                    }
                    response_info.append(info)
                    del received_sku_infos[sku_info.sku]

            for sku in received_sku_infos:
                info = {
                    MSG_SKU_NO: sku,
                    MSG_RECV_COUNT: received_sku_infos[sku],
                    MSG_ORDER_COUNT: 0
                }
                response_info.append(info)

            return response_info

        except Exception as err_info:
            self.error("pack ship sku response msg: %s", err_info)
            return None

    def pack_list_count_response_msg(self, ship_id, statistics_info):
        """
        组装发货的消息

        :param ship_id:
        :param statistics_info:
        :return:
        """
        try:
            order_sku_infos = self.db.query(TShipOrderDetail).filter(TShipOrderDetail.ship_id == ship_id).all()

            received_sku_infos = {sku: len(statistics_info[SKU_INFO][sku]) for sku in statistics_info[SKU_INFO]}

            response_info = []
            for sku_info in order_sku_infos:
                if sku_info.sku in received_sku_infos:
                    info = {
                        MSG_SKU_NO: sku_info.sku,
                        MSG_RECV_COUNT: received_sku_infos[sku_info.sku],
                        MSG_ORDER_COUNT: sku_info.ship_quantity
                    }
                    response_info.append(info)
                    del received_sku_infos[sku_info.sku]

            for sku in received_sku_infos:
                info = {
                    MSG_SKU_NO: sku,
                    MSG_RECV_COUNT: received_sku_infos[sku],
                    MSG_ORDER_COUNT: 0
                }
                response_info.append(info)

            return response_info

        except Exception as err_info:
            self.error("pack ship sku response msg: %s", err_info)
            return None

    def sku_valid(self, statistics_info):
        try:
            reported_sku = set(statistics_info[REPORTED_EPC][SKU_INFO].keys())
            un_reported_sku = set(statistics_info[UNREPORTED_EPC].keys())
            received_sku = list(reported_sku.union(un_reported_sku))

        except Exception as err_info:
            self.error("check sku validation failed: %s", err_info)
            return False

        for sku in received_sku:
            try:
                self.db.query(TSkuInfo).filter(TSkuInfo.sku == sku).one()
            except NoResultFound:
                self.debug("no sku[%s] info", sku)
                return False
            except MultipleResultsFound:
                self.debug("sku[%s] have multi records", sku)
            except Exception as err_info:
                self.error("check sku whether valid failed: %s", err_info)
                return False
        else:
            return True

    def query_ship_sku_info_in_order(self, ship_id):
        try:
            result = self.db.query(TShipOrderDetail).filter(TShipOrderDetail.ship_id == ship_id).all()

            sku = set()
            for order_detail in result:
                sku.add(order_detail.sku)

            return sku

        except Exception as err_info:
            self.error("query ship order detail info failed: %s", err_info)
            return None

    def fields_valid_check(self):
        try:
            if MSG_DEVICE_ID not in self.msg_info:
                return False, ResponseStatus.LACK_DEVICE_ID_FIELD

            if MSG_EPC_SYNC_TYPE not in self.msg_info:
                return False, ResponseStatus.LACK_EPC_SYNC_TYPE_FIELD

            if MSG_EPCS not in self.msg_info:
                return False, ResponseStatus.LACK_EPCS_FIELD

            return True, None

        except Exception as err_info:
            self.error("epc sync handler check fields valid failed: %s", err_info)
            return False, ResponseStatus.SYSTEM_ERROR

    def get_customer_id(self, cloth_epcs):
        for epc in cloth_epcs:
            try:

                result = self.db.query(TEpcDetail.epc, TSupplierInfo.supplier_name).join(
                    TSupplierInfo, TEpcDetail.supplier_id == TSupplierInfo.supplier_id
                ).filter(
                    TEpcDetail.epc == epc
                ).one()

                return result.supplier_name
            except Exception as err_info:
                self.error("get customer id failed: %s", err_info)
                continue
        else:
            return ""

    def update_order_info(self, box_id, statistics_info):
        """
        根据box_id 更新order信息

        :param box_id:
        :param statistics_info:
        :return:
        """
        try:
            case_orders = []
            extra_sku = set(statistics_info[EXTRA_SKU])
            for order in statistics_info[ORDER_INFO]:
                order_sku = set(statistics_info[ORDER_INFO][order])
                if len(extra_sku.intersection(order_sku)) == 0:
                    # 这个订单号里面没有非本订单的sku
                    case_orders.append(order)

            order_info = self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id
            ).one()

            if order_info.order_id is not None:
                already_add_orders = set(order_info.order_id.split(","))
            else:
                already_add_orders = set()
            if "" in already_add_orders:
                already_add_orders.remove("")

            for order in case_orders:
                already_add_orders.add(order)

            order_str = ",".join(already_add_orders)
            self.db.query(TReceiptBatchCase).filter(
                TReceiptBatchCase.case_id == box_id
            ).update({
                TReceiptBatchCase.order_id: order_str
            })

            return True

        except Exception as err_info:
            self.error("update order info failed: %s", err_info)
            return False

    def case_sku_confirmed(self, box_id, order_sku):
        try:
            result = self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                TReceiptBatchCaseSkuStatistic.case_id == box_id,
                TReceiptBatchCaseSkuStatistic.sku == order_sku
            ).one()

            if result.status >= ReceiptSkuState.TO_SYNC.value:
                return True
            else:
                return False

        except Exception as err_info:
            self.error("check case sku confirmed failed:%s", err_info)
            return True

    def record_receipt_scan_info(self, box_id, statistics_info, scan_state):
        try:
            success = self.record_receipt_scan_detail(statistics_info)
            if not success:
                return False

            success = self.record_receipt_scan_log(box_id, statistics_info, scan_state)
            if not success:
                return False

            return True

        except Exception as err_info:
            self.error("record receipt scan info failed:%s", err_info)
            return False

    def record_receipt_scan_log(self, box_id, statistics_info, scan_state):
        try:
            un_report_sku_info = {sku: len(statistics_info[UNREPORTED_EPC][sku])
                                  for sku in statistics_info[UNREPORTED_EPC]}
            reported_sku_info = {sku: len(statistics_info[REPORTED_EPC][SKU_INFO][sku])
                                 for sku in statistics_info[REPORTED_EPC][SKU_INFO]}

            received_sku_info = dict(Counter(un_report_sku_info) +
                                     Counter(reported_sku_info))

            for sku in received_sku_info:

                # 确认这个sku，属于哪些order
                order_info = []
                for order in statistics_info[ORDER_INFO]:
                    if sku in statistics_info[ORDER_INFO][order]:
                        order_info.append(order)

                success, ship_quantity = self.sku_ship_quantity_in_box(box_id, sku)
                if not success:
                    ship_quantity = 0

                scan_log = TReceiptScanLog()
                scan_log.trans_id = self.request_transid
                scan_log.sku = sku
                scan_log.order_id = ','.join(order_info)
                scan_log.case_id = box_id
                scan_log.received_quantity = received_sku_info[sku]
                scan_log.receive_date = datetime.now()
                scan_log.status = scan_state.value
                scan_log.ship_quantity = ship_quantity

                self.db.add(scan_log)

            if len(statistics_info[INVALID_EPC]) > 0:
                scan_log = TReceiptScanLog()
                scan_log.trans_id = self.request_transid
                scan_log.sku = "无效芯片"
                scan_log.order_id = ""
                scan_log.case_id = box_id
                scan_log.received_quantity = len(statistics_info[INVALID_EPC])
                scan_log.receive_date = datetime.now()
                scan_log.status = ReceiptScanState.TO_CONFIRM.value

                self.db.add(scan_log)

            return True

        except Exception as err_info:
            self.error("record receipt scan log failed:%s", err_info)
            return False

    def record_receipt_scan_detail(self, statistics_info):
        try:
            from itertools import chain
            for sku, epcs in chain(statistics_info[REPORTED_EPC][SKU_INFO].items(),
                                   statistics_info[UNREPORTED_EPC].items()):
                for epc in epcs:
                    scan_detail = TReceiptScanDetail()
                    scan_detail.trans_id = self.request_transid
                    scan_detail.epc = epc
                    scan_detail.sku = sku

                    self.db.add(scan_detail)

            return True

        except Exception as err_info:
            self.error("record receipt scan detail failed:%s", err_info)
            return False

    def move_receipt_detail_to_his(self, trans_id):
        """
        move 收货表信息到收货历史表

        :return:
        """
        try:
            self.info("move_receipt_detail_to_his by trans_id = %s", trans_id)
            # handle the detail
            result = self.db.query(TReceiptScanDetail.epc).filter(TReceiptScanDetail.trans_id == trans_id).all()
            epcs = []
            for one_record in result:
                epcs.append(one_record.epc)

            keys = inspect(TReceiptDetail).columns.keys()
            get_columns = lambda post: {key: getattr(post, key) for key in keys if key != "id"}

            detial_infos = self.db.query(TReceiptDetail).filter(TReceiptDetail.epc.in_(epcs))
            self.db.bulk_insert_mappings(TReceiptDetailHistory, (get_columns(detail_info) for detail_info in detial_infos))
            detial_infos.delete(synchronize_session='fetch')
            self.db.commit()
            return True

        except Exception as ex:
            self.error("move_receipt_detail_to_his catch exception ex=%s", ex)
            return False

    def check_if_done(self, case_id, sku):
        try:
            sku_info = self.db.query(TReceiptBatchCaseSkuStatistic).filter(
                TReceiptBatchCaseSkuStatistic.case_id == case_id,
                TReceiptBatchCaseSkuStatistic.sku == sku
            ).one()

            if sku_info.pre_receipt_quantity == sku_info.storage_quantity + sku_info.return_quantity:
                result = self.update_receipt_sku_state(case_id, sku, ReceiptSkuState.DONE_STATE)
                self.delete_no_pre_sku(case_id, sku)
                return result

            return True

        except Exception as err_info:
            self.error("check if done exception: %s", err_info)
            return False

    def delete_no_pre_sku(self, case_id, sku):
        try:
            self.db.query(TReceiptDetail).filter(
                TReceiptDetail.case_id == case_id,
                TReceiptDetail.sku == sku,
                TReceiptDetail.status == 0
            ).delete(synchronize_session='fetch')

            self.db.commit()
            self.info("delete success from t_receipt_detail table .....")
        except Exception as err:
            self.error("delete no pre sku Exception: err={}".format(err))

    def list_receipt_return_count(self, ecps, info):

        try:
            # 统计满足退货条件数量（1表示已退货）,不打断收货动作,只修改提示
            # 修改返回信息：存在X件返修服装
            # MK 2019-04-24
            # #-----------------------------------------------------------------------------------
            ss_epc = set(ecps)

            pre_receipted_count = self.db.query(TReceiptDetail).filter(
                TReceiptDetail.epc.in_(ss_epc),
                TReceiptDetail.status == ReceiptEpcState.PRE_RECEIPT.value).count()

            # 全是预收货商品，则正常收货
            if pre_receipted_count == len(ss_epc):
                return True

            # 退货的那个时间点到现在是否超过了31天，如果超过了，就直接反馈错误码2008，拒收这批货
            subqry = self.db.query(func.max(TReturnInfo.return_time).label('return_time'),
                                   TReturnInfo.epc.label('epc'))\
                .filter(TReturnInfo.epc.in_(ss_epc)).group_by(TReturnInfo.epc).subquery()

            ls_count = self.db.query(distinct(TReturnInfo.epc).label('epc')) \
                .join(subqry, and_(TReturnInfo.epc == subqry.c.epc,
                                   TReturnInfo.return_time == subqry.c.return_time))\
                .filter(TReturnInfo.return_status == ReturnEpcState.RETURN_AL.value).count()

            if ls_count > 0:
                info[MSG_STATUS_TEXT] = MSG_BACK.replace("X", str(ls_count))
            else:
                return True

            delay_count = self.db.query(distinct(TReturnInfo.epc).label('epc')) \
                .join(subqry, and_(TReturnInfo.epc == subqry.c.epc,
                      TReturnInfo.return_time == subqry.c.return_time))\
                .filter(func.datediff(func.now(), TReturnInfo.return_time) > RETURN_EXPIRED_DURATION,
                        TReturnInfo.return_status == ReturnEpcState.RETURN_AL.value).count()

            if delay_count > 0:
                return False

            return True
            # #-----------------------------------------------------------------------------------
        except Exception as err_info:
            self.error("list receipt return count Exception: err={}".format(err_info))
            return True
