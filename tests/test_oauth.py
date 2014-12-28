# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import uuid

try:
    from urlparse import urlparse, parse_qs
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlparse, parse_qs, urlencode
from tests.wsgi import WSGITestCase


class OAuthTestCase(WSGITestCase):
    def get_app(self):
        from huacaya.auth import Server, Provider, ServerDaoWithStorage
        from huacaya.auth import EndpointApplication
        from huacaya.storage import mock
        from tornado.wsgi import WSGIAdapter

        self._storage = mock.Storage()
        serv_dao = ServerDaoWithStorage(self._storage)
        self._serv = Server(serv_dao)
        self._provider = Provider(self._serv)
        return WSGIAdapter(
            EndpointApplication(self._serv, self._provider)
        )

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
        token_data = provider.authorization_grant(authorization_code, credentials)
        access_token, refresh_token = token_data['access_token'], token_data['refresh_token']
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

        token_data = provider.refresh_grant(refresh_token)
        self.assertTrue(serv.verify_token(token_data['access_token']))

        serv.revoke_token(access_token)
        serv.revoke_token(refresh_token)
        self.assertFalse(serv.verify_token(access_token))
        self.assertFalse(serv.verify_token(refresh_token))
        with self.assertRaises(InvalidTokenError):
            provider.refresh_grant(refresh_token)

    def test_authorization_code_grant(self):
        """授权码三段验证
        http://tools.ietf.org/html/rfc6749#section-4.1
        基于重定向的页面流，为三方客户端提供 access_token 和 refresh_token 的授权
        +----------+
        | Resource |
        |   Owner  |
        |          |
        +----------+
             ^
             |
            (B)
        +----|-----+          Client Identifier      +---------------+
        |         -+----(A)-- & Redirection URI ---->|               |
        |  User-   |                                 | Authorization |
        |  Agent  -+----(B)-- User authenticates --->|     Server    |
        |          |                                 |               |
        |         -+----(C)-- Authorization Code ---<|               |
        +-|----|---+                                 +---------------+
          |    |                                         ^      v
        (A)  (C)                                        |      |
          |    |                                         |      |
          ^    v                                         |      |
        +---------+                                      |      |
        |         |>---(D)-- Authorization Code ---------'      |
        |  Client |          & Redirection URI                  |
        |         |                                             |
        |         |<---(E)----- Access Token -------------------'
        +---------+       (w/ Optional Refresh Token)
        """

        # 授信一个客户端
        server = self._serv
        client_id = uuid.uuid4().hex
        server.register_client(client_id)

        credentials = {'username': uuid.uuid4().hex, 'password': uuid.uuid4().hex, 'other': uuid.uuid4().hex}

        # 注册一个用户
        resp = self.request(
            '/signup', headers={'Content-Type': 'application/json'}, data=credentials
        )
        self.assertEqual(200, resp.code)
        self.assertIn('account_id', resp.dct)

        # User-agent 发起请求
        # End point 页面请求接收参数，返回 authorization code
        auth_request_mock_data = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': 'http://www.other.com/code',
            'state': 'xyz',
        }

        # 负面测试数据
        invalid_client_auth_request_mock_data = auth_request_mock_data.copy()
        invalid_client_auth_request_mock_data['client_id'] = uuid.uuid4().hex

        invalid_type_auth_request_mock_data = auth_request_mock_data.copy()
        invalid_type_auth_request_mock_data['response_type'] = uuid.uuid4().hex

        # 完成图中 (A)(B)(C) 步骤，返回 redirect_uri 的重定向
        # 此接口主要验证 client 合法性
        resp = self.request(
            '/authorize', data=auth_request_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertTrue(
            resp.headers['Location'].startswith(
                auth_request_mock_data['redirect_uri']
            )
        )
        self.assertIn('code', qdct)
        authorization_code = qdct['code'][0]   # 获得合法的请求码
        self.assertEqual('xyz', qdct['state'][0])

        # 无效 client，返回 error
        resp = self.request(
            '/authorize', data=invalid_client_auth_request_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertIn('unauthorized_client', qdct['error'])
        self.assertTrue(
            resp.headers['Location'].startswith(
                auth_request_mock_data['redirect_uri']
            )
        )
        self.assertEqual('xyz', qdct['state'][0])

        # 无效 response_type，返回 error
        resp = self.request(
            '/authorize', data=invalid_type_auth_request_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertTrue(
            resp.headers['Location'].startswith(
                auth_request_mock_data['redirect_uri']
            )
        )
        self.assertIn('invalid_request', qdct['error'])
        self.assertEqual('xyz', qdct['state'][0])

        # 参数不完整，返回 error
        resp = self.request(
            '/authorize', data={'client_id': 'abc'},
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertIn('invalid_request', qdct['error'])

        # 完成图中 (D)(E) 步骤
        # 此接口为 Authorization Server 的用户认证页面使用，
        # 注：
        #   1. 暂不处理 client authentication
        #   2. 返回 200 获得各种信息后，再由客户端 post 到三方 redirect_uri，此处不作测试
        #   3. 规范所述，如果授权码中含有 redirect_uri，则本步骤必须提供，以验证两者是否一致，
        #     如同域，或证书的验证，暂不实现
        #   4. 附加 user authenticates，由本服务器的认证前端 Endpoint，不在本测试范围内
        #   5. 返回 redirect_uri，给三方 client 附上 access、refresh 两个 token，由
        #     user-agent 承担，不在本测试范围内
        access_request_mock_data = {
            'grant_type': 'authorization_code',
            'redirect_uri': 'http://www.other.com/token',
            'code': authorization_code,
            'username': credentials['username'],
            'password': credentials['password'],
        }

        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=access_request_mock_data,
        )

        self.assertEqual(200, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('utf-8', resp.charset.lower())
        self.assertIn('access_token', resp.dct)
        self.assertIn('refresh_token', resp.dct)
        self.assertIn('expires_in', resp.dct)
        access_token = resp.dct['access_token']
        refresh_token = resp.dct['refresh_token']
        self.assertIn('bearer', resp.dct['token_type'])

        # 非法 authorization_code
        invalid_access_request_mock_data = access_request_mock_data.copy()
        invalid_access_request_mock_data['code'] = uuid.uuid4().hex
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=invalid_access_request_mock_data,
        )
        self.assertEqual(400, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('invalid_grant', resp.dct['error'])

        # redirect_uri 鉴定不一致
        invalid_access_request_mock_data = access_request_mock_data.copy()
        invalid_access_request_mock_data['redirect_uri'] = uuid.uuid4().hex
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=invalid_access_request_mock_data,
        )
        self.assertEqual(400, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('invalid_grant', resp.dct['error'])

        # 使用 access_token 获得账户信息
        resp = self.request(
            '/me', headers={'Authorization': 'Bearer ' + access_token}
        )
        self.assertEqual(200, resp.code)
        self.assertIn('account_id', resp.dct)
        self.assertEqual(credentials['username'], resp.dct['username'])
        self.assertEqual(credentials['other'], resp.dct['other'])

        # 使用错误的 access_token，返回 401
        resp = self.request(
            '/me', headers={'Authorization': 'Bearer ' + uuid.uuid4().hex}
        )
        self.assertEqual(401, resp.code)

        # 使用 refresh_token 获得新 access_token
        refresh_request_mock_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=refresh_request_mock_data,
        )
        self.assertEqual(200, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('utf-8', resp.charset.lower())
        self.assertIn('access_token', resp.dct)
        self.assertIn(refresh_token, resp.dct['refresh_token'])
        self.assertIn('expires_in', resp.dct)
        self.assertIn('bearer', resp.dct['token_type'])

        # 使用非法 refresh_token，返回 400
        invalid_refresh_request_mock_data = refresh_request_mock_data.copy()
        invalid_refresh_request_mock_data['refresh_token'] = uuid.uuid4().hex
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=invalid_refresh_request_mock_data,
        )
        self.assertEqual(400, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('invalid_grant', resp.dct['error'])

    def test_implicit_grant(self):
        # http://tools.ietf.org/html/rfc6749#section-4.2
        # 隐式授权，公共资源
        # TODO
        pass

    def test_owner_password_credentials_grant(self):
        # http://tools.ietf.org/html/rfc6749#section-4.3
        # 密码授权
        # TODO
        pass

    def test_client_credentials_grant(self):
        # http://tools.ietf.org/html/rfc6749#section-4.4
        # 私有证书授权
        # TODO
        pass
