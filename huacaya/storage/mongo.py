# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from .base import BucketBase, StorageBase
from pymongo.errors import OperationFailure

class MongoBucket(BucketBase):
    def __init__(self, collection):
        self._collection = collection

    @property
    def name(self):
        return self._collection.name

    def delete(self):
        self._collection.drop()

    def put_object(self, key, content):
        doc = self._collection.find_one({'key': key})
        if doc:
            doc['content'] = content
            self._collection.save(doc)
        else:
            self._collection.insert(
                {'key': key, 'content': content}
            )

    def get_object(self, key):
        obj = self._collection.find_one({'key': key}, {'_id': False, 'key': False})
        if obj:
            return obj['content']

    def delete_object(self, key):
        self._collection.remove({'key': key})

    def find(self, fields):
        find_fields = {'content.%s' % k: v for k, v in fields.items()}
        for doc in self._collection.find(find_fields):
            yield doc

    def find_one(self, fields):
        find_fields = {'content.%s' % k: v for k, v in fields.items()}
        return self._collection.find_one(find_fields)

    def __getitem__(self, item):
        return self.get_object(item)

    def __contains__(self, item):
        return self._collection.find({'key': item}).count() > 0

    def __iter__(self):
        for doc in self._collection.find(fields={'key': True, '_id': False}):
            yield doc['key']

    def keys(self):
        return list(self)

class MongoStorage(StorageBase):
    def __init__(self, db):
        self._db = db

    def get_bucket(self, name):
        try:
            self._db.validate_collection(name)
            return MongoBucket(self._db[name])
        except OperationFailure:
            return MongoBucket(self._db.create_collection(name))

    def __getitem__(self, item):
        return self.get_bucket(item)

    def delete(self, bucket):
        if isinstance(bucket, str):
            return self._db.drop_collection(bucket)
        elif isinstance(bucket, MongoBucket):
            return self._db.drop_collection(bucket.name)
        else:
            raise KeyError('No such bucket: {0}'.format(bucket))

    def __contains__(self, item):
        return item in self._db.collection_names()
