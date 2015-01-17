# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import random
import unittest
import uuid


class StorageTestCase(unittest.TestCase):
    def test_mock_storage(self):
        from huacaya.storage import mock
        self._exec(mock.MockStorage())

    def test_mongo_storage(self):
        storage = None
        try:
            from huacaya.storage import mongo
            from pymongo.mongo_client import MongoClient
            storage = mongo.MongoStorage(MongoClient().huacaya)
        except:
            self.skipTest('MongoDB at localhost is not avaliable now, test_mongo_storage skipped.')
        if storage:
            self._exec(storage)

    def _exec(self, storage):
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
        self.assertEqual(cnt_1, bkt.get_object('1.txt'))

        bkt.put_object('2.txt', cnt_2)
        self.assertIn('2.txt', bkt)
        cnt = bkt.get_object('2.txt')
        self.assertEqual(cnt, cnt_2)

        bkt.delete_object('1.txt')
        self.assertNotIn('1.txt', bkt)
        bkt.delete_object('2.txt')
        self.assertNotIn('2.txt', bkt)

        storage.delete('t')
        self.assertNotIn('t', storage)

    def test_sqlite(self):
        from huacaya.storage.sqlite import SqliteStorage
        storage = SqliteStorage()
        bkt = storage.create_bucket('testbkt')
        self.assertIsNotNone(bkt)

        bkt.drop()
        self.assertNotIn('testbkt', storage)

        cnt_1 = {'id': uuid.uuid4().hex, 'name': 'cnt_1',
                 'body': bytes([random.randint(1, 254) for i in range(100)])}
        cnt_2 = {'id': uuid.uuid4().hex, 'name': 'cnt_2',
                 'body': bytes([random.randint(1, 254) for i in range(100)])}
        bkt = storage.create_bucket('t', ('name', 'flag'))
        self.assertIn('t', storage)

        bkt.put(cnt_1)
        self.assertIn(cnt_1['id'], bkt)
        self.assertDictEqual(cnt_1, bkt.get(cnt_1['id']))

        bkt.put(cnt_2)
        self.assertIn(cnt_2['id'], bkt)
        self.assertDictEqual(cnt_2, bkt.get(cnt_2['id']))

        bkt.delete(cnt_1['id'])
        self.assertNotIn(cnt_1['id'], bkt)
        bkt.delete(cnt_2['id'])
        self.assertNotIn(cnt_2['id'], bkt)

        cnt_3 = {'name': 'cnt_3', 'body': bytes([random.randint(1, 254) for i in range(100)])}
        cnt_3_id = bkt.put(cnt_3)
        self.assertIn({'name': 'cnt_3'}, bkt)
        cnt = bkt.get({'name': 'cnt_3'})
        self.assertEqual(cnt_3_id, cnt['id'])

        cnt_3 = {'name': 'cnt_3', 'flag': 'some'}
        cnt_3_id = bkt.put(cnt_3)
        self.assertIn({'name': 'cnt_3', 'flag': 'some'}, bkt)
        cnt = bkt.get({'name': 'cnt_3', 'flag': 'some'})
        self.assertEqual(cnt_3_id, cnt['id'])

        for cnt in bkt.find({'name': 'cnt_3'}):
            self.assertEqual('cnt_3', cnt['name'])

        storage.drop('t')
        self.assertNotIn('t', storage)
