# !/usr/bin/python3
# -*- coding: utf-8 -*-

from enum import Enum, unique

__author__ = "jxh"

MSG_TRANS_ID = "transid"
MSG_STATUS = 'result'
MSG_STATUS_TEXT = "desc"

MSG_DEVICE_ID = 'deviceid'
MSG_EPC_SYNC_TYPE = "type"
MSG_EPCS = "epcs"
MSG_CUSTOMER_ID = "customercode"

MSG_CONFIRM_TYPE = 'type'
MSG_DELIVER_NORMAL = 'NORMAL'
MSG_DELIVER_UNNORMAL = 'UNNORMAL'

BOX_EPC_PREIX = "B"
CLOTH_EPC_PREFIX = "C"

MSG_RECV_TYPE = 'RECV'
MSG_SEND_TYPE = 'SEND'

MSG_BOX_NO = "boxno"
MSG_SKUS = "skus"
MSG_SKU_NO = "no"
MSG_ORDER_COUNT = "ordercount"
MSG_RECV_COUNT = "actualcount"
MSG_INVALID_SKU = "invalid_sku"

MSG_ORDER_NO = "orderCode"
MSG_QUANTITY = "quantity"
MSG_OPER_TIME = "opertime"
MSG_TASK_NO = "taskno"
MSG_TASKS = "tasks"
MSG_ORDER_TYPE = "type"
MSG_OPERATOR = "operator"
MSG_PARAM = "param"
MSG_TASK_DESC = "desc"
MSG_TASK_CREATE_TIME = "createtime"

URL_APPKEY_PARAM = "appkey"
URL_SERVICE_PARAM = "service"
URL_SECRET_PARAM = "secret"
URL_FORMAT_PARAM = "format"
URL_CONTENT_PARAM = "content"

URL_ORDER_CODE = "orderCode"
URL_BOX_ID = "baco"
URL_SKU = "sku"
URL_QTY = "qty"
URL_ITEMS = "items"
URL_EPC = "no"
URL_TYPE = "type"
URL_SQTY = "sqty"

MSG_BODY = "body"
MSG_SUCCESS = "isSuccess"
MSG_TS = "ts"


@unique
class ResponseStatus(Enum):
    SUCCESS = "0000"
    LACK_TRANSID_FIELD = "0001"
    LACK_DEVICE_ID_FIELD = "0002"
    LACK_EPC_SYNC_TYPE_FIELD = "0003"
    LACK_EPCS_FIELD = "0004"
    LACK_CONFIRM_TYPE = "0005"
    WRONG_EPC_SYNC_TYPE = "0006"
    WRONG_CONFIRM_TYPE = "0007"
    LACK_ORDER_CODE_FIELD = "0008"
    LACK_ORDER_SYNC_TYPE = "0009"
    LACK_ITEMS_FIELD = "0010"
    LACK_SKU_FIELD = "0011"
    LACK_SQTY_FIELD = "0012"
    WRONG_ORDER_SYNC_TYPE = "0013"
    LACK_TASK_NO_FIELD = "0014"
    NO_BOX_ID = "1001"
    INVALID_BOX_ID = "1002"
    MULTI_BOX_ID = "1003"
    CLOTH_BELONG_OTHER_BOX = "2001"
    SKU_NOT_SAME = "2002"
    CLOTH_ALREADY_COMMITTED = "2003"
    INVALID_EPC = "2004"
    EXTRA_SKU = "2005"
    INVALID_SKU = "2006"
    NEED_INSPECT = "2007"
    TRANSACTION_NOT_EXISTED = "3001"
    ORDER_EXISTED = "3002"
    INVALID_TASKNO = "3003"
    TASK_NOT_STARTED = "3004"
    DEVICE_BUSY = "3005"
    TASK_ALREADY_STARTED = "3006"
    TRANSACTION_CONFIRMED = "3007"
    SYSTEM_ERROR = "9999"
    RETURN_DELAY = "2008" # 返修衣服超过一个月



