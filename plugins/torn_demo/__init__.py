# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import *

import logging
logger = logging.getLogger(__name__)

import tornado.web
import tornado.wsgi

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('demo web bundle using tornado')

@service
@provide('wsgi.application')
class DemoApplication(tornado.wsgi.WSGIAdapter):
    __route__ = 'torn'

    def __init__(self):
        super(self.__class__, self).__init__(
            tornado.web.Application([
                (r'/?', MainHandler),
            ])
        )