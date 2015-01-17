# -*- coding: utf-8 -*-
__author__ = 'Chinfeng'


import uuid
import sqlite3
import datetime
import itertools
from .base import StorageBase, BucketBase
try:
    import cPickle as pickle
except ImportError:
    import pickle

class SqliteBucket(BucketBase):
    def __init__(self, db, name, indexes):
        self._db = db
        self._name = name
        self._indexes = indexes

    def drop(self):
        self._db.cursor().executescript('''
            DROP TABLE IF EXISTS {table}_entities;
            DROP TABLE IF EXISTS {table}_indexes;
            DELETE FROM settings WHERE bucket='{table}'
        '''.format(table=self._name))

    def put(self, entity):
        if not isinstance(entity, dict):
            raise ValueError('dict type support only')

        cursor = self._db.cursor()

        if 'id' in entity:
            cursor.execute(
                'INSERT OR REPLACE INTO {0}_entities(id, updated, body) VALUES(?, ?, ?)'.format(self._name),
                (entity['id'], datetime.datetime.now(), pickle.dumps(entity))
            )
        else:
            entity['id'] = uuid.uuid4().hex
            cursor.execute(
                'INSERT INTO {0}_entities (id, updated, body) VALUES(?, ?, ?)'.format(self._name),
                (entity['id'], datetime.datetime.now(), pickle.dumps(entity))
            )

        index_param_list = []
        for index in self._indexes:
            if index in entity and isinstance(entity[index], str):
                index_param_list.append((entity['id'], index, entity[index]))
        cursor.executemany(
            'INSERT OR REPLACE INTO {0}_indexes(entity_id, index_name, index_val) VALUES(?, ?, ?)'.format(self._name),
            index_param_list
        )

        return entity['id']

    def get(self, stub):
        if isinstance(stub, str):
            row = self._db.cursor().execute(
                'SELECT body FROM {0}_entities WHERE id=?'.format(self._name),
                (stub, )
            ).fetchone()
            if row:
                return pickle.loads(row[0])
            else:
                raise IndexError('entity {0} not found'.format(stub))
        elif isinstance(stub, dict):
            sql = ' INTERSECT '.join((
                'SELECT entity_id FROM {0}_indexes WHERE index_name=? AND index_val=?'.format(self._name) for i in range(len(stub))
            ))
            row = self._db.cursor().execute(
                sql, tuple(itertools.chain(*stub.items()))
            ).fetchone()
            if len(row) == 1:
                return self.get(row[0])
            elif len(row) == 0:
                raise IndexError('entity {0} not found'.format(stub))
            elif len(row) > 1:
                raise IndexError('entity {0} more than one'.format(stub))

    def delete(self, stub):
        if isinstance(stub, str):
            self._db.cursor().execute(
                'DELETE FROM {0}_entities WHERE id=?'.format(self._name),
                (stub, )
            )
        elif isinstance(stub, dict):
            sql = ' INTERSECT '.join((
                'SELECT entity_id FROM {0}_indexes WHERE index_name=? AND index_val=?'.format(self._name) for i in range(len(stub))
            ))
            row = self._db.cursor().execute(
                sql, tuple(itertools.chain(*stub.items()))
            ).fetchone()
            if len(row) == 1:
                return self.delete(row[0])
            elif len(row) == 0:
                raise IndexError('entity {0} not found'.format(stub))
            elif len(row) > 1:
                raise IndexError('entity {0} more than one'.format(stub))

    def find(self, index_dict):
        if isinstance(index_dict, dict):
            sql = ' INTERSECT '.join((
                'SELECT entity_id FROM {0}_indexes WHERE index_name=? AND index_val=?'.format(self._name) for i in range(len(index_dict))
            ))
            rows = self._db.cursor().execute(
                'SELECT body FROM {0}_entities WHERE id IN ({1})'.format(self._name, sql),
                tuple(itertools.chain(*index_dict.items()))
            )
            for r in rows:
                yield pickle.loads(r[0])

    def __contains__(self, stub):
        if isinstance(stub, str):
            return self._db.cursor().execute(
                'SELECT COALESCE((SELECT 1 FROM {0}_entities WHERE id=?), 0)'.format(self._name),
                (stub, )).fetchone()[0]
        elif isinstance(stub, dict):
            sql = ' INTERSECT '.join((
                'SELECT entity_id FROM {0}_indexes WHERE index_name=? AND index_val=?'.format(self._name) for i in range(len(stub))
            ))
            return bool(self._db.cursor().execute(
                'SELECT EXISTS({0})'.format(sql), tuple(itertools.chain(*stub.items()))
            ).fetchone()[0])

class SqliteStorage(StorageBase):
    def __init__(self, uri=':memory:'):
        self._sqlite_db = sqlite3.connect(uri, check_same_thread=False)
        self._sqlite_db.execute('''
          CREATE TABLE settings (
            bucket VARCHAR PRIMARY KEY,
            indexes VARCHAR
          )
        ''')

    def create_bucket(self, name, indexes=()):
        # TODO
        # CREATE BUCKET TABLE
        cursor = self._sqlite_db.cursor()
        if indexes:
            cursor.execute(
                'INSERT OR REPLACE INTO settings(bucket, indexes) VALUES(?, ?)',
                (name, ','.join(indexes))
            )
        else:
            indexes_val = cursor.execute(
                'SELECT COALESCE((SELECT indexes FROM settings WHERE bucket=?), NULL)', (name, )
            ).fetchone()[0]
            indexes = indexes_val.split(',') if indexes_val else ()
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS {table}_entities (
            id CHAR(32) PRIMARY KEY,
            updated DATETIME NOT NULL,
            body BLOB
          )
        '''.format(table=name))
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS {table}_indexes (
            index_name VARCHAR,
            index_val VARCHAR,
            entity_id CHAR(32),
            PRIMARY KEY (entity_id, index_name),
            FOREIGN KEY (entity_id) REFERENCES {table}_entities(id) ON DELETE CASCADE
          )
        '''.format(table=name))
        return SqliteBucket(self._sqlite_db, name, indexes)

    def get_bucket(self, name):
        indexes_str = self._sqlite_db.cursor().execute(
            'SELECT COALESCE((SELECT indexes FROM settings WHERE bucket=?), NULL)', (name, )
        ).fetchone()[0]
        return SqliteBucket(self._sqlite_db, name, indexes_str.split(',') if indexes_str else ())

    def drop(self, bucket):
        if isinstance(bucket, str):
            self.get_bucket(bucket).drop()
        elif isinstance(bucket, SqliteBucket):
            bucket.drop()

    def __contains__(self, item):
        return self._sqlite_db.cursor().execute(
            'SELECT COALESCE((SELECT 1 FROM settings WHERE bucket=?), 0)', (item, )
        ).fetchone()[0]
