# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import service, provide

import tornado.web
import tornado.wsgi

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('Hello world!')

@service
@provide('tserv.application')
@provide('cserv.application')
class FirstApplication(tornado.wsgi.WSGIAdapter):
    __route__ = 'firstapp'

    def __init__(self):
        super(self.__class__, self).__init__(
            tornado.web.Application([
                (r'/?', MainHandler),
            ])
        )