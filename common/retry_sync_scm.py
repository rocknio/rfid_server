# !/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
from urllib.parse import urlencode

from models.models import TScmSyncLog, TReceiptScanLog
from common.dbutils import db_session
from tornado.gen import coroutine
from common.http_request import http_client_request
from common.settings import SCM_URL
import uuid
import json
from common.receipt_ship_state import ReceiptScanState

__author__ = "Neo"


@coroutine
def retry_sync_scm():
    trans_id = str(uuid.uuid1()).replace("-", "")
    try:
        db = db_session
        sync_failed_logs = db.query(TScmSyncLog).filter(TScmSyncLog.status == 0).all()
        for sync_failed_log in sync_failed_logs:
            logging.info("retry send scm msg: %s", sync_failed_log.req_body)
            param = json.loads(sync_failed_log.url_params)
            sync_msg = json.loads(sync_failed_log.req_body)
            url = SCM_URL + "?" + urlencode(param)
            success, body = yield http_client_request(url, sync_msg, {"request_transid": trans_id})
            if success:
                db.query(TScmSyncLog).filter(TScmSyncLog.id == sync_failed_log.id).update(
                    {
                        TScmSyncLog.status: 1,
                        TScmSyncLog.res_body: body
                    }
                )
                db.commit()

    except Exception as err_info:
        logging.error("retry sync scm exception:%s", err_info)
        db.rollback()
