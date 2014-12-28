# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode
try:
    from cookielib import CookieJar
except ImportError:
    from http.cookiejar import CookieJar
try:
    from urllib2 import build_opener, Request, HTTPError, HTTPCookieProcessor, HTTPErrorProcessor
except ImportError:
    from urllib.request import build_opener, Request, HTTPCookieProcessor, HTTPErrorProcessor
    from urllib.error import HTTPError

import json
import random
import unittest
import threading
from wsgiref.validate import validator
from wsgiref.simple_server import make_server

import logging
logger = logging.getLogger(__name__)

class NoRedirectionProcessor(HTTPErrorProcessor):
    def http_response(self, request, response):
        return response
    https_response = http_response

class WSGITestCase(unittest.TestCase):
    def __init__(self, *args, **kwds):
        unittest.TestCase.__init__(self, *args, **kwds)
        self._cookie_jar = CookieJar()
        app = self.get_app()
        validator(app)
        self._port = random.randint(50000, 60000)
        self._httpd = make_server('', self._port, app)
        self._serve_thread = threading.Thread(target=self._httpd.serve_forever)
        self._serve_thread.setDaemon(True)
        self._opener = build_opener(NoRedirectionProcessor, HTTPCookieProcessor(self._cookie_jar))

        self._cookies = {}

    def setUp(self):
        self._serve_thread.start()

    def tearDown(self):
        self._httpd.shutdown()
        self._serve_thread.join()

    def get_app(self):
        raise NotImplementedError

    def request(self, url, method=None, data=None, headers=None):
        headers = headers or {}
        method = method or 'GET'

        if isinstance(data, dict):
            for k, v in headers.items():
                if k.lower().startswith('content-type') and v.lower().startswith('application/json'):
                    data = json.dumps(data).encode('utf-8') if isinstance(data, dict) else data
                    method = 'POST'
                    break
            else:
                if method == 'GET':
                    headers = {}
                    url = '?'.join((url, urlencode(data)))
                    data = None
                else:
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    data = urlencode(data).encode('utf-8')

        request = Request('http://localhost:%d%s' % (self._port, url), data=data, headers=headers)
        if method.upper() not in ('GET', 'POST'):
            request.get_method = lambda m=method: m
        response = self._opener.open(request)

        try:
            # for py3
            charset = response.headers.get_param('charset')
        except AttributeError:
            # for py2
            charset = response.headers.getparam('charset')
        response.body = response.read().decode(charset)
        response.charset = charset
        if response.headers.get('content-type').startswith('application/json'):
            response.dct = json.loads(response.body)
        else:
            response.dct = {}
        response.status = '%d %s' % (response.code, response.msg)
        return response
