# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import functools
import collections

from .framework import (
    ServiceReference, _ManagerHelper, Binder, Unbinder,
    EventSlot, Activator, Deactivator, ServiceUnavaliableError)

activate = lambda func: _ManagerTypeDefinition(Activator)(func)
deactivate = lambda func: _ManagerTypeDefinition(Deactivator)(func)

class _SettingsDeco(object):
    def __init__(self, **kwds):
        self._settings = kwds
    def __call__(self, wrapped):
        if isinstance(wrapped, _ManagerHelper):
            wrapped.settings = self.merge_settings(wrapped.settings)
            return wrapped
        else:
            return _ManagerHelper(wrapped, settings=self.merge_settings({}))
    def merge_settings(self, helper_settings):
        return dict(helper_settings, **self._settings)

class _RecursiveStringSettingsDeco(_SettingsDeco):
    def _recursive_flat(self, ir):
        if type(ir) is str:
            yield ir
        elif isinstance(ir, collections.Iterable):
            for elm in ir:
                for e in self._recursive_flat(elm):
                    yield e
    def merge_settings(self, helper_settings):
        rt = {}
        for k, v in self._settings.items():
            if k in helper_settings:
                rt[k] = set(self._recursive_flat((v, helper_settings[k])))
            else:
                rt[k] = set(self._recursive_flat(v))
        return rt

class _ManagerTypeDefinition(_SettingsDeco):
    def __init__(self, manager_type, **kwds):
        super(self.__class__, self).__init__(**kwds)
        self._manager_type = manager_type
    def __call__(self, wrapped):
        if isinstance(wrapped, _ManagerHelper):
            wrapped.settings = self.merge_settings(wrapped.settings)
            wrapped._manager_type = self._manager_type
            return wrapped
        else:
            return _ManagerHelper(wrapped, self._manager_type, self.merge_settings({}))

provide = lambda res, *args: _RecursiveStringSettingsDeco(provides=res if not args else (res, ) + args)
service = lambda name: _ManagerTypeDefinition(ServiceReference)(name) if not isinstance(name, str) else _ManagerTypeDefinition(ServiceReference, name=name)

def require(*service_names, **service_dict):
    def deco(func):
        def injected_func(self, *args, **kwds):
            _args = list(args)
            _kwds = kwds.copy()
            timeout = _kwds.get('__timeout__', None)
            for sn in service_names:
                try:
                    _args.append(self.__context__.get_service(sn, timeout))
                except ServiceUnavaliableError:
                    _args.append(None)
            for k, v in service_dict.items():
                try:
                    _kwds[k] = self.__context__.get_service(v, timeout)
                except ServiceUnavaliableError:
                    _kwds[k] = None
            return func(self, *_args, **_kwds)
        return injected_func
    return deco

class _BinderHelper(object):
    def __init__(self, func, resource_uri):
        self._func = func
        self._resource_uri = resource_uri
        self.unbind = functools.partial(_UnbinderHelper, resource_uri=self._resource_uri)
    def __get__(self, instance, owner):
        if instance:
            return Binder(instance, self._func, self._resource_uri)
        else:
            raise TypeError('Service instance is needed for a binder')

class _UnbinderHelper(object):
    def __init__(self, func, resource_uri):
        self._func = func
        self._resource_uri = resource_uri
    def __get__(self, instance, owner):
        if instance:
            return Unbinder(instance, self._func, self._resource_uri)
        else:
            raise TypeError('Service instance is needed for a unbinder')

bind = lambda resource: functools.partial(_BinderHelper, resource_uri=resource)

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
            config = self.__context__.configuration
            for p, c in config_map.items():
                try:
                    if c in config:
                        _kwds[p] = config.get(c)
                except:
                    pass
            return func(self, *args, **_kwds)
        return configuration_injected_func
    return deco