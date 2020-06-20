# !/usr/bin/python3
# -*- coding: utf-8 -*-

import logging

__author__ = "jxh"


class FileFormatter(logging.Formatter):
    """
    文件日志格式化记录
    
    """
    def format(self, record):
        try:
            # Standard document
            request_transid = record.__dict__.get("request_transid", None)
            old_msg = record.msg
            record.msg = "[%s]:" % request_transid + record.msg
            result = super().format(record)
            record.msg = old_msg
            return result

        except Exception as err_info:
            print("file formatter failed: %s" % err_info)
            return ""
