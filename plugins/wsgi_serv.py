# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import threading
from wsgiref.util import shift_path_info
from wsgiref import validate
from gumpy.deco import *

import logging
logger = logging.getLogger(__name__)

@service
class WSGIServer(threading.Thread):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.daemon = True
        self._apps = {}
        self._server = None

    def run(self):
        try:
            from tornado.wsgi import WSGIContainer
            from tornado.httpserver import HTTPServer
            from tornado.ioloop import IOLoop
            container = WSGIContainer(self._wsgi_app)
            self._server = HTTPServer(container)
            self._server.listen(self._port)
            IOLoop.instance().start()
        except BaseException as e:
            logger.error('wsgi_serv httpd fail to start')
            logger.exception(e)

    def on_start(self):
        self._conf = self.__context__.configuration
        self._port = self._conf.get('port', 8888)
        self.start()

    def on_stop(self):
        from tornado.ioloop import IOLoop
        ioloop = IOLoop.instance()
        ioloop.add_callback(self._server.stop)
        ioloop.add_callback(ioloop.stop)

    @bind('wsgi.application')
    def wsgi_application(self, app):
        validate.validator(app)
        if hasattr(app, '__route__'):
            self._apps[app.__route__] = app
        else:
            self._apps[app.__class__.__name__] = app

    @wsgi_application.unbind
    def unbind_wsgi_application(self, app):
        if hasattr(app, '__route__'):
            del self._apps[app.__route__]
        else:
            del self._apps[app.__class__.__name__]

    def _wsgi_app(self, environ, start_response):
        if self._apps:
            app_route = shift_path_info(environ)
            if app_route in self._apps:
                environ['SCRIPT_NAME'] = ''
                return self._apps[app_route](environ, start_response)
        start_response('404 NOT FOUND', [('Content-type', 'text/plain'), ])
        return ['no application deployed'.encode('utf-8')]