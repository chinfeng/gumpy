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
    from urllib2 import build_opener, Request, HTTPError, HTTPCookieProcessor
except ImportError:
    from urllib.request import build_opener, Request, HTTPCookieProcessor
    from urllib.error import HTTPError

import json
import random
import unittest
import threading
from wsgiref.validate import validator
from wsgiref.simple_server import make_server

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

        self._cookies = {}

    def setUp(self):
        self._serve_thread.start()

    def tearDown(self):
        self._httpd.shutdown()
        self._serve_thread.join()

    def get_app(self):
        raise NotImplementedError

    def request(self, url, method='GET', data=None, headers=None):
        headers = headers or {}
        data = json.dumps(data).encode('utf-8') if isinstance(data, dict) else data
        opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
        request = Request('http://localhost:%d%s' % (self._port, url), data=data, headers=headers)
        if method.upper() not in ('GET', 'POST'):
            request.get_method = lambda m=method: m
        try:
            response = opener.open(request)
            charset = response.headers.get_charset() or 'UTF-8'
            response.dct = json.loads(response.read().decode(charset))
        except HTTPError as err:
            response = err
            response.dct = {}
        response.status = '%d %s' % (response.code, response.msg)
        return response
