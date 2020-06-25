# -*- coding: utf-8 -*-
import logging
import logging.handlers
import os
import sys
import asyncio

import tornado.httpserver
import tornado.web
# noinspection PyUnresolvedReferences
from tornado import ioloop
from tornado.ioloop import PeriodicCallback

from common.settings import SERVER_PORT, log_level, WMS_RETRY_INTERVAL
from serv.urls import app_handlers
from common.dbutils import check_db
from common.custom_log_handler import FileFormatter
from common.base_handler import TMBaseReqHandler
from common.retry_sync_wms import retry_sync_wms

__author__ = 'Ennis'


# noinspection PyUnresolvedReferences
def init_rfid_server():
    """
    初始化设置WebSocket Server的参数
    :return:
    """
    try:
        # 装载url配置
        # noinspection PyUnresolvedReferences
        app = tornado.web.Application(
            handlers=app_handlers
        )

        # 配置server
        api_server = tornado.httpserver.HTTPServer(app)
        api_server.listen(SERVER_PORT)
        logging.info("start Server at: %d", SERVER_PORT)
        sync_retry = PeriodicCallback(retry_sync_wms, WMS_RETRY_INTERVAL * 1000)
        sync_retry.start()

        TMBaseReqHandler.load_transaction_data()
    except Exception as e:
        logging.error('Exception: %s', e)


def init_logging():
    """
    日志文件设置
    """
    logger = logging.getLogger()
    logger.setLevel(log_level)
    if os.path.exists('./log') is False:
        os.mkdir('./log')

    sh = logging.StreamHandler()
    file_log = logging.handlers.TimedRotatingFileHandler('log/rfid_server.log', 'midnight', 1, 7)
    formatter = FileFormatter('[%(asctime)s] [%(levelname)-8s] %(message)s')
    sh.setFormatter(formatter)
    file_log.setFormatter(formatter)

    logger.addHandler(sh)
    logger.addHandler(file_log)

    logging.info("Current log level is : %s", logging.getLevelName(logger.getEffectiveLevel()))


if __name__ == '__main__':
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        # 日志初始化
        init_logging()

        # 检查数据库连接
        # if check_db() is False:
        #     exit()

        # 初始化Server
        init_rfid_server()

        ioloop.IOLoop.instance().start()

    except Exception as err:
        log_str = 'rfid server start fail! err = %s' % err

        logging.fatal(log_str)
        print(log_str)
