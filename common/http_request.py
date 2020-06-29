# !/usr/bin/python3
# -*- coding: utf-8 -*-

import json
import logging

import tornado
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from common.settings import POST_RETRY_TIMES, POST_REQUEST_TIMEOUT

__author__ = "jxh"


@gen.coroutine
def http_client_request(url, msg, log_trans, method='POST'):
    """
    异步发送消息到业务层,并重试，重试后仍失败，返回false
    :param url: 门户接口url
    :param msg: dict类型http body
    :param log_trans: 此次投递时的trans_id
    :param method: http 方法
    """
    header, body = {}, ""
    try:
        logging.info('<<<<< post msg to url[%s]: %s', url, msg, extra=log_trans)
        if not isinstance(msg, str):
            body = json.dumps(msg)

        headers = {"Content-Type": "application/json"}
        client = tornado.httpclient.AsyncHTTPClient()

        retry_time = 0
        while retry_time < POST_RETRY_TIMES:
            try:
                response = yield client.fetch(url, method=method, headers=headers, body=body, request_timeout=POST_REQUEST_TIMEOUT)
                logging.info('time[%d] response code: %d, response body:%s', retry_time+1,
                             response.code, response.body, extra=log_trans)

                # 对端返回200或者500，表示对端已收到，如果处理失败就不再重发
                if response.code == 200 or response.code == 500:
                    break
                else:
                    retry_time += 1
            except Exception as err_info:
                logging.error('time[%d] post! err = %s', retry_time+1, err_info, extra=log_trans)
                retry_time += 1
        else:
            return False, None

        return True, response.body

    except Exception as err_info:
        logging.error('notify server with err = %s', err_info, extra=log_trans)
        return False, None
