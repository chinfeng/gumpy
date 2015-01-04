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

from .auth import AuthorizationError

def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return str(obj)
    else:
        return obj

class BaseHandler(tornado.web.RequestHandler):
    def initialize(self, **kwds):
        self._auth_server = kwds.get('auth_server', None)
        self._auth_provider = kwds.get('auth_provider', None)
        self._current_user = None

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
        if not self._current_user:
            account_raw = self.get_secure_cookie('account', None)
            self._current_user = json_decode(account_raw) if account_raw else None
        return self._current_user

class RedirectBaseHandler(BaseHandler):
    def send_redirect(self, redirect_uri, args):
        self.clear()
        url_parts = list(urlsplit(redirect_uri))
        url_parts[3] = '&'.join((urlencode({k: v for k, v in args.items() if v is not None}), url_parts[3])).strip('&')
        self.redirect(urlunsplit(url_parts))

    def send_invalid_request_error(self, redirect_uri, state=None):
        self.send_redirect(redirect_uri, dict(
            state=state, error='invalid_request', error_description='The request is missing a required parameter.',
        ))

    def send_unsupported_response_type_error(self, redirect_uri, state=None):
        self.send_redirect(redirect_uri, dict(
            state=state, error='unsupported_response_type',
            error_description='The authorization server does not support obtaining an authorization code using this method.',
        ))

    def send_unauthorized_client_error(self, redirect_uri, state=None):
        self.send_redirect(redirect_uri, dict(
            state=state, error='unauthorized_client',
            error_description='The client is not authorized to request an authorization code using this method.',
        ))

    def send_access_denied_error(self, redirect_uri, state=None):
        self.send_redirect(redirect_uri, dict(
            state=state, error='access_denied',
            error_description='The resource owner or authorization server denied the request.',
        ))

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
        if self._auth_server.verify_scope(token, 'me'):
            account = self._auth_server.get_account_by_token(token)

            if account:
                account.pop('password', None)
                self.write(account)
            else:
                self.send_error(
                    500, error='server_error',
                    error_description='account not found',
                )
        else:
            self.set_header(
                'WWW-Authenticate',
                'Bearer realm="{0}", error="{1}"'.format(
                    'example', 'access_denied',
                )
            )
            self.send_error(401)

class SignInHandler(BaseHandler):
    __route__ = r'/signin'

    def post(self):
        account = self._auth_server.find_account(self.json_data)
        if account:
            del account['password']
        self.set_secure_cookie('account', json.dumps(account, default=json_default))
        self.write({'sign_in': 'success'})

class AuthorizeHandler(RedirectBaseHandler):
    __route__ = r'/authorize'
    __sign_in_endpoint__ = r'/signin.html'
    __auth_endpoint__ = r'/auth.html'
    __default_redirect__ = r'/default_callback'

    def get(self):
        # https://tools.ietf.org/html/rfc6749#section-4.1.1
        # https://tools.ietf.org/html/rfc6749#section-4.2.1
        # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数

        redirect_uri = self.get_argument('redirect_uri', None)
        response_type = self.get_argument('response_type', None)
        client_id = self.get_argument('client_id', None)
        scope = self.get_argument('scope', None)
        state = self.get_argument('state', None)

        if not (redirect_uri and response_type and client_id):
            self.send_invalid_request_error(redirect_uri or self.__default_redirect__, state)
        elif response_type not in ('code', 'token'):
            self.send_unsupported_response_type_error(redirect_uri, state)
        elif not self._auth_server.has_client_id(client_id):
            self.send_unauthorized_client_error(redirect_uri, state)
        else:
            self.send_redirect(self.__sign_in_endpoint__, dict(
                response_type=response_type, client_id=client_id,
                redirect_uri=redirect_uri, state=state, scope=scope,
            ))

    def post(self):
        # https://tools.ietf.org/html/rfc6749#section-4.1.1
        # https://tools.ietf.org/html/rfc6749#section-4.2.1
        # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数

        redirect_uri = self.get_argument('redirect_uri', None)
        response_type = self.get_argument('response_type', None)
        client_id = self.get_argument('client_id', None)
        state = self.get_argument('state', None)
        scope = self.get_argument('scope', None)
        agreed = self.get_argument('agreed', 0)
        account = self.get_current_user()

        if not (redirect_uri and response_type and client_id):
            self.send_invalid_request_error(redirect_uri or self.__default_redirect__, state)
        elif not agreed:
            self.send_access_denied_error(redirect_uri, state)
        if not (redirect_uri and response_type and client_id):
            self.send_invalid_request_error(redirect_uri, state)
        elif response_type == 'code':
            # https://tools.ietf.org/html/rfc6749#section-4.1.1
            # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数
            if self._auth_server.has_client_id(client_id):
                self.send_redirect(redirect_uri, dict(
                    state=state,
                    code=self._auth_provider.authorization_request(account['username'], client_id, redirect_uri, scope)
                ))
            else:
                self.send_unauthorized_client_error(redirect_uri, state)
        elif response_type == 'token':
            # https://tools.ietf.org/html/rfc6749#section-4.2.1
            # 暂无默认 redirect callback 机制，所以 redirect_uri 必要参数
            if self._auth_server.has_client_id(client_id):
                    access_token_data = self._auth_provider.implicit_grant(account['username'], client_id, redirect_uri, scope)
                    self.send_redirect(redirect_uri, dict(
                        state=state, expires_in=access_token_data['expires_in'],
                        token_type=access_token_data['token_type'], access_token=access_token_data['access_token'],
                    ))
            else:
                self.send_unauthorized_client_error(redirect_uri, state)
        else:
            self.send_unsupported_response_type_error(redirect_uri, state)

class GrantHandler(BaseHandler):
    __route__ = r'/grant'

    def post(self):
        grant_type = self.get_argument('grant_type', None)

        if grant_type == 'authorization_code':
            authorization_code = self.get_argument('code', None)
            client_id = self.get_argument('client_id', None)
            redirect_uri = self.get_argument('redirect_uri', None)

            try:
                self.write(
                    self._auth_provider.authorization_code_grant(
                        authorization_code, client_id, redirect_uri
                    )
                )
            except BaseException as err:
                self.send_error(400, **err.args[0])
        elif grant_type == 'refresh_token':
            # Refreshing an Access Token
            # https://tools.ietf.org/html/rfc6749#section-6
            try:
                self.write(
                    self._auth_provider.refresh_token_grant(self.get_argument('refresh_token', None))
                )
            except BaseException as err:
                self.send_error(400, **err.args[0])
        elif grant_type == 'password':
            username = self.get_argument('username', None)
            password = self.get_argument('password', None)
            scope = self.get_argument('scope', None)

            try:
                token_data = self._auth_server.password_grant(
                    username, {'username': username, 'password': password}, scope)
                self.write(token_data)
            except AuthorizationError:
                self.send_error(400, error='invalid_request')
        elif grant_type:
            self.send_error(
                400, error='unsupported_grant_type',
                error_description='The authorization grant type is not supported by the authorization server.',
            )

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
