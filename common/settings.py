# -*- coding: utf-8 -*-

import logging
import configparser

__author__ = 'Ennis'

try:
    # 将配置文件解析
    config = configparser.ConfigParser()
    config.read("common/settings.ini")

    log_level = int(config.get('default', 'LOG_LEVEL'))

    SERVER_PORT = int(config.get('default', 'SERVER_PORT'))

    IS_DEBUG = int(config.get('default', 'IS_DEBUG'))
    DB_CONNECT_STR = config.get('default', 'DB_CONNECT_STR')

    POST_RETRY_TIMES = int(config.get('default', 'POST_RETRY_TIMES'))
    POST_REQUEST_TIMEOUT = int(config.get('default', 'POST_REQUEST_TIMEOUT'))

    WMS_URL = config.get('default', 'WMS_URL')

    SCM_URL = config.get('default', 'SCM_URL')
    SCM_SIGN_STRING = config.get('default', 'SCM_SIGN_STRING')

    PORTAL_URL = config.get('default', 'PORTAL_URL')

    APP_KEY = config.get('default', 'APP_KEY')
    SESSION_KEY = config.get('default', 'SESSION_KEY')
    RECEIPT_INTERFACE = config.get('default', 'RECEIPT_INTERFACE')
    SHIP_COUNT_INTERFACE = config.get('default', 'SHIP_COUNT_INTERFACE')

    WMS_RETRY_INTERVAL = int(config.get('default', 'WMS_RETRY_INTERVAL'))

    RETURN_EXPIRED_DURATION = int(config.get('default', 'RETURN_EXPIRED_DURATION'))

except Exception as e:
    logging.error('parse config fail, error = {}'.format(e))
    exit(0)
