import unittest
import json
import os
import tempfile
from pathlib import Path

from app import app, store

class TestAuthFlow(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_signup_login_and_bootstrap_flow(self):
        import uuid
        email = f"teststudent_{uuid.uuid4().hex[:8]}@example.com"
        password = "password123"
        name = "Test Student"

        # 1. Signup
        signup_res = self.app.post('/api/auth/signup', data=json.dumps({
            'email': email,
            'password': password,
            'name': name
        }), content_type='application/json')

        self.assertEqual(signup_res.status_code, 200)
        signup_data = json.loads(signup_res.data)
        self.assertTrue(signup_data.get('success'))
        self.assertIn('user', signup_data)
        user_id = signup_data['user']['id']
        self.assertEqual(signup_data['user']['email'], email)

        # 2. Bootstrap with session cookie
        boot_res = self.app.get('/api/bootstrap')
        self.assertEqual(boot_res.status_code, 200)
        boot_data = json.loads(boot_res.data)
        self.assertIsNotNone(boot_data.get('user'))
        self.assertEqual(boot_data['user']['id'], user_id)

        # 3. Logout
        logout_res = self.app.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # 4. Bootstrap without session cookie (should be unauthenticated)
        boot_res2 = self.app.get('/api/bootstrap')
        boot_data2 = json.loads(boot_res2.data)
        self.assertIsNone(boot_data2.get('user'))

        # 5. Bootstrap with X-User-Id header (header fallback)
        boot_res3 = self.app.get('/api/bootstrap', headers={'X-User-Id': user_id})
        boot_data3 = json.loads(boot_res3.data)
        self.assertIsNotNone(boot_data3.get('user'))
        self.assertEqual(boot_data3['user']['id'], user_id)

        # 6. Login
        login_res = self.app.post('/api/auth/login', data=json.dumps({
            'email': email,
            'password': password
        }), content_type='application/json')
        self.assertEqual(login_res.status_code, 200)
        login_data = json.loads(login_res.data)
        self.assertTrue(login_data.get('success'))
        self.assertEqual(login_data['user']['id'], user_id)

if __name__ == '__main__':
    unittest.main()
