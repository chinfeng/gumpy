# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import imp
import zipimport
import itertools
import threading
import collections
from .executor import ExecutorHelper, async

try:
    from itertools import izip_longest
except ImportError:
    from itertools import zip_longest as izip_longest

import logging
logger = logging.getLogger(__name__)

_immutable_prop = lambda v: property(lambda self, value=v: value)
_uri_class = collections.namedtuple('GumURI', ('host', 'port', 'bundle', 'service'))
_BUNDLE_LEVEL = 0
_SERVICE_LEVEL = 1

def service_uri(uri, pwd_level=_SERVICE_LEVEL):
    if uri.startswith('gum://'):
        # absolute uri like:
        #   gum://host:port/bundle:service
        location, entity = uri[6:].split('/')
        loc_list = location.split(':')
        host = loc_list.pop(0)
        port = int(loc_list.pop(0)) if loc_list else 3040
        entity_list = entity.split(':')
        bundle = entity_list.pop(0)
        service = entity_list.pop(0) if entity_list else None
    else:
        # relative uri like:
        #   service
        #   bundle:service
        #   host/bundle:service
        u_list = uri.split('/')
        entity = u_list.pop()
        location = u_list.pop() if u_list else None
        if location:
            loc_list = location.split(':')
            host = loc_list.pop(0)
            port = int(loc_list.pop(0)) if loc_list else 3040
        else:
            host = port = None
        entity_list = entity.split(':')
        if len(entity_list) == 1:
            if pwd_level == _BUNDLE_LEVEL:
                bundle = entity_list[0]
                service = None
            else:
                bundle = None
                service = entity_list[0]
        else:
            bundle, service = entity_list
    return _uri_class(host, port, bundle, service)

class BundleInstallError(RuntimeError):
    pass

class BundleUnavailableError(RuntimeError):
    pass

class BundleReloadError(RuntimeError):
    pass

class ServiceUnavaliableError(RuntimeError):
    pass

class _ManagerHelper(object):
    def __init__(self, managed_object, manager_type=None, settings=None):
        self._settings = settings or {}
        self._managed_object = managed_object
        self._manager_type = manager_type
    @property
    def settings(self):
        return self._settings
    @settings.setter
    def settings(self, sts):
        self._settings = sts
    @property
    def manager_type(self):
        return self._manager_type
    @manager_type.setter
    def manager_type(self, tp):
        self._manager_type = tp
    def to_managed(self, **kwds):
        tp = self.manager_type
        return tp(self._managed_object, **dict(self.settings, **kwds)) if tp else None

class _callable(object):
    def __init__(self, func):
        if callable(func):
            self._func = func
        else:
            raise RuntimeError('need a callable object')
    def __call__(self, *args, **kwds):
        self._func(*args, **kwds)

class activator(_callable):
    def __init__(self, func):
        super(self.__class__, self).__init__(func)

class deactivator(_callable):
    def __init__(self, func):
        super(self.__class__, self).__init__(func)

class _consumer(object):
    def __init__(self, instance, func, resource_uri):
        self._instance = instance
        self._func = func
        self._resource_uri = resource_uri
    def __call__(self, resource_reference):
        if self.match(resource_reference):
            return self._func(self._instance, resource_reference.get_service())
    def match(self, reference):
        return self.resource_uri in reference.provides
    @property
    def resource_uri(self):
        return self._resource_uri

class binder(_consumer):
    pass

class unbinder(_consumer):
    pass

class ServiceReference(object):
    def __init__(self, cls, name=None, provides=None):
        self._cls = cls
        self._name = name or cls.__name__
        self._provides = provides or set()
        self._instance = None
        self._evt = threading.Event()

        self.__context__ = None
        self.__framework__ = None
        self._consumers = None

    @property
    def name(self):
        return self._name

    @property
    def provides(self):
        return self._provides

    @property
    def cls(self):
        return self._cls

    @property
    def consumers(self):
        return self._consumers

    def start(self):
        if not self._instance:
            instance = self._cls()
            instance.__context__ = self.__context__
            instance.__framework__ = self.__framework__
            instance.__reference__ = self
            if 'on_start' in dir(instance):
                instance.on_start()
            self._instance = instance
            self._evt.set()
            members = (getattr(instance, an) for an in dir(instance))
            self._consumers = set(filter(lambda obj: isinstance(obj, _consumer), members))
            self.__framework__.register_consumers(self._consumers)
            self.__framework__.register_producer(self)

    def stop(self):
        if self._instance:
            self.__framework__.unregister_consumers(self._consumers)
            self.__framework__.unregister_producer(self)
            self._consumers = None
            if 'on_stop' in dir(self._instance):
                self._instance.on_stop()
            del self._instance
            self._instance = None
            self._evt.clear()

    def get_service(self, timeout=None):
        if self._evt.wait(timeout):
            return self._instance
        else:
            raise ServiceUnavaliableError('{0}:{1}'.format(self.__context__.name, self._name))

