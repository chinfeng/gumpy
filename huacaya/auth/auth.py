# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import datetime
import re
from uuid import uuid4
from base64 import b32encode
from .exception import RegisterError, AuthorizationError
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

rndgen = lambda: b32encode(uuid4().bytes).decode('ascii').strip('=')

class Provider(object):
    def __init__(self, server):
        self._server = server

    def authorization_request(self, account_ident, client_id, redirect_uri=None, scope=None):
        return self._server.authorization_request(account_ident, client_id, redirect_uri, scope)

    def verify_authorization_code(self, authorization_code):
        return self._server.verify_authorization_code(authorization_code)

    def authorization_code_grant(self, authorization_code, client_id, redirect_uri=None):
        return self._server.authorization_code_grant(authorization_code, client_id, redirect_uri)

    def verify_token(self, token):
        return self._server.verify_token(token)

    def verify_scope(self, access_token, scope):
        return self._server.verify_scope(access_token, scope)

    def refresh_token_grant(self, refresh_token):
        return self._server.refresh_token_grant(refresh_token)

    def implicit_grant(self, account_ident, client_id, redirect_uri=None, scope=None):
        return self._server.implicit_grant(account_ident, client_id, redirect_uri, scope)

    def password_grant(self, account_ident, credentials, scope=None):
        return self._server.password_grant(account_ident, credentials, scope)

class Server(object):
    def __init__(self, dao=None):
        self._dao = dao

    def register_client(self, client_id, **kwds):
        if self._dao.has_client_id(client_id):
            raise RegisterError('client_id have been registered.')
        else:
            client_data = kwds.copy()
            client_data['client_id'] = client_id
            self._dao.insert_client(client_data)

    def register_account(self, account):
        identity = account.get('username', None)
        if self._dao.has_username(identity):
            raise RegisterError('username had been registered')
        else:
            uid = self._dao.insert_account(account)
            return uid

    def authorization_request(self, account_ident, client_id, redirect_uri=None, scope=None):
        if self._dao.has_client_id(client_id):
            authorization_code_data = {
                'code': rndgen(),
                'issue_time': datetime.datetime.utcnow(),
                'expires_in': 300,
                'disabled': False,
                'account_ident': account_ident,
                'redirect_uri': redirect_uri,
                'client_id': client_id,
                'scope': scope,
            }
            self._dao.insert_authorization_code(authorization_code_data)
            return authorization_code_data['code']
        else:
            raise AuthorizationError(dict(
                error='unauthorized_client',
                error_description='The client is not authorized to request an authorization code using this method.',
            ))

    def authorization_code_grant(self, authorization_code, client_id=None, redirect_uri=None):
        if self.verify_authorization_code(authorization_code):
            authorization_code_data = self._dao.get_authorization_code(authorization_code)
            client_valid = client_id == authorization_code_data['client_id']
            redirect_valid = self._redirect_uri_identical(authorization_code_data['redirect_uri'], redirect_uri)
            if not client_valid:
                raise AuthorizationError(dict(
                    error='invalid_client',
                    error_description='no client authentication included',
                ))
            if not redirect_valid:
                raise AuthorizationError(dict(
                    error='invalid_grant',
                    error_description='The provided authorization grant ' +
                                      'does not match the redirection URI used in the authorization request',
                ))
            refresh_token = rndgen()
            refresh_token_data = {
                'grant_type': 'authorization_code',
                'issue_time': datetime.datetime.utcnow(),
                'refresh_token': refresh_token,
                'account_ident': authorization_code_data['account_ident'],
                'associated_authorization_code': authorization_code,
                'scope': authorization_code_data['scope'],
                'disabled': False,
            }
            self._dao.insert_token(refresh_token_data)
            access_token_data = self.refresh_token_grant(refresh_token)
            # bearer token for now
            return {
                'token_type': 'bearer',
                'access_token': access_token_data['access_token'],
                'expires_in': access_token_data['expires_in'],
                'refresh_token': refresh_token,
            }
        else:
            raise AuthorizationError(dict(
                error='invalid_grant',
                error_description='invalid authorization code',
            ))

    def verify_authorization_code(self, authorization_code):
        if self._dao.has_authorization_code(authorization_code):
            authorization_code_data = self._dao.get_authorization_code(authorization_code)
            sec = (datetime.datetime.utcnow() - authorization_code_data['issue_time']).seconds
            if (not authorization_code_data['disabled']) and sec <= authorization_code_data['expires_in']:
                return True
        return False

    def verify_token(self, token):
        if self._dao.has_token(token):
            return not self._dao.get_token(token).get('disabled', False)
        return False

    def verify_scope(self, access_token, scope):
        token_data = self._dao.get_token(access_token)
        if token_data:
            grant_scope_set = set(re.split(',|\s', token_data.get('scope', None) or ''))
            scope_set = set(re.split(', ', scope or ''))
            return scope_set.issubset(grant_scope_set)
        else:
            return False

    def refresh_token_grant(self, refresh_token):
        if isinstance(refresh_token, dict):
            refresh_token_data = refresh_token
        else:
            refresh_token_data = self._dao.get_token(refresh_token)
        if refresh_token_data and not refresh_token_data.get('disabled', False):
            access_token = rndgen()
            access_token_data = {
                'grant_type': 'refresh_token',
                'issue_time': datetime.datetime.utcnow(),
                'access_token': access_token,
                'account_ident': refresh_token_data['account_ident'],
                'scope': refresh_token_data['scope'],
                'expires_in': 86400,
                'associated_refresh_token': refresh_token,
                'disabled': False,
            }
            self._dao.insert_token(access_token_data)
            return {
                'token_type': 'bearer',
                'access_token': access_token,
                'expires_in': access_token_data['expires_in'],
                'refresh_token': refresh_token,
            }
        else:
            raise AuthorizationError(dict(
                error='invalid_grant',
                error_description='invalid refresh token',
            ))

    def implicit_grant(self, account_ident, client_id, redirect_uri=None, scope=None):
        if self._dao.has_client_id(client_id):
            access_token = rndgen()
            access_token_data = {
                'grant_type': 'implicit',
                'issue_time': datetime.datetime.utcnow(),
                'access_token': access_token,
                'account_ident': account_ident,
                'expires_in': 86400,
                'disabled': False,
                'redirect_uri': redirect_uri,
                'scope': scope,
            }
            self._dao.insert_token(access_token_data)
            return {
                'token_type': 'bearer',
                'access_token': access_token,
                'expires_in': access_token_data['expires_in'],
            }
        else:
            raise AuthorizationError(dict(
                error='invalid_client',
                error_description='The client is not authorized to request an access token using this method.',
            ))

    def password_grant(self, account_ident, credentials, scope=None):
        account = self._dao.find_account(credentials)
        if account:
            refresh_token = rndgen()
            refresh_token_data = {
                'grant_type': 'authorization_code',
                'issue_time': datetime.datetime.utcnow(),
                'refresh_token': refresh_token,
                'account_ident': account_ident,
                'scope': scope,
                'disabled': False,
            }
            self._dao.insert_token(refresh_token_data)
            access_token_data = self.refresh_token_grant(refresh_token)
            # bearer token for now
            return {
                'token_type': 'bearer',
                'access_token': access_token_data['access_token'],
                'expires_in': access_token_data['expires_in'],
                'refresh_token': refresh_token,
            }
        else:
            raise AuthorizationError(dict(
                error='invalid_grant',
                error_description='Resource owner credentials is invalid.',
            ))

    def revoke_authorization_code(self, authorization_code):
        self._dao.update_authorization_code(authorization_code, dict(disabled=True))

    def revoke_token(self, token):
        self._dao.update_token(token, dict(disabled=True))

    def _redirect_uri_identical(self, auth_redirect_uri, acc_redirect_url):
        # TODO 鉴别两个 redirect_uri 是否同一个所有者
        # https://tools.ietf.org/html/rfc6749#section-4.1.3
        # 目前仅作简单处理，access_token 请求为同域名即可通过
        auth_loc = urlparse(auth_redirect_uri or '')
        acc_loc = urlparse(acc_redirect_url or '')
        return auth_loc.netloc == acc_loc.netloc

    def has_client_id(self, client_id):
        return self._dao.has_client_id(client_id)

    def get_accounts(self):
        return self._dao.get_accounts()

    def get_tokens(self):
        return self._dao.get_tokens()

    def get_clients(self):
        return self._dao.get_clients()

    def find_account(self, credentials):
        return self._dao.find_account(credentials)

    def get_account_by_token(self, token):
        return self._dao.find_account_by_token(token)

