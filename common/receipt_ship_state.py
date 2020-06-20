# !/usr/bin/python3
# -*- coding: utf-8 -*-

from enum import Enum, unique

__author__ = "jxh"


@unique
class ReceiptOrderState(Enum):
    INIT_STATE = 0
    RECEIPTING_STATE = 1
    DONE_STATE = 2
    CANCEL_STATE = 3


@unique
class ReceiptCaseState(Enum):
    INIT_STATE = 0
    RECEIPTING_STATE = 1
    DONE_STATE = 2
    CANCEL_STATE = 3


@unique
class ReceiptSkuState(Enum):
    INIT_STATE = 0
    CANCEL_STATE = 1
    TO_CONFIRM = 2
    TO_CHECK = 3
    DONE_STATE = 4


@unique
class ReceiptScanState(Enum):
    """
    1表示需要把多个sku的箱子拆开
    2表示数量不一致需要确认
    3表示预收货了，需要质检
    4表示同步到wms同步失败了
    """
    TO_UNPACK = 1
    TO_CONFIRM = 2
    TO_CHECK = 3
    SYNC_FAILED = 4
    SYNC_SUCCESS = 5


@unique
class ReceiptEpcState(Enum):
    SCANNED = 0
    PRE_RECEIPT = 1
    CHECKED = 2

# MK 2019-04-24 预退货状态
@unique
class ReturnEpcState(Enum):
    PRE_RETURN = 1
    RETURN_AL = 2


@unique
class ShipOrderState(Enum):
    INIT_STATE = 0
    SHIPPING_STATE = 1
    DONE_STATE = 2
