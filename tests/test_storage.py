# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import random
import unittest

class OAuthTestCase(unittest.TestCase):
    def setUp(self):
        from huacaya.storage import mock
        self._storage = mock.Storage()

    def test_storage(self):
        storage = self._storage
        bkt = storage.get_bucket('testbkt')
        self.assertIsNotNone(bkt)

        bkt.delete()
        self.assertNotIn('testbkt', storage)

        cnt_1 = bytes([random.randint(1, 254) for i in range(100)])
        cnt_2 = bytes([random.randint(1, 254) for i in range(200)])        
        bkt = storage.get_bucket('t')
        self.assertIn('t', storage)

        bkt.put_object('1.txt', cnt_1)
        self.assertIn('1.txt', bkt)
        self.assertEqual(cnt_1, bkt.get_object_content('1.txt'))

        bkt.put_object('2.txt', cnt_2, metadata={'content_type': 'text/plain'})
        self.assertIn('2.txt', bkt)
        metadata, cnt = bkt.get_object('2.txt')
        self.assertEqual(cnt, cnt_2)
        self.assertEqual(metadata['content_type'], 'text/plain')

        bkt.delete_object('1.txt')
        self.assertNotIn('1.txt', bkt)
        bkt.delete_object('2.txt')
        self.assertNotIn('2.txt', bkt)

        storage.delete('t')
        self.assertNotIn('t', storage)
