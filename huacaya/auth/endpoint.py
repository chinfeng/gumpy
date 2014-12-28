# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import uuid
import json
import datetime
import tornado.web
try:
    from urllib import urlencode
    from urlparse import urlsplit, urlunsplit
except ImportError:
    from urllib.parse import urlencode, urlsplit, urlunsplit

import logging
logger = logging.getLogger(__name__)

from .auth import AuthorizationError, InvalidTokenError

def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return str(obj)
    else:
        return obj

class BaseHandler(tornado.web.RequestHandler):
    def initialize(self, **kwds):
        self._auth_server = kwds.get('auth_server', None)
        self._auth_provider = kwds.get('auth_provider', None)
    def write_error(self, status_code, **kwds):
        self.write(kwds)

class MainHandler(BaseHandler):
    __route__ = r'/?'
    def get(self):
        self.redirect('/auth/index.html')

class SignUpHandler(BaseHandler):
    __route__ = r'/signup'
    def post(self):
        data = json.loads(self.request.body.decode('utf-8'))
        account_id = self._auth_server.register_account(data)
        self.write(dict(account_id=account_id))

class RevokeTokenHandler(BaseHandler):
    """ TODO: demonstration without any permission check for now """
    __route__ = r'/revoke'
    def post(self):
        data = json.loads(self.request.body.decode('utf-8'))
        token = data.get('token')
        self._auth_server.revoke_token(token)
        self.write({})

class AccountListHandler(BaseHandler):
    __route__ = r'/accounts'
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_accounts())))
        else:
            self.send_error(403)

class TokenListHandler(BaseHandler):
    __route__ = r'/tokens'
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_tokens()), default=json_default))
        else:
            self.send_error(403)

class ClientListHandler(BaseHandler):
    __route__ = r'/clients'
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_clients())))
        else:
            self.send_error(403)

class AccountInfoHandler(BaseHandler):
    __route__ = r'/me'
    def _get_access_token(self):
        bearer_str = self.request.headers.get('Authorization', None)
        if bearer_str:
            if bearer_str.startswith('Bearer '):
                return bearer_str[7:]

        access_token = self.get_argument('access_token', None)
        access_token = access_token or self.get_secure_cookie('access_token', None)
        return access_token

    def get(self):
        token = self._get_access_token()
        if self._auth_server.verify_token(token):
            account = self._auth_server.get_account_by_token(token)

            if account:
                if 'password' in account:
                    account.pop('password')
                self.write(account)
            else:
                self.send_error(500)
        else:
            self.send_error(401)

class AuthorizeHandler(BaseHandler):
    __route__ = r'/authorize'
    __default_redirect_uri__ = '/auth/default_callback'

    def get(self):
        # Authorization Request
        # https://tools.ietf.org/html/rfc6749#section-4.1.1
        response_type = self.get_argument('response_type', '').lower()
        state = self.get_argument('state', None)
        client_id = self.get_argument('client_id', None)
        redirect_uri = self.get_argument('redirect_uri', None)
        if not all((response_type, client_id, response_type == 'code', redirect_uri)):
            dct = {'error': 'invalid_request'}
        elif not self._auth_server.has_client_id(client_id):
            dct = {'error': 'unauthorized_client'}
        else:
            code = self._auth_provider.authorization_request(client_id, redirect_uri)
            if code:
                dct = {'code': code, 'redirect_uri': redirect_uri}
            else:
                dct = {'error': 'access_denied'}
        if state:
            dct['state'] = state

        url_parts = list(urlsplit(redirect_uri or self.__default_redirect_uri__))
        url_parts[3] = '&'.join((url_parts[3], urlencode(dct)))
        self.redirect(urlunsplit(url_parts))

class GrantHandler(BaseHandler):
    __route__ = r'/grant'

    def post(self):
        grant_type = self.get_argument('grant_type', '')
        if grant_type.lower() == 'authorization_code':
            # Access Token Request
            # https://tools.ietf.org/html/rfc6749#section-4.1.3
            code = self.get_argument('code', None)
            if code:
                credentials = {
                    'username': self.get_argument('username', None),
                    'password': self.get_argument('password', None),
                }
                try:
                    self.write(
                        self._auth_provider.authorization_grant(
                            code, credentials, self.get_argument('redirect_uri', None)
                        )
                    )
                except AuthorizationError:
                    self.send_error(400, error='invalid_grant')
            else:
                self.send_error(400, error='invalid_grant')
        elif grant_type.lower() == 'refresh_token':
            # Refreshing an Access Token
            # https://tools.ietf.org/html/rfc6749#section-6
            try:
                self.set_header('Content-Type', 'application/json; charset=utf-8')
                self.write(json.dumps(
                    self._auth_provider.refresh_grant(self.get_argument('refresh_token', None)),
                    default=json_default,
                ))
            except InvalidTokenError:
                self.send_error(400, error='invalid_grant')
        else:
            self.send_error(400, error='invalid_request')

class EndpointApplication(tornado.web.Application):
    def __init__(self, auth_server, auth_provider):
        self._auth_server = auth_server
        self._auth_provider = auth_provider
        super(self.__class__, self).__init__(
            self.get_handlers(auth_server=auth_server, auth_provider=auth_provider),
            cookie_secret=uuid.uuid4().hex
        )

    def get_handlers(self, **kwds):
        handlers = [
            MainHandler, SignUpHandler, AuthorizeHandler, GrantHandler, AccountInfoHandler,
            RevokeTokenHandler, AccountListHandler, TokenListHandler, ClientListHandler,
        ]

        for handler in handlers:
            yield (handler.__route__, handler, kwds)

        static_path = os.path.join(os.path.dirname(__file__), 'static')
        yield (r'/(.*)', tornado.web.StaticFileHandler, dict(path=static_path))
