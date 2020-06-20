# !/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
from urllib.parse import urlencode

from models.models import TWmsSyncLog, TReceiptScanLog
from common.dbutils import db_session
from tornado.gen import coroutine
from common.http_request import http_client_request
from common.settings import WMS_URL
import uuid
import json
from common.receipt_ship_state import ReceiptScanState

__author__ = "jxh"


@coroutine
def retry_sync_wms():
    trans_id = str(uuid.uuid1()).replace("-", "")
    try:
        db = db_session
        sync_failed_logs = db.query(TWmsSyncLog).filter(TWmsSyncLog.status == 0).all()
        for sync_failed_log in sync_failed_logs:
            logging.info("retry send wms msg: %s", sync_failed_log.req_body)
            param = json.loads(sync_failed_log.req_body)
            url = WMS_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, {}, {"request_transid": trans_id})
            if success:
                db.query(TWmsSyncLog).filter(TWmsSyncLog.id == sync_failed_log.id).update(
                    {
                        TWmsSyncLog.status: 1,
                        TWmsSyncLog.res_body: body
                    }
                )
                db.query(TReceiptScanLog).filter(TReceiptScanLog.trans_id == sync_failed_log.trans_id).update({
                    TReceiptScanLog.status: ReceiptScanState.SYNC_SUCCESS.value
                })
                db.commit()

    except Exception as err_info:
        logging.error("retry sync wms exception:%s", err_info)
        db.rollback()
