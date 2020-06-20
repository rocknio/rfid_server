# -*- coding: utf-8 -*-
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from common.settings import DB_CONNECT_STR, IS_DEBUG
import  pymysql

__author__ = 'Ennis'

# tornado单线程，只需要一个数据库链接即可
engine = create_engine(DB_CONNECT_STR, pool_recycle=3600, echo=IS_DEBUG, isolation_level='READ_UNCOMMITTED')

db_session = scoped_session(sessionmaker(bind=engine))


def check_db():
    # pymysql.install_as_MySQLdb()
    """
    检查数据库连接是否可用
    :return:
    """
    try:
        global db_session
        db_session.connection()
        return True
    except Exception as err:
        logging.fatal("db error = {}".format(err))
        return False
