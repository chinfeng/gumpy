# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

class BucketBase(object):
    def drop(self):
        raise NotImplementedError

    def put(self, entity):
        raise NotImplementedError

    def get(self, stub):
        raise NotImplementedError

    def delete(self, stub):
        raise NotImplementedError

    def update(self, entity):
        raise NotImplementedError

    def __contains__(self, item):
        raise NotImplementedError

    def __getitem__(self, item):
        return self.get(item)

class StorageBase(object):
    def create_bucket(self, name, index=()):
        raise NotImplementedError

    def get_bucket(self, name):
        raise NotImplementedError

    def drop(self, bucket):
        raise NotImplementedError

    def __contains__(self, item):
        raise NotImplementedError

    def __getitem__(self, item):
        return self.get_bucket(item)
