# !/usr/bin/python3
# -*- coding: utf-8 -*-

from enum import Enum, unique
import sys

__author__ = "jxh"


@unique
class EpcScene(Enum):
    RECEIPT_SINGLE_SKU = 0                  # 有箱标，并且只包含一种SKU
    RECEIPT_MULTI_SKU = 1                   # 订单有多个sku
    SIMPLE_COUNT = 5                        # 简单清点
    SHIP = 6                                # 批量发货
    LIST_COUNT = 7                          # 工单清点
    RETURN = 8                              # 退货  2019-04-24 MK 增加退货类型
    UNKNOWN_SCENE = sys.maxsize
