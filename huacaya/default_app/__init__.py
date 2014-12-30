# -*- coding: utf-8 -*-
__author__ = 'chinfeng'
__gum__ = 'default_app'

import os
import mimetypes
from gumpy.deco import service, provide
from util import HTTP_STATUS
try:
    from urllib import url2pathname
except ImportError:
    from urllib.request import url2pathname

@service
@provide('cserv.default.application')
class StaticApplication(object):
    def __call__(self, environ, start_response):
        filepath = os.path.dirname(__file__) + url2pathname(environ['SCRIPT_NAME'] + environ['PATH_INFO'])
        bn, ext = os.path.splitext(filepath)
        try:
            with open(filepath, 'rb') as fd:
                if ext in mimetypes.types_map:
                    start_response(HTTP_STATUS(200), [('Content-Type', mimetypes.types_map[ext]), ])
                else:
                    start_response(HTTP_STATUS(200), [('Content-Type', 'application/octet-stream'), ])
                return [fd.read(), ]
        except (OSError, IOError):
            start_response(HTTP_STATUS(404), [('Content-Type', 'text/plain'), ])
            return ['File not found'.encode('utf-8')]
