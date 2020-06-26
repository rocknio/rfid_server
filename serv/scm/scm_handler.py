# -*- coding: utf-8 -*-

from datetime import datetime

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from tornado.gen import coroutine
import tornado

from common.msg_field import *
from common.receipt_ship_state import *
from models.models import *
import logging
import json
import base64
from common.dbutils import db_session

__author__ = 'Neo'


class ScmHandler(tornado.web.RequestHandler):
    """
    scm成衣入库回传
    """
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.db = db_session

    @coroutine
    def post(self):
        try:
            query_args = self.request.query_arguments
            msg_info = json.loads(self.request.body)
            logging.info("Recv post query_args = {}, body = {}".format(query_args, msg_info))

            if msg_info.get('transid') is None:
                self.write({
                    "msg": "没有transid",
                    "success": False
                })
                self.finish()
                return

            yield self.update_purchase_code(msg_info)

        except Exception as err_info:
            self.error("handle scm failed: %s", err_info)
            self.write({
                    "msg": "{}".format(err_info),
                    "success": False
                })
            self.finish()

    @coroutine
    def update_purchase_code(self, msg_info):
        try:
            wsm_sync_req_record = self.db.query(TWmsSyncLog.req_body).filter(TWmsSyncLog.trans_id == msg_info['transid']).one()
            wsm_sync_req = json.loads(wsm_sync_req_record.req_body)
            content = base64.b64decode(wsm_sync_req['content']).decode()
            items = json.loads(content)
            logging.info("TransId = {}, Content = {}".format(msg_info['transid'], items))

            epcs = []
            for one_item in items:
                tmp = [no['no'] for no in one_item['items']]
                epcs.extend(tmp)

            logging.info("t_wms_sync_logs all epcs = {}".format(epcs))

            try:
                for one_item in msg_info['items']:
                    qty = one_item['actual_qty']
                    purchase_code = one_item['purchase_order_code']
                    for _ in range(qty):
                        one_epc = epcs.pop(0)
                        self.db.query(TEpcDetail).filter(TEpcDetail.epc == one_epc).update({TEpcDetail.order_id: purchase_code})
                    logging.info("update t_epc_detail done! qty = {}, order_id = {}".format(qty, purchase_code))
            except Exception as err_info:
                # 只记录日志，可能部分成功，也作为成功处理
                logging.error('update t_epc_detail failed! err = {}'.format(err_info))

            self.db.commit()
            self.write({"msg": "成功", "success": True})
            self.finish()

        except Exception as err_info:
            logging.error("update_purchase_code failed, req = {}, err = {}".format(msg_info, err_info))
            self.db.commit()
            self.write({"msg": "{}".format(err_info), "success": False})
            self.finish()

