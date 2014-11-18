# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from wsgiref.util import FileWrapper
from gumpy.deco import *
import os
import threading
import json
import argparse
import mimetypes

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

import logging
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--path',
                    dest='plugins_path', default='plugins',
                    help='plugins directory')
_plugins_path = parser.parse_args().plugins_path
_config_path = os.path.join(_plugins_path, 'config.ini')

def _repo(framework):
    rt = []
    for fn in os.listdir(_plugins_path):
        fp = os.path.join(_plugins_path, fn)
        bn, ext = os.path.splitext(fn)
        uri = fn
        if bn[:2] == '__':
            continue
        if os.path.isdir(fp) and bn[0] != '.':
            tp = '[PKG]'
        elif ext == '.zip':
            tp = '[ZIP]'
        elif ext == '.py':
            tp = '[MOD]'
            uri = bn
        else:
            continue

        for bdl in framework.bundles.values():
            if bdl.uri == uri:
                st = '[%s]' % bdl.state[1]
                break
        else:
            st = ''

        rt.append(dict(uri=uri, type=tp, state=st))
    return rt

def _list(framework):
    rt = []
    for bdl in framework.bundles.values():
        rt.append(dict(
            name=bdl.name,
            state=bdl.state[1],
            uri=bdl.uri
        ))
    return rt

class WSGIApplication(object):
    def __init__(self, framework):
        self._framework = framework

    def __call__(self, environ, start_response):
        try:
            path = environ['PATH_INFO']
            bn, ext = os.path.splitext(path)
            if not path or path == '/':
                abs_path = os.path.join(os.path.dirname(__file__), 'index.html')
                start_response('200 OK', [('content-type', 'text/html'), ])
                with open(abs_path, 'rb') as fd:
                    for chunk in FileWrapper(fd):
                        yield chunk
            elif ext in mimetypes.types_map:
                abs_path = os.path.dirname(__file__) + path.replace('/', os.path.sep)
                with open(abs_path, 'rb') as fd:
                    headers = [('content-type', mimetypes.types_map[ext])]
                    start_response('200 OK', headers)
                    for chunk in FileWrapper(fd):
                        yield chunk
            else:
                path = (environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '')).split('/')
                action = path[1]
                params = json.loads(environ['wsgi.input'].read(int(environ['CONTENT_LENGTH'])).decode('utf-8') if environ['CONTENT_LENGTH'] else '{}', encoding='UTF-8')
                if action == 'repo':
                    rt = _repo(self._framework)
                elif action == 'list':
                    rt = _list(self._framework)
                elif action == 'install' and environ["REQUEST_METHOD"].lower() == 'post':
                    _f = self._framework.install_bundle(params['uri'])
                    _f.add_done_callback(lambda rt: self._framework.save_state())
                    rt = dict(install_result=u'ok')
                elif action == 'start' and environ["REQUEST_METHOD"].lower() == 'post':
                    _f = self._framework.bundles[params['name']].start()
                    _f.add_done_callback(lambda rt: self._framework.save_state())
                    rt = dict(start_result=u'ok')
                elif action == 'stop' and environ["REQUEST_METHOD"].lower() == 'post':
                    _f = self._framework.bundles[params['name']].stop()
                    _f.add_done_callback(lambda rt: self._framework.save_state())
                    rt = dict(start_result=u'ok')
                else:
                    start_response('404 NOT FOUND', [('Content-type', 'text/plain'), ])
                    yield '404: Not Found'.encode('utf-8')
                    return
                self._framework.wait_until_idle()
                start_response('200 OK', [('Content-type', 'application/json'), ])
                yield json.dumps(rt, indent=4).encode('utf-8')
        except FileNotFoundError:
            start_response('404 NOT FOUND', [('Content-type', 'text/plain'), ])
            yield '404: Not Found'.encode('utf-8')
        except BaseException as err:
            start_response('500 INTERNAL SERVER ERROR', [('Content-type', 'text/plain'), ])
            yield err.args[0].encode('utf-8')

@service
class WebConsoleServer(threading.Thread):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.daemon = True
        self._apps = {}
        self._httpd = None

    def run(self):
        try:
            from wsgiref.simple_server import make_server
            self._httpd = make_server('', 3040, WSGIApplication(self.__framework__))
            self._httpd.serve_forever()
        except BaseException as e:
            logger.error('simple_wsgi_serv httpd fail to start')
            logger.exception(e)

    def on_start(self):
        self.start()

    def on_stop(self):
        if self._httpd:
            self._httpd.shutdown()