response_desc = {
    ResponseStatus.SUCCESS: "成功",
    ResponseStatus.LACK_TRANSID_FIELD: "缺少事务号字段",
    ResponseStatus.LACK_DEVICE_ID_FIELD: "缺少设备ID字段",
    ResponseStatus.LACK_EPC_SYNC_TYPE_FIELD: "缺少标签同步类型字段",
    ResponseStatus.LACK_EPCS_FIELD: "缺少标签字段",
    ResponseStatus.LACK_CONFIRM_TYPE: "缺少确认操作类型字段",
    ResponseStatus.WRONG_EPC_SYNC_TYPE: "错误的标签同步类型",
    ResponseStatus.WRONG_CONFIRM_TYPE: "错误的确认操作类型",
    ResponseStatus.LACK_ORDER_CODE_FIELD: "缺少订单号",
    ResponseStatus.LACK_ORDER_SYNC_TYPE: "缺少订单同步类型",
    ResponseStatus.LACK_ITEMS_FIELD: "缺少items字段",
    ResponseStatus.LACK_SKU_FIELD: "缺少sku字段",
    ResponseStatus.LACK_SQTY_FIELD: "缺少剩余数量字段",
    ResponseStatus.WRONG_ORDER_SYNC_TYPE: "错误订单同步类型",
    ResponseStatus.LACK_TASK_NO_FIELD: "缺少taskno字段",
    ResponseStatus.NO_BOX_ID: "箱标缺失",
    ResponseStatus.INVALID_BOX_ID: "无效的箱标",
    ResponseStatus.MULTI_BOX_ID: "多个箱标",
    ResponseStatus.CLOTH_BELONG_OTHER_BOX: "衣服不属于这个箱子",
    ResponseStatus.CLOTH_ALREADY_COMMITTED: "衣服已经提交",
    ResponseStatus.SKU_NOT_SAME: "拆箱情况，上报了多个sku数据",
    ResponseStatus.INVALID_EPC: "无效的epc数据",
    ResponseStatus.EXTRA_SKU: "额外的sku",
    ResponseStatus.INVALID_SKU: "无效的sku",
    ResponseStatus.NEED_INSPECT: "存在非“预退货”状态的衣服",
    ResponseStatus.TRANSACTION_NOT_EXISTED: "不存在的事务号",
    ResponseStatus.ORDER_EXISTED: "订单号已存在",
    ResponseStatus.INVALID_TASKNO: "非法的任务号",
    ResponseStatus.DEVICE_BUSY: "正在执行其他任务",
    ResponseStatus.TASK_NOT_STARTED: "任务未开始",
    ResponseStatus.TASK_ALREADY_STARTED: "任务已经开始",
    ResponseStatus.TRANSACTION_CONFIRMED: "事务已确认",
    ResponseStatus.SYSTEM_ERROR: "系统运行异常",
    ResponseStatus.RETURN_DELAY: "存在超过一个月的返修衣服"
}


@unique
class EpcState(Enum):
    UN_REPORTED = 0      # 未上报过
    UN_COMMITTED = 1      # 上报过但未提交
    COMMITTED = 2         # 已经提交过
    UN_INIT = 3           # 没有初始化


@unique
class EpcSyncType(Enum):
    RECEIPT = "RECV"            # 收货上报标签
    SHIP = "SEND"               # 发货上报标签
    COUNT = "COUNT"             # 简单清单
    LISTCOUNT = "LISTCOUNT"     # 工单清点
    RETURN = "RETURN"           # 退货发运


@unique
class ConfirmType(Enum):
    NORMAL = "NORMAL"       # 正常情况下确认操作
    UN_NORMAL = "UNNORMAL"  # 差额验货确认操作


@unique
class OrderSyncStrType(Enum):
    SHIP_ORDER = "01"
    COUNT_ORDER = "02"


@unique
class OrderSyncDBType(Enum):
    SHIP_ORDER = 0
    COUNT_ORDER = 1


@unique
class RETURNNUM(Enum):
    ZERO = 0
    ONE = 1


wms_order_type = {
    OrderSyncDBType.SHIP_ORDER.value: "batchsend",
    OrderSyncDBType.COUNT_ORDER.value: "listcount"
}

SKU_INFO = "sku_info"
REPORTED_EPC = "reported"
UNREPORTED_EPC = "unreported"
INVALID_EPC = "invalid"
BOX_ID = "box_id"
COMMITTED_EPC = "committed"
ORDER_INFO = "order_info"
EXTRA_SKU = "extra_sku"
# 2019-04-24 增加操作 MK
MSG_BACK = "存在X件返修服装"
RETURN_EPC = "return_epc"
TRACK_NO = "trackno"
ECP_RET_FAIL = "X退货写入失败"


