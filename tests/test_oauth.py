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
        from huacaya.storage import StorageService
        from tornado.wsgi import WSGIAdapter

        self._storage = StorageService()
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
        account_id = serv.register_account({'username': username, 'password': password})
        with self.assertRaises(RegisterError):
            serv.register_client(client_id)
        with self.assertRaises(RegisterError):
            serv.register_account({'username': username})

        # test client grant
        authorization_code = provider.authorization_request(client_id, account_id)
        self.assertTrue(serv.verify_authorization_code(authorization_code))
        self.assertIsNone(provider.authorization_request(uuid.uuid4().hex, account_id))

        # test user authorization
        token_data = provider.authorization_grant(authorization_code)
        access_token, refresh_token = token_data['access_token'], token_data['refresh_token']
        self.assertTrue(serv.verify_token(access_token))
        self.assertTrue(serv.verify_token(refresh_token))

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
        """ 授权码三段验证
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

        流程：
            1. 客户代理 -> GET /authorize 发起请求 (A)
            2. GET /authorize 中转到登陆 endpoint，用户登陆（已登陆略过）(B)
            3. 转到授权 endpoint，点选同意按钮 (B)
            4. 转回 redirect_uri （带 authorization code）(C)

            5. 使用第4步的 code 发起 POST /grant (D)
            6. 返回 access/refresh token (E)

            7. 使用 access token 访问 /me 查看用户信息
            8. 使用第6步的 refresh token 发起 POST /grant，获得新的 access token

        注：本测试不包含 endpoint 的 html 页面。
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

        # 1. 客户代理 -> GET /authorize 发起请求 (A)
        #   测试是否能正常中转至登陆页面 /signin.html
        authorize_get_mock_data = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': 'http://www.other.com/code',
            'state': 'xyz',
        }
        resp = self.request(
            '/authorize', data=authorize_get_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        # 中转至登陆 endpoint页面
        self.assertEqual('/signin.html', location.path)
        # 确保参数正确传递给登陆 endpoint
        self.assertIn(authorize_get_mock_data['response_type'], qdct['response_type'][0])
        self.assertIn(authorize_get_mock_data['client_id'], qdct['client_id'][0])
        self.assertIn(authorize_get_mock_data['redirect_uri'], qdct['redirect_uri'][0])
        self.assertEqual('xyz', qdct['state'][0])

        # 2. GET /authorize 中转到登陆 endpoint，用户登陆（已登陆略过）(B)
        #   模拟 /signin.html 中的登陆请求，获得登陆状态
        resp = self.request(
            '/signin', data=credentials,
            method='POST', headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(200, resp.code)

        # 3. 转到授权 endpoint，点选同意按钮 (B)
        #   在 /signin.html 登陆成功后，用脚本转到授权页面 /auth.html，提供是否同意授权选择
        #   所有 /sigin.html 的中间参数，会以 query 的形势传递给 auth.html，该前端过程不在此测试内
        #   注意 /authorize 为 GET 时转入登陆 endpoint，为 POST 时处理授权请求
        authorize_post_mock_data = authorize_get_mock_data.copy()
        authorize_post_mock_data['agreed'] = 1
        resp = self.request(
            '/authorize', data=authorize_post_mock_data,
            method='POST', headers={'Content-Type': 'application/json'}
        )

        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertTrue(
            resp.headers['Location'].startswith(
                authorize_get_mock_data['redirect_uri']
            )
        )
        self.assertIn('code', qdct)
        # 4. 转回 redirect_uri （带 authorization code）(C)
        authorization_code = qdct['code'][0]   # 获得合法的请求码
        self.assertEqual('xyz', qdct['state'][0])

        # 负面测试
        invalid_client_auth_get_mock_data = authorize_get_mock_data.copy()
        invalid_client_auth_get_mock_data['client_id'] = uuid.uuid4().hex

        invalid_type_auth_get_mock_data = authorize_get_mock_data.copy()
        invalid_type_auth_get_mock_data['response_type'] = uuid.uuid4().hex

        # 无效 client，返回 error
        resp = self.request(
            '/authorize', data=invalid_client_auth_get_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertIn('unauthorized_client', qdct['error'])
        self.assertTrue(
            resp.headers['Location'].startswith(
                authorize_get_mock_data['redirect_uri']
            )
        )
        self.assertEqual('xyz', qdct['state'][0])

        # 无效 response_type，返回 error
        resp = self.request(
            '/authorize', data=invalid_type_auth_get_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertTrue(
            resp.headers['Location'].startswith(
                authorize_get_mock_data['redirect_uri']
            )
        )
        self.assertIn('unsupported_response_type', qdct['error'])
        self.assertEqual('xyz', qdct['state'][0])

        # 参数不完整，返回 error
        resp = self.request(
            '/authorize', data={'client_id': 'abc'},
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertIn('invalid_request', qdct['error'][0])

        # 5. 使用第4步的 code 发起 POST /grant (D)
        # 注：
        #   1. 暂不处理 client authentication
        #   2. 规范所述，如果授权码中含有 redirect_uri，则本步骤必须提供，以验证两者是否一致，
        #     如同域，或证书的验证，暂不实现
        access_request_mock_data = {
            'grant_type': 'authorization_code',
            'redirect_uri': 'http://www.other.com/token',
            'code': authorization_code,
        }

        resp = self.request(
            '/grant', data=access_request_mock_data, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )

        self.assertEqual(200, resp.code)
        self.assertTrue(resp.headers.get('content-type').startswith('application/json'))
        self.assertEqual('utf-8', resp.charset.lower())
        self.assertIn('access_token', resp.dct)
        self.assertIn('refresh_token', resp.dct)
        self.assertIn('expires_in', resp.dct)
        self.assertEqual('bearer', resp.dct['token_type'])
        # 6. 返回 access/refresh token (E)
        access_token = resp.dct['access_token']
        refresh_token = resp.dct['refresh_token']

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

        # 7. 使用 access token 访问 /me 查看用户信息
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

        # 8. 使用第6步的 refresh token 发起 POST /grant，获得新的 access token
        refresh_request_mock_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=refresh_request_mock_data,
        )
        self.assertEqual(200, resp.code)
        self.assertTrue(resp.headers.get('content-type').startswith('application/json'))
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
        """ 隐式授权
        http://tools.ietf.org/html/rfc6749#section-4.2
        无能力保存请求码，譬如浏览器之类的，使用隐式授权，一次交互完成。
        但这一种授权只发放 access_token，不发放 refresh_token

            +----------+
            | Resource |
            |  Owner   |
            |          |
            +----------+
              ^
              |
             (B)
            +----|-----+          Client Identifier     +---------------+
            |         -+----(A)-- & Redirection URI --->|               |
            |  User-   |                                | Authorization |
            |  Agent  -|----(B)-- User authenticates -->|     Server    |
            |          |                                |               |
            |          |<---(C)--- Redirection URI ----<|               |
            |          |          with Access Token     +---------------+
            |          |            in Fragment
            |          |                                +---------------+
            |          |----(D)--- Redirection URI ---->|   Web-Hosted  |
            |          |          without Fragment      |     Client    |
            |          |                                |    Resource   |
            |     (F)  |<---(E)------- Script ---------<|               |
            |          |                                +---------------+
            +-|--------+
            |    |
            (A)  (G) Access Token
            |    |
            ^    v
            +---------+
            |         |
            |  Client |
            |         |
            +---------+

        流程：
            1. 客户代理 -> GET /authorize 发起请求 (A)
            2. GET /authorize 中转到登陆 endpoint，用户登陆（已登陆略过）(B)
            3. 转到授权 endpoint，点选同意按钮 (B)
            4. 转回 redirect_uri，获得 access token (C)

            5. 使用 access token 访问 /me 查看用户信息
        """
        # TODO
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

        # 1. 客户代理 -> GET /authorize 发起请求 (A)
        #   测试是否能正常中转至登陆页面 /signin.html
        token_request_mock_data = {
            'response_type': 'token',
            'client_id': client_id,
            'redirect_uri': 'http://www.other.com/token',
            'state': 'xyz',
        }
        resp = self.request(
            '/authorize', data=token_request_mock_data,
        )
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        # 中转至登陆 endpoint页面
        self.assertEqual('/signin.html', location.path)
        # 确保参数正确传递给登陆 endpoint
        self.assertIn(token_request_mock_data['response_type'], qdct['response_type'][0])
        self.assertIn(token_request_mock_data['client_id'], qdct['client_id'][0])
        self.assertIn(token_request_mock_data['redirect_uri'], qdct['redirect_uri'][0])
        self.assertEqual('xyz', qdct['state'][0])

        # 2. GET /authorize 中转到登陆 endpoint，用户登陆（已登陆略过）(B)
        #   模拟 /signin.html 中的登陆请求，获得登陆状态
        resp = self.request(
            '/signin', data=credentials,
            method='POST', headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(200, resp.code)

        # 3. 转到授权 endpoint，点选同意按钮 (B)
        #   在 /signin.html 登陆成功后，用脚本转到授权页面 /auth.html，提供是否同意授权选择
        #   所有 /sigin.html 的中间参数，会以 query 的形势传递给 auth.html，该前端过程不在此测试内
        #   注意 /authorize 为 GET 时转入登陆 endpoint，为 POST 时处理授权请求
        token_grant_mock_data = token_request_mock_data.copy()
        token_grant_mock_data['agreed'] = 1
        resp = self.request(
            '/authorize', data=token_grant_mock_data,
            method='POST', headers={'Content-Type': 'application/json'}
        )

        # 4. 转回 redirect_uri，获得 access token (C)
        self.assertEqual(302, resp.code)
        location = urlparse(resp.headers['Location'])
        qdct = parse_qs(location.query)
        self.assertTrue(
            resp.headers['Location'].startswith(
                token_grant_mock_data['redirect_uri']
            )
        )
        self.assertIn('access_token', qdct)
        self.assertEqual('bearer', qdct['token_type'][0])
        self.assertIn('expires_in', qdct)
        access_token = qdct['access_token'][0]

        # 使用 access_token 获得账户信息
        resp = self.request(
            '/me', headers={'Authorization': 'Bearer ' + access_token}
        )
        self.assertEqual(200, resp.code)
        self.assertIn('account_id', resp.dct)
        self.assertEqual(credentials['username'], resp.dct['username'])
        self.assertEqual(credentials['other'], resp.dct['other'])

    def test_owner_password_credentials_grant(self):
        """ 用户密码授权
        http://tools.ietf.org/html/rfc6749#section-4.3
        直接使用用户名、密码授权

            +----------+
            | Resource |
            |  Owner   |
            |          |
            +----------+
              v
              |    Resource Owner
             (A) Password Credentials
              |
              v
            +---------+                                  +---------------+
            |         |>--(B)---- Resource Owner ------->|               |
            |         |         Password Credentials     | Authorization |
            | Client  |                                  |     Server    |
            |         |<--(C)---- Access Token ---------<|               |
            |         |    (w/ Optional Refresh Token)   |               |
            +---------+                                  +---------------+

        流程：
            1. 向授权接口发送 POST 请求，附上用户名和密码 (B)
            2. 返回 access/refresh token 信息
            3. 获取用户信息
            4. 使用第2步的 refresh token 发起 POST /grant，获得新的 access token
        """
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

        password_grant_mock_data = {
            'grant_type': 'password',
            'username': credentials['username'],
            'password': credentials['password'],
        }

        resp = self.request(
            '/grant', data=password_grant_mock_data, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        self.assertEqual(200, resp.code)
        self.assertEqual('application/json', resp.headers.get('content-type')[:16])
        self.assertEqual('utf-8', resp.charset.lower())
        self.assertIn('access_token', resp.dct)
        self.assertIn('refresh_token', resp.dct)
        self.assertIn('expires_in', resp.dct)
        self.assertEqual('bearer', resp.dct['token_type'])

        # 2. 返回 access/refresh token (E)
        access_token = resp.dct['access_token']
        refresh_token = resp.dct['refresh_token']

        # 3. 获取用户信息
        resp = self.request(
            '/me', headers={'Authorization': 'Bearer ' + access_token}
        )
        self.assertEqual(200, resp.code)
        self.assertIn('account_id', resp.dct)
        self.assertEqual(credentials['username'], resp.dct['username'])
        self.assertEqual(credentials['other'], resp.dct['other'])

        # 4. 使用第2步的 refresh token 发起 POST /grant，获得新的 access token
        refresh_request_mock_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }
        resp = self.request(
            '/grant', method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=refresh_request_mock_data,
        )
        self.assertEqual(200, resp.code)
        self.assertTrue(resp.headers.get('content-type').startswith('application/json'))
        self.assertEqual('utf-8', resp.charset.lower())
        self.assertIn('access_token', resp.dct)
        self.assertIn(refresh_token, resp.dct['refresh_token'])
        self.assertIn('expires_in', resp.dct)
        self.assertIn('bearer', resp.dct['token_type'])

        # 无效用户名密码
        invalid_password_grant_mock_data = password_grant_mock_data.copy()
        invalid_password_grant_mock_data['password'] = uuid.uuid4().hex

        resp = self.request(
            '/grant', data=invalid_password_grant_mock_data, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        self.assertEqual(400, resp.code)

    def test_client_credentials_grant(self):
        # http://tools.ietf.org/html/rfc6749#section-4.4
        # 私有证书授权，待定
        # TODO
        pass