class ServerDaoWithStorage(object):
    def __init__(self, storage):
        self._storage = storage

    @property
    def _clients(self):
        return self._storage.get_bucket('auth.clients')

    @property
    def _tokens(self):
        return self._storage.get_bucket('auth.tokens')

    @property
    def _accounts(self):
        return self._storage.get_bucket('auth.accounts')

    @property
    def _codes(self):
        return self._storage.get_bucket('auth.codes')

    def has_client_id(self, client_id):
        return client_id in self._clients

    def insert_client(self, client_data):
        self._clients.put_object(client_data.get('client_id'), client_data)

    def has_username(self, username):
        account = self._accounts.find_one(dict(username=username))
        return bool(account)

    def insert_account(self, account):
        account_id = rndgen()
        account['account_id'] = account_id
        self._accounts.put_object(account['username'], account)
        return account_id

    def has_authorization_code(self, authorization_code):
        return authorization_code in self._codes

    def insert_authorization_code(self, authorization_code):
        self._codes.put_object(authorization_code['code'], authorization_code)

    def has_token(self, token):
        return token in self._tokens

    def find_account_by_token(self, token):
        account_id = self._tokens.get_object(token).get('account_ident')
        return self._accounts.get_object(account_id)

    def find_account(self, data):
        for account_id in self._accounts:
            if set(data.items()).issubset(self._accounts[account_id].items()):
                return self._accounts[account_id]
        return None

    def get_account_by_id(self, account_id):
        return self._accounts.get_object(account_id)

    def update_token(self, token, param):
        token_data = self._tokens.get_object(token)
        token_data.update(param)
        self._tokens.put_object(token, token_data)

    def get_authorization_code(self, authorization_code):
        return self._codes.get_object(authorization_code) if authorization_code in self._codes else None

    def update_authorization_code(self, authorization_code, param):
        code_data = self._codes.get_object(authorization_code)
        code_data.update(param)
        self._codes.put_object(authorization_code, code_data)

    def insert_token(self, token_data):
        token = token_data.get('refresh_token', None)
        token = token or token_data.get('access_token', None)
        self._tokens.put_object(token, token_data)

    def get_token(self, token):
        return self._tokens.get_object(token) if token in self._tokens else None

    def get_accounts(self):
        for account_id in self._accounts:
            account = self._accounts.get_object(account_id)
            if 'password' in account: account.pop('password')
            yield account

    def get_tokens(self):
        for token in self._tokens:
            yield self._tokens.get_object(token)

    def get_clients(self):
        for client_id in self._clients:
            yield self._clients.get_object(client_id)