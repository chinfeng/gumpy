# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import functools

from .framework import (
    Consumer, Annotation, ServiceAnnotation, Task,
    EventSlot, Activator, Deactivator, ServiceUnavaliableError)

def require(*service_names, **service_dict):
    def deco(func):
        def injected_func(self, *args, **kwds):
            _args = list(args)
            _kwds = kwds.copy()
            for sn in service_names:
                try:
                    _args.append(self.__context__.get_service(sn))
                except ServiceUnavaliableError:
                    _args.append(None)
            for k, v in service_dict.items():
                try:
                    _kwds[k] = self.__context__.get_service(v)
                except ServiceUnavaliableError:
                    _kwds[k] = None
            return func(self, *_args, **_kwds)
        return injected_func
    return deco

class _ConsumerHelper(object):
    def __init__(self, fn, resource_uri, cardinality):
        assert(cardinality in ('0..1', '0..n', '1..1', '1..n'))
        self._fn = fn
        self._resource_uri = resource_uri
        self._cardinality = cardinality
        self._unbind_fn = lambda instance: None
        self._consumers = {}
    def __get__(self, instance, owner):
        if instance:
            _id = id(instance)
            if _id not in self._consumers:
                self._consumers[_id] = Consumer(instance, self._fn, self._unbind_fn, self._resource_uri, self._cardinality)
            return self._consumers[_id]
        else:
            raise TypeError('Service instance is needed for a binder')
    def unbind(self, fn):
        self._unbind_fn = fn
        return self

bind = lambda resource, cardinality='1..n': functools.partial(_ConsumerHelper, resource_uri=resource, cardinality=cardinality)

class _EventHepler(object):
    def __init__(self, func):
        self._func = func
    def __get__(self, instance, owner):
        if instance:
            return EventSlot(instance, self._func)
        else:
            raise TypeError('Service instance needed for event ')

event = _EventHepler

def configuration(**config_map):
    def deco(func):
        def configuration_injected_func(self, *args, **kwds):
            _kwds = kwds.copy()
            config = self.__reference__.__context__.configuration
            for p, c in config_map.items():
                try:
                    if isinstance(c, str):
                        ck, default = c, None
                    elif isinstance(c, (tuple, list)) and isinstance(c[0], str):
                        ck, default = c[0], c[1] if len(c) > 1 else None
                    else:
                        break
                    _kwds[p] = config.get(ck, default)
                except KeyError:
                    pass
            return func(self, *args, **_kwds)
        return configuration_injected_func
    return deco

class activate(Annotation):
    @property
    def subject(self):
        return Activator(self._subject)

class deactivate(Annotation):
    @property
    def subject(self):
        return Deactivator(self._subject)

provide = lambda provides: functools.partial(Annotation, provides=provides)
service = lambda name: ServiceAnnotation(name) if not isinstance(name, str) else functools.partial(ServiceAnnotation, name=name)

class _TaskHelper(object):
    def __init__(self, fn):
        self._fn = fn
    def __get__(self, instance, owner):
        if instance:
            return Task(self._fn, instance)
        else:
            raise TypeError('Service instance is needed for a task')

task = _TaskHelper