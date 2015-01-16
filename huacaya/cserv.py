# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import functools
import threading
import wsgiref.simple_server, wsgiref.util, wsgiref.validate
from gumpy.deco import service, configuration, bind, event
from util import HTTP_STATUS

import logging
logger = logging.getLogger(__name__)

class TaskPoolWSGIServer(wsgiref.simple_server.WSGIServer):
    def __init__(self, executor, *args, **kwds):
        wsgiref.simple_server.WSGIServer.__init__(self, *args, **kwds)
        self._executor = executor

    def process_request_coroutine(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except:
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def process_request(self, request, client_address):
        self._executor.call(functools.partial(self.process_request_coroutine, request, client_address))

@service
class WSGIService(object):
    def __init__(self):
        self._apps = {}
        self._server = None
        self._default_app = None
        self.start_wsgi_server()

    @configuration(port=('port', 8002))
    def start_wsgi_server(self, port):
        try:
            sc = functools.partial(TaskPoolWSGIServer, self.__executor__)
            self._server = wsgiref.simple_server.make_server(
                '', port, self._wsgi_app, server_class=sc
            )

            t = threading.Thread(target=self._server.serve_forever)
            t.setDaemon(True)
            t.start()
        except BaseException as err:
            err.args = ('tserv start fails.', ) + err.args
            logger.exception(err)

    def on_stop(self):
        if self._server:
            self._server.shutdown()
        del self._server

    @bind('cserv.application')
    def application(self, app):
        wsgiref.validate.validator(app)
        if hasattr(app, '__route__'):
            self._apps[app.__route__] = app
        else:
            self._apps[app.__class__.__name__] = app

    @application.unbind
    def application(self, app):
        if hasattr(app, '__route__'):
            del self._apps[app.__route__]
        else:
            del self._apps[app.__class__.__name__]

    @bind('cserv.default.application', '0..1')
    def default_application(self, app):
        wsgiref.validate.validator(app)
        self._default_app = app

    @default_application.unbind
    def application_default(self, app):
        self._default_app = None

    def _wsgi_app(self, environ, start_response):
        if self._apps:
            app_route = wsgiref.util.shift_path_info(environ)
            if app_route in self._apps:
                environ['SCRIPT_NAME'] = ''
                return self._apps[app_route](environ, start_response)
            elif self._default_app:
                return self._default_app(environ, start_response)
        start_response(HTTP_STATUS(404), [('Content-Type', 'text/plain'), ])
        return ['no application deployed'.encode('utf-8')]

    @event
    def on_configuration_changed(self, key, value):
        if key == 'port':
            ctx = self.__context__
            ctx.stop().add_done_callback(lambda rt, bdl=ctx: bdl.start())
