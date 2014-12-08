# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

class BucketBase(object):
    def delete(self):
        raise NotImplementedError

    def put_object(self, key, content, metadata=None):
        raise NotImplementedError

    def get_object(self, key):
        raise NotImplementedError

    def delete_object(self, key):
        raise NotImplementedError

    def get_object_content(self, key):
        raise NotImplementedError

    def __contains__(self, item):
        raise NotImplementedError

    def __getitem__(self, item):
        raise NotImplementedError

class StorageBase(object):
    def get_bucket(self, name):
        raise NotImplementedError

    def delete(self, bucket):
        raise NotImplementedError

    def __contains__(self, item):
        raise NotImplementedError

    def __getitem__(self, item):
        raise NotImplementedError
