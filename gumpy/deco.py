# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import functools

from .framework import (
    ServiceReference, _ManagerHelper, binder, unbinder,
    activator, deactivator, ServiceUnavaliableError)

activate = lambda func: _ManagerTypeDefinition(activator)(func)
deactivate = lambda func: _ManagerTypeDefinition(deactivator)(func)

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

class _MultiElementSettingsDeco(_SettingsDeco):
    def merge_settings(self, helper_settings):
        for k, v in self._settings.items():
            if k in helper_settings:
                hv = helper_settings[k]
                if isinstance(helper_settings[k], set):
                    hv.add(v)
                else:
                    helper_settings[k] = {v, hv}
            else:
                helper_settings[k] = {v} if not isinstance(v, set) else v
        return helper_settings

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

provide = lambda resource: _MultiElementSettingsDeco(provides=resource)
service = lambda name: _ManagerTypeDefinition(ServiceReference)(name) if not isinstance(name, str) else _ManagerTypeDefinition(ServiceReference, name=name)

def require(*service_names, **service_dict):
    def deco(func):
        def injected_func(self, *args, **kwds):
            _args = list(args)
            _kwds = kwds.copy()
            timeout = _kwds.get('__timeout__', 0)
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
            return binder(instance, self._func, self._resource_uri)
        else:
            raise TypeError('Service instance is needed for a binder')

class _UnbinderHelper(object):
    def __init__(self, func, resource_uri):
        self._func = func
        self._resource_uri = resource_uri
    def __get__(self, instance, owner):
        if instance:
            return unbinder(instance, self._func, self._resource_uri)
        else:
            raise TypeError('Service instance is needed for a unbinder')

bind = lambda uri: functools.partial(_BinderHelper, resource_uri=uri)
unbind = lambda uri: functools.partial(_UnbinderHelper, resource_uri=uri)