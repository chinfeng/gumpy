# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import multiprocessing.pool
import functools
import wsgiref.simple_server, wsgiref.util, wsgiref.validate
from gumpy.deco import service, configuration, bind, event

import logging
logger = logging.getLogger(__name__)

class ThreadPoolWSGIServer(wsgiref.simple_server.WSGIServer):
    def __init__(self, thread_count, *args, **kwds):
        wsgiref.simple_server.WSGIServer.__init__(self, *args, **kwds)
        self._pool = multiprocessing.pool.ThreadPool(thread_count)

    def process_request_worker(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except:
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def process_request(self, request, client_address):
        self._pool.apply_async(self.process_request_worker, args=(request, client_address))

    def serve_forever(self, *args, **kwds):
        self._pool.apply_async(wsgiref.simple_server.WSGIServer.serve_forever, args=(self, ) + args, kwds=kwds)

    def shutdown(self):
        super(self.__class__, self).shutdown()
        self._pool.terminate()

@service
class WSGIService(object):
    @configuration(rootapp='rootapp')
    def __init__(self, rootapp):
        self._apps = {}
        self._server = None
        self._rootapp = rootapp
        self.start_wsgi_server()

    @configuration(port=('port', 8001))
    def start_wsgi_server(self, port):
        try:
            sc = functools.partial(ThreadPoolWSGIServer, 20)
            self._server = wsgiref.simple_server.make_server(
                '', port, self._wsgi_app, server_class=sc
            )
            self._server.serve_forever()
        except BaseException as err:
            err.args = ('tserv start fails.', ) + err.args
            logger.exception(err)

    def on_stop(self):
        if self._server:
            self._server.shutdown()
        del self._server

    @bind('tserv.application')
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

    def _wsgi_app(self, environ, start_response):
        if self._apps:
            app_route = wsgiref.util.shift_path_info(environ)
            if app_route in self._apps:
                environ['SCRIPT_NAME'] = ''
                return self._apps[app_route](environ, start_response)
            elif self._rootapp:
                return self._apps[self._rootapp](environ, start_response)
        start_response('404 NOT FOUND', [('Content-type', 'text/plain'), ])
        return ['no application deployed'.encode('utf-8')]

    @event
    def on_configuration_changed(self, key, value):
        if key == 'port':
            ctx = self.__context__
            ctx.stop().add_done_callback(lambda rt, bdl=ctx: bdl.start())
        elif key == 'rootapp':
            self._rootapp = value
