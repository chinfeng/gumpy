# -*- coding: utf-8 -*-
__author__ = 'chinfeng'
__gum__ = 'auth'

from .auth import Server, Provider, ServerDaoWithStorage
from .endpoint import EndpointApplication
from .exception import RegisterError, InvalidTokenError, AuthorizationError
from gumpy.deco import service, provide, bind, require
from tornado.wsgi import WSGIAdapter

try:
    from httplib import responses
except ImportError:
    from http.client import responses
status = lambda code: '%d %s' % (code, responses[code])

@service
@provide('huacaya.auth.server')
class AuthServerService(Server):
    @bind('huacaya.storage', '1..1')
    def storage(self, s):
        self._dao = ServerDaoWithStorage(s)

    @storage.unbind
    def storage(self, s):
        del self._dao
        self._dao = None

@service
@provide('huacaya.auth.provider')
class AuthProviderService(Provider):
    @require(server='AuthServerService')
    def __init__(self, server):
        super(self.__class__, self).__init__(server)

@service
@provide('cserv.application')
class AuthEndpointApplication(object):
    __route__ = 'auth'

    def __init__(self):
        self._app = None

    def __call__(self, environ, start_response):
        if not self._app:
            self._app = WSGIAdapter(EndpointApplication(
                self._auth_server, self._auth_provider
            ))
        return self._app(environ, start_response)

    @bind('huacaya.auth.provider', '1..1')
    def auth_provider(self, provider):
        self._auth_provider = provider

    @bind('huacaya.auth.server', '1..1')
    def auth_server(self, server):
        self._auth_server = server