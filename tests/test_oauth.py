# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import random
import uuid
try:
    from urlparse import urlparse, parse_qs
except ImportError:
    from urllib.parse import urlparse, parse_qs
from tests.wsgi import WSGITestCase

class OAuthTestCase(WSGITestCase):
    def setUp(self):
        from huacaya.storage import mock
        from huacaya.auth import Server, Provider, ServerDaoWithStorage

        self._storage = mock.Storage()
        serv_dao = ServerDaoWithStorage(self._storage)
        self._serv = Server(serv_dao)
        self._provider = Provider(self._serv)

    def test_oauth_native(self):
        """ OAuth interface native test """
        from huacaya.auth import RegisterError, InvalidTokenError, AuthorizationError

        serv, provider = self._serv, self._provider
        client_id = uuid.uuid4().hex
        username = uuid.uuid4().hex
        password = uuid.uuid4().hex

        # test user and client register
        serv.register_client(client_id)
        serv.register_account({'username': username, 'password': password})
        with self.assertRaises(RegisterError):
            serv.register_client(client_id)
        with self.assertRaises(RegisterError):
            serv.register_account({'username': username})

        # test client grant
        authorization_code = provider.authorization_request(client_id)
        self.assertTrue(serv.verify_authorization_code(authorization_code))
        self.assertIsNone(provider.authorization_request(uuid.uuid4().hex))

        # test user authorization
        credentials = {'username': username, 'password': password}
        access_token, refresh_token = provider.authorization_grant(authorization_code, credentials)
        self.assertTrue(serv.verify_token(access_token))
        self.assertTrue(serv.verify_token(refresh_token))
        with self.assertRaises(AuthorizationError):
            provider.authorization_grant(authorization_code, {'username': username, 'password': 'errpwd'})
        with self.assertRaises(AuthorizationError):
            provider.authorization_grant(authorization_code, {'username': 'other', 'password': password})
        with self.assertRaises(AuthorizationError):
            provider.authorization_grant(uuid.uuid4().hex, {'username': '', 'password': ''})

        # test accessing protected resource
        account = serv.get_account_by_token(access_token)
        self.assertEqual(account['username'], username)
        self.assertEqual(account['password'], password)

        # revoke token
        serv.revoke_authorization_code(authorization_code)
        serv.revoke_token(access_token)

        self.assertFalse(serv.verify_authorization_code(authorization_code))
        self.assertFalse(serv.verify_token(access_token))
        with self.assertRaises(AuthorizationError):
            provider.authorization_grant(authorization_code, None)
        
        access_token = provider.refresh_grant(refresh_token)
        self.assertTrue(serv.verify_token(access_token))

        serv.revoke_token(access_token)
        serv.revoke_token(refresh_token)
        self.assertFalse(serv.verify_token(access_token))
        self.assertFalse(serv.verify_token(refresh_token))
        with self.assertRaises(InvalidTokenError):
            provider.refresh_grant(refresh_token)

    def test_api(self):
        """ Authorize grant redirect flow test """
        from huacaya.auth import EndpointApplication
        from tornado.wsgi import WSGIAdapter
        self._ep_app = WSGIAdapter(
            EndpointApplication(self._serv, self._provider)
        )

        app = self._ep_app
        serv = self._serv

        client_id = uuid.uuid4().hex
        serv.register_client(client_id)

        username = uuid.uuid4().hex
        password = uuid.uuid4().hex

        credentials = {'username': username, 'password': password}
        invlid_credentials = {'username': uuid.uuid4().hex, 'password': ''}

        # user signup
        resp = self.request(
            app, '/signup', method='POST',
            data=dict(username=username, password=password)
        )
        self.assertEqual(resp.status, '200 OK')
        self.assertIn('userid', resp.dct)

        # request grant by registered client
        resp = self.request(
            app, '/authorize', method='POST',
            data=dict(client_id=client_id)
        )
        self.assertEqual(resp.status, '200 OK')
        self.assertIn('code', resp.dct)
        authorization_code = resp.dct['code']

        # request grant by unregistered client
        resp = self.request(
            app, '/authorize', method='POST',
            data=dict(client_id=uuid.uuid4().hex),
        )
        self.assertEqual(resp.status, '403 Forbidden')

        # grant access token by valid authorization_code
        resp = self.request(
            app, '/grant', method='POST',
            data=dict(code=authorization_code, credentials=credentials)
        )
        self.assertIn('access_token', resp.dct)
        self.assertIn('refresh_token', resp.dct)
        access_token, refresh_token = resp.dct['access_token'], resp.dct['refresh_token']

        # grant access token by invalid authorization_code
        resp = self.request(
            app, '/grant', method='POST',
            data=dict(code=uuid.uuid4().hex, credentials=credentials)
        )
        self.assertEqual('403 Forbidden', resp.status)

        # grant access token by invalid credentials
        resp = self.request(
            app, '/grant', method='POST',
            data=dict(code=authorization_code, credentials=invlid_credentials)
        )
        self.assertEqual('403 Forbidden', resp.status)

        # get account resource
        resp = self.request(
            app, '/me', method='GET',
            headers=[('Authorization', 'Bearer {0}'.format(access_token)), ]
        )
        self.assertEqual(resp.dct['username'], username)
        self.assertIn('userid', resp.dct)
        self.assertNotIn('password', resp.dct)

        # revoke access token
        self.request(
            app, '/revoke', method='POST',
            data=dict(token=access_token)
        )
        resp = self.request(
            app, '/me', method='GET',
            headers=[('Authorization', 'Bearer {0}'.format(access_token)), ]
        )
        self.assertEqual('401 Unauthorized', resp.status)

        # refresh grant
        resp = self.request(
            app, '/refresh', method='POST',
            data=dict(refresh_token=refresh_token)
        )
        self.assertIn('access_token', resp.dct)

        # revoke refresh token
        self.request(
            app, '/revoke', method='POST',
            data=dict(token=refresh_token)
        )
        resp = self.request(
            app, '/refresh', method='POST',
            data=dict(refresh_token=refresh_token)
        )
        self.assertEqual('401 Unauthorized', resp.status)
