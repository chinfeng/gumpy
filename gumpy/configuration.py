# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import json

import logging

logger = logging.getLogger(__name__)


class Configuration(object):
    def reload(self):
        raise NotImplementedError

    def persist(self):
        raise NotImplementedError


class _DictObject(dict):
    def __init__(self, other=None):
        super(self.__class__, self).__init__(other or {})
        if other:
            self.update(other)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self.get(key)


class _LocalDocument(object):
    def __init__(self, fn=None):
        super(self.__class__, self).__setattr__('_fn', fn)
        try:
            with open(fn, 'r') as fd:
                super(self.__class__, self).__setattr__(
                    '_dict_object',
                    _DictObject(json.load(fd, object_hook=lambda dct: _DictObject(dct) if type(dct) is dict else dct)))
        except BaseException as err:
            super(self.__class__, self).__setattr__(
                '_dict_object', _DictObject())

    def __setattr__(self, key, value):
        if key in dir(self):
            super(self.__class__, self).__setattr__(key, value)
        else:
            self._dict_object[key] = value

    def __getattr__(self, key):
        try:
            return super(self.__class__, self).__getattr__(key)
        except AttributeError:
            return self._dict_object[key]

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, item):
        return self.__getattr__(item)

    def pop(self, key):
        return self._dict_object.pop(key)

    def get(self, key, default=None):
        return self._dict_object.get(key, default)

    def set(self, key, value):
        return self._dict_object.set(key, value)

    def keys(self):
        return self._dict_object.keys()

    def values(self):
        return self._dict_object.values()

    def items(self):
        return self._dict_object.items()

    def __iter__(self):
        return self._dict_object.__iter__()

    def persist(self):
        if self._fn:
            with open(self._fn, 'w') as fd:
                json.dump(self._dict_object, fd)

    def close(self):
        self.persist()

    def __del__(self):
        self.close()


class LocalConfiguration(Configuration):
    def __init__(self, path=None):
        if path and os.path.isdir(path):
            self._dir = os.path.abspath(path)
        else:
            self._dir = None
        self._docs = {}

    def __getattr__(self, key):
        if key in self._docs:
            return self._docs[key]

        if self._dir:
            fn = os.path.join(self._dir, key)
            self._docs[key] = _LocalDocument(fn)
        else:
            self._docs[key] = _LocalDocument()
        return self._docs[key]

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __del__(self):
        self.close()

    def close(self):
        for doc in self._docs.values():
            doc.close()

    def persist(self):
        for doc in self._docs.values():
            doc.persist()

    def reload(self):
        if self._dir:
            for key in self._docs:
                fn = os.path.join(self._dir, key)
                self._docs[key] = _LocalDocument(fn)
        else:
            for key in self._docs:
                self._docs[key] = _LocalDocument()
