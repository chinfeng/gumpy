# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import uuid
import json
import datetime
import tornado.web

def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return str(obj)
    else:
        return obj

class BaseHandler(tornado.web.RequestHandler):
    def initialize(self, **kwds):
        self._auth_server = kwds.get('auth_server', None)
        self._auth_provider = kwds.get('auth_provider', None)

class MainHandler(BaseHandler):
    def get(self):
        self.redirect('/auth/index.html')

class SignUpHandler(BaseHandler):
    def post(self):
        data = json.loads(self.request.body)
        userid = self._auth_server.register_account(data)
        self.write(dict(userid=userid))

class AuthorizeHandler(BaseHandler):
    def post(self):
        data = json.loads(self.request.body)
        client_id = data['client_id'].encode('utf-8')
        authorization_code = self._auth_provider.authorization_request(client_id)
        if authorization_code:
            self.write(dict(code=authorization_code))
        else:
            self.send_error(403)

class GrantHandler(BaseHandler):
    def post(self):
        data = json.loads(self.request.body)
        code = data['code'].encode('utf-8')
        try:
            at, rt = self._auth_provider.authorization_grant(code, data['credentials'])
            self.write(dict(
                access_token=at, refresh_token=rt
            ))
        except:
            self.send_error(403)

class RevokeTokenHandler(BaseHandler):
    """ TODO: demonstration without any permission check for now """
    def post(self):
        data = json.loads(self.request.body)
        token = data.get('token').encode('utf-8')
        self._auth_server.revoke_token(token)
        self.write({})

class AccountInfoHandler(BaseHandler):
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

class RefreshGrantHandler(BaseHandler):
    def post(self):
        data = json.loads(self.request.body)
        refresh_token = data.get('refresh_token').encode('utf-8')
        try:
            access_token = self._auth_provider.refresh_grant(refresh_token)
            self.write(dict(access_token=access_token))
        except:
            self.send_error(401)

class AccountListHandler(BaseHandler):
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_accounts())))
        else:
            self.send_error(403)

class TokenListHandler(BaseHandler):
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_tokens()), default=json_default))
        else:
            self.send_error(403)

class ClientListHandler(BaseHandler):
    def get(self):
        """ # TODO: demonstration with simple access control fornow """
        if self.request.remote_ip == '127.0.0.1':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(list(self._auth_server.get_clients())))
        else:
            self.send_error(403)


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
            (r'/?', MainHandler),
            (r'/signup', SignUpHandler),
            (r'/authorize', AuthorizeHandler),
            (r'/grant', GrantHandler),
            (r'/me', AccountInfoHandler),
            (r'/revoke', RevokeTokenHandler),
            (r'/refresh', RefreshGrantHandler),
            (r'/accounts', AccountListHandler),
            (r'/tokens', TokenListHandler),
            (r'/clients', ClientListHandler),
        ]

        for handler in handlers:
            yield (handler[0], handler[1], kwds)

        static_path = os.path.join(os.path.dirname(__file__), 'static')
        yield (r'/(.*)', tornado.web.StaticFileHandler, dict(path=static_path))
