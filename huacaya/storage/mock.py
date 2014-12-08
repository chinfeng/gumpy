# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from .base import BucketBase, StorageBase
import pickle
import shutil
import os
import sys
try:
    import anydbm as dbm
except ImportError:
    import dbm
from tempfile import gettempdir

_singleton_storage = None

class Bucket(BucketBase):
    def __init__(self, name, db, storage):
        self._name = name
        self._db = db
        self._storage = storage

    def delete(self):
        self._storage.delete(self._name)

    def put_object(self, key, content, metadata=None):
        self._db[key] = pickle.dumps((metadata, content))

    def get_object(self, key):
        return pickle.loads(self._db[key])

    def delete_object(self, key):
        del self._db[key]

    def get_object_content(self, key):
        return self.get_object(key)[1]

    def find(self, fields):
        for k in self._db.keys():
            obj = self.get_object_content(k)
            if set(fields.items()).issubset(set(obj.items())):
                yield obj

    def find_one(self, fields):
        for k in self._db.keys():
            obj = self.get_object_content(k)
            if set(fields.items()).issubset(set(obj.items())):
                return obj
        return None

    def __getitem__(self, item):
        return self.get_object_content(item)

    def __contains__(self, item):
        return item in self._db

    def __iter__(self):
        return iter(self._db)

    def keys(self):
        return self._db.keys()

class Storage(StorageBase):
    def __init__(self, path=None):
        if path:
            self._path = os.path.abspath(path)
        else:
            self._path = os.path.join(os.path.abspath(gettempdir()), '.mock_storage_{0}'.format(sys.version_info.major))
        self._dbs = {}
        if not os.path.isdir(self._path):
            os.mkdir(self._path)

    def get_bucket(self, name):
        if name in self._dbs:
            return Bucket(name, self._dbs[name], self)
        else:
            pt = os.path.join(self._path, name)
            if not os.path.isdir(pt):
                os.mkdir(pt)
            db = dbm.open(os.path.join(pt, 'storage'), 'c')
            self._dbs[name] = db
            return Bucket(name, db, self)

    def __getitem__(self, item):
        return self.get_bucket(item)

    def delete(self, bucket):
        if type(bucket) is str:
            name = bucket
        elif isinstance(bucket, Bucket):
            name = bucket._name
        else:
            return
        if name in self._dbs:
            self._dbs.pop(name).close()
        pt = os.path.join(self._path, name)
        if os.path.isdir(pt):
            shutil.rmtree(pt)

    def __contains__(self, item):
        return os.path.isdir(os.path.join(self._path, item))
