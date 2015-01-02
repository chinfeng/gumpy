# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from .base import BucketBase, StorageBase
import pickle
import base64
import sqlite3

_singleton_storage = None

class MockBucket(BucketBase):
    def __init__(self, storage, db, name):
        self._storage = storage
        self._db = db
        self._name = name
        self._db.cursor().execute('''
            CREATE TABLE IF NOT EXISTS {0} (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              k VARCHAR UNIQUE,
              v BLOG
            )
        '''.format(name))

    def delete(self):
        self._db.cursor().execute(
            'DROP TABLE IF EXISTS {0}'.format(self._name)
        )

    def put_object(self, key, content):
        sql = 'INSERT OR REPLACE INTO {0}(k, v) VALUES(?, ?)'.format(self._name)
        self._db.cursor().execute(sql, (key, pickle.dumps(content)))

    def get_object(self, key):
        sql = 'SELECT v FROM {0} WHERE k=?'.format(self._name)
        one = self._db.cursor().execute(sql, (key, )).fetchone()
        return pickle.loads(one[0]) if one else None

    def delete_object(self, key):
        sql = 'DELETE FROM {0} WHERE k=?'.format(self._name)
        self._db.cursor().execute(sql, (key, ))

    def find(self, fields):
        for k, v in self.items():
            if set(fields.items()).issubset(set(v.items())):
                yield k, v

    def find_one(self, fields):
        for k, v in self.items():
            if set(fields.items()).issubset(set(v.items())):
                return k, v
        return None

    def __getitem__(self, item):
        return self.get_object(item)

    def __contains__(self, item):
        sql = 'SELECT COUNT(id) FROM {0} WHERE k=?'.format(self._name)
        return self._db.cursor().execute(sql, (item, )).fetchone()[0] > 0

    def __iter__(self):
        sql = 'SELECT k FROM {0}'.format(self._name)
        for row in self._db.cursor().execute(sql):
            yield row[0]

    def keys(self):
        return list(self)

    def items(self):
        sql = 'SELECT k, v FROM {0}'.format(self._name)
        for row in self._db.cursor().execute(sql):
            yield row[0], pickle.loads(row[1])


class MockStorage(StorageBase):
    def __init__(self, uri=':memory:'):
        self._sqlite_db = sqlite3.connect(uri, check_same_thread=False)

    def _to_table_name(self, name):
        return base64.b32encode(name.encode('utf-8')).decode('utf-8').strip('=')

    def get_bucket(self, name):
        return MockBucket(self, self._sqlite_db, self._to_table_name(name))

    def __getitem__(self, item):
        return self.get_bucket(item)

    def delete(self, bucket):
        if isinstance(bucket, str):
            self.get_bucket(bucket).delete()
        elif isinstance(bucket, MockBucket):
            bucket.delete()

    def __contains__(self, name):
        return self._sqlite_db.cursor().execute(
            'SELECT count(*) FROM sqlite_master WHERE type=? and name=?',
            ('table', self._to_table_name(name))
        ).fetchone()[0] > 0
