# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import uuid
import json
import datetime
import tornado.web
from tornado.web import HTTPError
from tornado.escape import json_decode
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
    def prepare(self):
        if all((
            self.request.method.upper() != 'GET',
            self.request.headers.get('content-type').startswith('application/json'),
        )):
            self.json_data = json_decode(self.request.body)
        else:
            self.json_data = None
    def get_argument(self, name, default=None, strip=True):
        if self.json_data:
            arg = self.json_data.get(name, default)
            return arg.strip() if strip and isinstance(arg, str) else arg
        else:
            return tornado.web.RequestHandler.get_argument(self, name, default, strip)
    def write_error(self, status_code, **kwds):
        try:
            self.write(kwds)
        except TypeError:
            tornado.web.RequestHandler.write_error(self, status_code, **kwds)
    def get_current_user(self):
        account_raw = self.get_secure_cookie('account', None)
        return json_decode(account_raw) if account_raw else None

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

class SignInHandler(BaseHandler):
    __route__ = r'/signin'

    def post(self):
        account = self._auth_server.find_account(self.json_data)
        if account:
            del account['password']
        self.set_secure_cookie('account', json.dumps(account, default=json_default))
        self.write({'sign_in': 'success'})

class AuthorizeHandler(BaseHandler):
    __route__ = r'/authorize'
    __sign_in_endpoint__ = r'/signin.html'
    __auth_endpoint__ = r'/auth.html'
    __default_redirect__ = r'/default_callback'

    def get(self):
        response_type = self.get_argument('response_type', None)
        redirect_uri = self.get_argument('redirect_uri', None)

        if response_type == 'code' or response_type == 'token':
            # https://tools.ietf.org/html/rfc6749#section-4.1.1
            # https://tools.ietf.org/html/rfc6749#section-4.2.1
            # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数
            client_id = self.get_argument('client_id', None)
            if client_id and redirect_uri:
                if self._auth_server.has_client_id(client_id):
                    dest_uri = self.__sign_in_endpoint__
                    dct = {
                        'response_type': response_type,
                        'client_id': client_id,
                        'redirect_uri': redirect_uri,
                    }
                else:
                    dct = {'error': 'unauthorized_client'}
            else:
                dct = {'error': 'invalid_request'}
        elif response_type:
            dct = {'error': 'unsupported_response_type'}
        else:
            dct = {'error': 'invalid_request'}

        state = self.get_argument('state', None)
        if state:
            dct['state'] = state

        dest_uri = (redirect_uri or self.__default_redirect__) if 'error' in dct else dest_uri
        url_parts = list(urlsplit(dest_uri))
        url_parts[3] = '&'.join((url_parts[3], urlencode(dct)))
        self.redirect(urlunsplit(url_parts))

    def post(self):
        response_type = self.get_argument('response_type', '').lower()
        redirect_uri = self.get_argument('redirect_uri', None)
        agreed = self.get_argument('agreed', 0)

        if not agreed:
            dct = {'error': 'access_denied'}
        elif response_type == 'code':
            # https://tools.ietf.org/html/rfc6749#section-4.1.1
            # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数
            client_id = self.get_argument('client_id', None)
            if client_id and redirect_uri:
                if self._auth_server.has_client_id(client_id):
                    account_id = self.get_current_user()['account_id']
                    dct = {
                        'code': self._auth_provider.authorization_request(client_id, account_id, redirect_uri)
                    }
                else:
                    dct = {'error': 'unauthorized_client'}
            else:
                dct = {'error': 'invalid_request'}
        elif response_type == 'token':
            # https://tools.ietf.org/html/rfc6749#section-4.2.1
            # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数
            client_id = self.get_argument('client_id', None)
            if client_id and redirect_uri:
                if self._auth_server.has_client_id(client_id):
                    account_id = self.get_current_user()['account_id']
                    access_token_data = self._auth_provider.implicit_grant(client_id, account_id, redirect_uri)
                    dct = {
                        'access_token': access_token_data['access_token'],
                        'expires_in': access_token_data['expires_in'],
                        'token_type': access_token_data['token_type'],
                    }
                else:
                    dct = {'error': 'unauthorized_client'}
            else:
                dct = {'error': 'invalid_request'}
        else:
            dct = {'error': 'unsupported_response_type'}

        state = self.get_argument('state', None)
        if state:
            dct['state'] = state

        url_parts = list(urlsplit(redirect_uri))
        url_parts[3] = '&'.join((url_parts[3], urlencode(dct)))
        self.redirect(urlunsplit(url_parts))


class GrantHandler(BaseHandler):
    __route__ = r'/grant'

    def post(self):
        grant_type = self.get_argument('grant_type', None)
        if grant_type == 'authorization_code':
            code = self.get_argument('code', None)
            if code:
                try:
                    self.write(
                        self._auth_provider.authorization_grant(
                            code, self.get_argument('redirect_uri', None)
                        )
                    )
                except AuthorizationError:
                    self.send_error(400, error='invalid_grant')
            else:
                self.send_error(400, error='invalid_grant')
        elif grant_type == 'refresh_token':
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
        elif grant_type == 'password':
            try:
                account = self._auth_server.password_grant({
                    'username': self.get_argument('username'),
                    'password': self. get_argument('password'),
                })
                self.write(account)
            except AuthorizationError:
                self.send_error(400, error='invalid_request')
        elif grant_type:
            self.send_error(400, error='unsupported_grant_type')

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
            RevokeTokenHandler, AccountListHandler, TokenListHandler, ClientListHandler, SignInHandler,
        ]

        for handler in handlers:
            yield (handler.__route__, handler, kwds)

        static_path = os.path.join(os.path.dirname(__file__), 'static')
        yield (r'/(.*)', tornado.web.StaticFileHandler, dict(path=static_path))
