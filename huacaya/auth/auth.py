# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import uuid
import datetime
from .exception import RegisterError, InvalidTokenError, AuthorizationError

class Provider(object):
    def __init__(self, server):
        self._server = server

    def authorization_request(self, client_id):
        return self._server.authorization_request(client_id)

    def authorization_grant(self, authorization_code, credentials):
        return self._server.authorization_grant(authorization_code, credentials)

    def refresh_grant(self, token):
        return self._server.refresh_grant(token)

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

    def verify_token(self, token):
        if self._dao.has_token(token):
            return self._dao.get_token(token).get('active', False)
        return False

    def get_account_by_token(self, token):
        return self._dao.find_account_by_token(token)

    def revoke_token(self, token):
        self._dao.update_token(token, dict(active=False))

    def verify_authorization_code(self, code):
        if self._dao.has_authorization_code(code):
            authorization_code_data = self._dao.get_authorization_code(code)
            sec = (datetime.datetime.now() - authorization_code_data['generated_time']).seconds
            if authorization_code_data['active'] and sec <= authorization_code_data['expires_in']:
                return True
        return False

    def revoke_authorization_code(self, authorization_code):
        self._dao.update_authorization_code(authorization_code, dict(active=False))

    def authorization_request(self, client_id):
        if self._dao.has_client_id(client_id):
            authorization_code_data = {
                'code': uuid.uuid4().hex,
                'generated_time': datetime.datetime.now(),
                'expires_in': 300, 'active': True,
            }
            self._dao.insert_authorization_code(authorization_code_data)
            return authorization_code_data['code']
        else:
            return None

    def authorization_grant(self, authorization_code, credentials):
        if self.verify_authorization_code(authorization_code):
            account = self._dao.find_account(credentials)
            if account:
                refresh_token = uuid.uuid4().hex
                refresh_token_data = {
                    'generated_time': datetime.datetime.now(),
                    'refresh_token': refresh_token,
                    'userid': account['userid'],
                    'active': True,
                }
                self._dao.insert_token(refresh_token_data)
                access_token = self.refresh_grant(refresh_token)
                return access_token, refresh_token
            else:
                raise AuthorizationError('invalid user credentials')
        else:
            raise AuthorizationError('invalid authorization code')

    def refresh_grant(self, refresh_token):
        refresh_token_data = self._dao.get_token(refresh_token)
        if refresh_token_data and refresh_token_data.get('active', False):
            access_token = uuid.uuid4().hex
            access_token_data = {
                'generated_time': datetime.datetime.now(),
                'access_token': access_token,
                'userid': refresh_token_data['userid'],
                'expires_in': 86400,
                'active': True,
            }
            self._dao.insert_token(access_token_data)
            return access_token
        else:
            raise InvalidTokenError('invalid refresh token {0}'.format(refresh_token))

    def get_accounts(self):
        return self._dao.get_accounts()

    def get_tokens(self):
        return self._dao.get_tokens()

    def get_clients(self):
        return self._dao.get_clients()

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
        userid = uuid.uuid4().hex
        account['userid'] = userid
        self._accounts.put_object(userid, account)
        return userid

    def has_authorization_code(self, authorization_code):
        return authorization_code in self._codes

    def insert_authorization_code(self, authorization_code):
        self._codes.put_object(authorization_code['code'], authorization_code)

    def has_token(self, token):
        return token in self._tokens

    def find_account_by_token(self, token):
        userid = self._tokens.get_object_content(token).get('userid')
        return self._accounts.get_object_content(userid)

    def find_account(self, data):
        for userid in self._accounts:
            if set(data.items()).issubset(self._accounts[userid].items()):
                return self._accounts[userid]
        return None

    def update_token(self, token, param):
        token_data = self._tokens.get_object_content(token)
        token_data.update(param)
        self._tokens.put_object(token, token_data)

    def get_authorization_code(self, authorization_code):
        return self._codes.get_object_content(authorization_code)

    def update_authorization_code(self, authorization_code, param):
        metadata, code_data = self._codes.get_object(authorization_code)
        code_data.update(param)
        self._codes.put_object(authorization_code, code_data, metadata)

    def insert_token(self, token_data):
        token = token_data.get('refresh_token', None)
        token = token or token_data.get('access_token', None)
        self._tokens.put_object(token, token_data)

    def get_token(self, token):
        return self._tokens.get_object_content(token)

    def get_accounts(self):
        for userid in self._accounts:
            account = self._accounts.get_object_content(userid)
            if 'password' in account: account.pop('password')
            yield account

    def get_tokens(self):
        for token in self._tokens:
            yield self._tokens.get_object_content(token)

    def get_clients(self):
        for client_id in self._clients:
            yield self._clients.get_object_content(client_id)