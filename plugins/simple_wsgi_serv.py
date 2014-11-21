# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from wsgiref.simple_server import WSGIServer
from wsgiref.util import shift_path_info
from wsgiref import validate
import multiprocessing.pool

from gumpy.deco import *

import logging
logger = logging.getLogger(__name__)

class ThreadPoolWSGIServer(WSGIServer):
    def __init__(self, thread_count, *args, **kwds):
        super(self.__class__, self).__init__(*args, **kwds)
        self._thread_count = thread_count
        self._pool = multiprocessing.pool.ThreadPool(self._thread_count)

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except:
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def process_request(self, request, client_address):
        self._pool.apply_async(self.process_request_thread, args=(request, client_address))

    def serve_forever(self, *args, **kwds):
        self._pool.apply_async(super(self.__class__, self).serve_forever, args=args, kwds=kwds)

    def shutdown(self):
        super(self.__class__, self).shutdown()
        self._pool.terminate()

@service
class WSGIServer(object):
    def __init__(self):
        self.daemon = True
        self._apps = {}

    def on_start(self):
        try:
            self._conf = self.__context__.configuration
            self._port = self._conf.get('port', 8000)

            from wsgiref.simple_server import make_server
            self._httpd = make_server('', self._port, self._wsgi_app, server_class=functools.partial(ThreadPoolWSGIServer, 10))
            self._httpd.serve_forever()
        except BaseException as e:
            logger.error('simple_wsgi_serv httpd fails')
            logger.exception(e)

    def on_stop(self):
        if self._httpd:
            self._httpd.shutdown()
        del self._httpd

    @event
    def on_configuration_changed(self, key, value):
        if key == 'port':
            ctx = self.__context__
            ctx.stop().add_done_callback(lambda rt, bdl=ctx: bdl.start())

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

