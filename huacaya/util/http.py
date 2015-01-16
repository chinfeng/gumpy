# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

try:
    from httplib import responses
except ImportError:
    from http.client import responses

HTTP_STATUS = lambda code: '%d %s' % (code, responses[code])
