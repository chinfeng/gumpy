# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

try:
    from StringIO import StringIO
except:
    from io import StringIO
import re
import json
import unittest
from wsgiref.util import setup_testing_defaults
from wsgiref.headers import Headers
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

class _Response(object):
    def __init__(self):
        self.status = None
        self.started = False
        self.headers = None
        self.data = bytes()
        self._dct = None
        self.charset = 'utf-8'

    @property
    def dct(self):
        if not self._dct:
            try:
                charset = re.match(
                    '.*charset=(.*)$',
                    self.headers.get_all('content-type')[0]
                ).group(1)
                self._dct = json.loads(self.data.decode(charset))
            except:
                self._dct = {}
        return self._dct

    def write(self, chunk):
        self.data += chunk


class WSGITestCase(unittest.TestCase):
    def __init__(self, *args, **kwds):
        unittest.TestCase.__init__(self, *args, **kwds)
        self.cookies = []

    def request(self, app, url, method='GET',
                content_type='json', data='', cookies=None, headers=None):
        response = _Response()
        if isinstance(data, dict):
            if method == 'GET':
                url = '?'.join((url, urlencode(data)))
                data = ''
                content_type = ''
            elif content_type in ('application/json', 'json'):
                content_type = 'application/json'
                data = json.dumps(data)
            elif content_type in ('application/x-www-form-urlencoded', 'form'):
                content_type = 'application/x-www-form-urlencoded'
                data = urlencode(data)
        data_io = StringIO(data)
        method = 'POST' if data and method == 'GET' else method
        environ = {
            'PATH_INFO': url,
            'REQUEST_METHOD': method,
            'CONTENT_TYPE': content_type,
            'CONTENT_LENGTH': len(data) if data else 0,
            'wsgi.input': data_io,
        }
        for k, v in headers or []:
            environ['HTTP_{0}'.format(k)] = v
        setup_testing_defaults(environ)
        if self.cookies:
            environ['HTTP_COOKIE'] = ';'.join(self.cookies)

        start_response = lambda status, header, _resp=response: self._start_response(_resp, status, header)
        for ret in app(environ, start_response):
            assert response.started
            response.write(ret)
        data_io.close()
        return response

    def _start_response(self, response, status, headers):
        assert not response.started
        response.started = True
        response.status = status
        for header in headers:
            if header[0] == 'Set-Cookie':
                v = header[1].split(';', 1)
                if len(v) > 1 and v[1].startswith(' Max-Age='):
                    if int(v[1][9:]) > 0:
                        self.cookies.append(v[0])
                    else:
                        index = self.cookies.index(v[0])
                        self.cookies.pop(index)
        response.headers = Headers(headers)

    def clear_cookies(self):
        self.cookies = []