class BundleContext(ExecutorHelper):
    ST_INSTALLED = _immutable_prop((0, 'INSTALLED'))
    ST_RESOLVED = _immutable_prop((1, 'RESOLVED'))
    ST_STARTING = _immutable_prop((2, 'STARTING'))
    ST_ACTIVE = _immutable_prop((3, 'ACTIVE'))
    ST_STOPING = _immutable_prop((4, 'STOPING'))
    ST_UNINSTALLED = _immutable_prop((5, 'UNINSTALLED'))

    def __init__(self, framework, uri):
        ExecutorHelper.__init__(self, framework.__executor__)
        self._framework = framework
        self._uri = uri
        self._state = self.ST_INSTALLED
        self._service_references = {}
        self._activator = lambda: None
        self._deactivator = lambda: None
        self._module = None

        abspath = os.path.abspath(uri)
        if os.path.isfile(abspath):
            fn, ext = os.path.splitext(os.path.basename(abspath))
            if ext == '.py':
                self._module = imp.load_source(fn, abspath)
            elif ext == '.zip':
                self._module = zipimport.zipimporter(abspath).load_module(fn)
            self._path = abspath
        else:
            module_name = uri.split('.')[-1]
            self._module = __import__(uri, fromlist=(module_name, ))
            self._path = os.path.dirname(self._module.__file__)

        if hasattr(self._module, '__symbol__'):
            self._name = self._module.__symbol__
        else:
            self._name = self._module.__name__

        for attr_name in dir(self._module):
            attr = getattr(self._module, attr_name)
            if isinstance(attr, _ManagerHelper):
                manager = attr.to_managed()
                if isinstance(manager, activator):
                    self._activator = manager
                elif isinstance(manager, deactivator):
                    self._deactivator = manager
                elif isinstance(manager, ServiceReference):
                    manager.__context__ = self
                    manager.__framework__ = self.__framework__
                    self._service_references[manager.name] = manager

        self._state = self.ST_RESOLVED

    @property
    def path(self):
        return self._path

    @property
    def uri(self):
        return self._uri

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def service_references(self):
        return self._service_references

    @property
    def __framework__(self):
        return self._framework

    @async
    def start(self):
        if self._state == self.ST_RESOLVED:
            self._activator()
            for sr in self._service_references.values():
                sr.start()
            self._state = self.ST_ACTIVE
        else:
            raise BundleUnavailableError('bundle {0} cannot start while {1}'.format(self.name, self.state[1]))

    @async
    def stop(self):
        if self._state == self.ST_ACTIVE:
            for sr in self._service_references.values():
                sr.stop()
            self._deactivator()
            self._state = self.ST_RESOLVED
        else:
            raise BundleUnavailableError('bundle {0} cannot stop while {1}'.format(self.name, self.state[1]))

    def get_service_reference(self, uri):
        u = service_uri(uri)
        if u.bundle:
            return self._framework.bundles[u.bundle].get_service_reference_by_name(u.service)
        else:
            return self.get_service_reference_by_name(u.service)

    def get_service_reference_by_name(self, name):
        if name in self._service_references:
            return self._service_references[name]
        else:
            return None

    def get_service(self, uri, timeout=None):
        sr = self.get_service_reference(uri)
        return sr.get_service(timeout) if sr else None

class Framework(ExecutorHelper):
    def __init__(self):
        ExecutorHelper.__init__(self)
        self._bundles = {}
        self._lock = threading.Lock()
        self._binders = set()
        self._unbinders = set()
        self._producers = set()

    def _consume(self, work_list):
        for consumer, producer in work_list:
            consumer(producer)

    def register_consumers(self, consumers):
        with self._lock:
            binders = {c for c in consumers if isinstance(c, binder)}
            unbinders = {c for c in consumers if isinstance(c, unbinder)}
            self._binders |= binders
            self._unbinders |= unbinders
            work_list = list(itertools.product(binders, self._producers))
        self._consume(work_list)

    def unregister_consumers(self, consumers):
        with self._lock:
            binders = {c for c in consumers if isinstance(c, binder)}
            unbinders = {c for c in consumers if isinstance(c, unbinder)}
            self._binders -= binders
            self._unbinders -= unbinders
            work_list = list(itertools.product(unbinders, self._producers))
        self._consume(work_list)

    def register_producer(self, reference):
        with self._lock:
            work_list = [(binder, reference) for binder in self._binders]
            self._producers.add(reference)
        self._consume(work_list)

    def unregister_producer(self, reference):
        with self._lock:
            work_list = [(unbinder, reference) for unbinder in self._unbinders]
            self._producers.remove(reference)
        self._consume(work_list)

    @property
    def bundles(self):
        return self._bundles

    def get_bundle(self, uri, default=None):
        return self._bundles.get(uri, default)

    @async
    def install_bundle(self, position):
        bdl = BundleContext(self, position)
        self._bundles[bdl.name] = bdl
        return bdl

    def install_bundles(self, tp_list):
        return [self.install_bundle(tp) for tp in tp_list]

    def get_service_reference(self, uri):
        u = service_uri(uri, _BUNDLE_LEVEL)
        if u.bundle in self._bundles:
            return self._bundles[u.bundle].get_service_reference_by_name(u.service)
        else:
            return None

    def get_service(self, name, timeout=None):
        service = self.get_service_reference(name)
        return service.get_service(timeout) if service else None

    def get(self, uri):
        u = service_uri(uri, _BUNDLE_LEVEL)
        if u.service:
            return self._bundles[u.bundle].get_service_reference_by_name(u.service)
        else:
            return self._bundles[u.bundle]

class DefaultFrameworkSingleton(object):
    _default_framework = None

    def __call__(self):
        if not self._default_framework:
            self._default_framework = Framework()
        return self._default_framework

default_framework = DefaultFrameworkSingleton()
