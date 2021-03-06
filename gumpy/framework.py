# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import zipfile
import os
import functools
import itertools
import zipimport
import threading
import collections

try:
    import ConfigParser as configparser
except ImportError:
    import configparser
try:
    from queue import Queue
except ImportError:
    from Queue import Queue
try:
    try:
        from importlib import reload
    except ImportError:
        from imp import reload
except ImportError:
    pass
try:
    from importlib.machinery import SourceFileLoader

    load_source = lambda fullname, path: SourceFileLoader(fullname, path).load_module()
except ImportError:
    from imp import load_source
from importlib import import_module
from .configuration import LocalConfiguration
from .executor import Executor
from inspect import isgeneratorfunction
import types

import logging

logger = logging.getLogger(__name__)


def async(func):
    def _async_callable(instance, *args, **kwargs):
        if hasattr(instance, '__executor__'):
            method = types.MethodType(func, instance)
            return instance.__executor__.call(functools.partial(method, *args, **kwargs))
        else:
            return func

    return _async_callable


_immutable_prop = lambda v: property(lambda self, value=v: value)
_uri_class = collections.namedtuple('GumURI', ('host', 'port', 'bundle', 'service'))
_subtract_dir = lambda a, b: {an for an in dir(a) if an not in dir(b) and not an.startswith('_')}
_BUNDLE_LEVEL = 0
_SERVICE_LEVEL = 1


def service_uri(uri, pwd_level=_SERVICE_LEVEL):
    if uri.startswith('gum://'):
        # absolute uri like:
        # gum://host:port/bundle:service
        location, entity = uri[6:].split('/')
        loc_list = location.split(':')
        host = loc_list.pop(0)
        port = int(loc_list.pop(0)) if loc_list else 3040
        entity_list = entity.split(':')
        bundle = entity_list.pop(0)
        service = entity_list.pop(0) if entity_list else None
    else:
        # relative uri like:
        # service
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


class Annotation(object):
    def __init__(self, subject, **metadata):
        if isinstance(subject, Annotation):
            self._subject = subject._subject
            self._nested = subject
            subject._nesting = self
        else:
            self._subject = subject
            self._nested = None
        self._nesting = None
        self._metadata = metadata

    def __call__(self, *args, **kwargs):
        return self._subject(*args, **kwargs)

    @property
    def nesting(self):
        return self._nesting

    @property
    def nested(self):
        return self._nested

    @property
    def root_nesting(self):
        return self.nesting.root_nesting if self.nesting else self

    @property
    def subject(self):
        if self._nested:
            return self._nested.subject
        else:
            return self._subject

    @property
    def metadata(self):
        data_items = self._other_metadata_items()
        metadata = {}
        for k, v in data_items:
            if k in metadata:
                if isinstance(metadata[k], list):
                    metadata[k].append(v)
                else:
                    metadata[k] = [metadata[k], v]
            else:
                metadata[k] = v
        return metadata

    def _other_metadata_items(self, annotation=None):
        s = annotation or self
        for item in s._metadata.items():
            yield item
        if s._nested:
            for item in self._other_metadata_items(s._nested):
                yield item


class ServiceAnnotation(Annotation):
    def __init__(self, subject, name=None):
        super(self.__class__, self).__init__(subject, name=name)

    @property
    def subject(self):
        metadata = self.root_nesting.metadata
        return ServiceReferenceFactory(self._subject, metadata.get('name'), metadata.get('provides', None))


class ServiceReferenceFactory(object):
    def __init__(self, cls, name=None, provides=None):
        self._cls = cls
        self._name = name
        self._provides = provides

    def create(self, bundle):
        return ServiceReference(bundle, self._cls, self._name, self._provides)


class _Callable(object):
    def __init__(self, func):
        if callable(func):
            self._func = func
        else:
            raise RuntimeError('need a callable object')

    def __call__(self, *args, **kwargs):
        self._func(*args, **kwargs)


class Activator(_Callable):
    def __init__(self, func):
        super(self.__class__, self).__init__(func)


class Deactivator(_Callable):
    def __init__(self, func):
        super(self.__class__, self).__init__(func)


class Task(object):
    def __init__(self, fn, instance):
        self._fn = fn
        self._instance = instance

    def __call__(self, *args, **kwargs):
        method = types.MethodType(self._fn, self._instance)
        if isgeneratorfunction(method):
            for n in method(*args, **kwargs):
                yield n
        else:
            yield method(*args, **kwargs)

    def spawn(self, *args, **kwargs):
        method = types.MethodType(self._fn, self._instance)
        if hasattr(self._instance, '__executor__'):
            extr = self._instance.__executor__
        else:
            extr = kwargs.pop('__executor__', None)
        if extr:
            extr.call(functools.partial(method, *args, **kwargs))
        else:
            raise RuntimeError('no executor specify for {0}'.format(self._fn.__name__))


class Consumer(object):
    def __init__(self, instance, bind_fn, unbind_fn, resource_uri, cardinality):
        self._instance = instance
        self._bind_fn = bind_fn
        self._unbind_fn = unbind_fn
        self._resource_uri = resource_uri
        self._optionality, self._multiplicity = cardinality.split('..')
        self._consumed_resources = set()

    def bind(self, resource_reference):
        try:
            if all((
                    (self.match(resource_reference)),
                    (self._instance is not resource_reference),
                    (not self.is_filled()),
                    (resource_reference not in self._consumed_resources)
            )):
                self._consumed_resources.add(resource_reference)
                self._bind_fn(self._instance, resource_reference.get_service())
                return True
            else:
                return False
        except BaseException as err:
            logger.exception(err)
            return False

    def unbind(self, resource_reference):
        try:
            if resource_reference in self._consumed_resources:
                self._consumed_resources.remove(resource_reference)
                self._unbind_fn(self._instance, resource_reference.get_service())
                return True
            else:
                return False
        except BaseException as err:
            logger.exception(err)
            return False

    def match(self, reference):
        return self.resource_uri in reference.provides

    @property
    def __reference__(self):
        return self._instance.__reference__

    @property
    def resource_uri(self):
        return self._resource_uri

    @property
    def is_satisfied(self):
        return len(self._consumed_resources) >= int(self._optionality)

    def is_filled(self):
        return bool(self._consumed_resources) and self._multiplicity == '1'


class EventSlot(object):
    def __init__(self, instance, func):
        self._name = func.__name__
        self._instance = instance
        self._func = func

    def call(self, *args, **kwargs):
        return self._func(self._instance, *args, **kwargs)

    @property
    def name(self):
        return self._name


class _EventProxy(object):
    def __init__(self, events=None):
        self._events = events or set()

    def send(self, *args, **kwargs):
        for e in self._events:
            e.call(*args, **kwargs)


class _EventManager(object):
    def __init__(self, owner):
        self._owner = owner

    def __getattr__(self, key):
        return _EventProxy(
            (e for e in (self._owner.events() or set()) if e.name == key)
        )

    def __getitem__(self, item):
        return self.__getattr__(item)


class Requirement(object):
    def __init__(self, instance, fn, service_names, service_dict):
        self._instance = instance
        self._fn = fn
        self._service_names = service_names
        self._service_dict = service_dict

    def __call__(self, *args, **kwargs):
        ctx = self._instance.__context__
        _args = list(args)
        _kwargs = kwargs.copy()
        for sn in self._service_names:
            _args.append(ctx.get_service(sn))
        for k, v in self._service_dict.items():
            try:
                _kwargs[k] = ctx.get_service(v)
            except ServiceUnavaliableError:
                _kwargs[k] = None
        return self._fn(self._instance, *_args, **_kwargs)

    def check_satisfied(self, ctx):
        return all(itertools.chain(
            (ctx.get_service_reference(sn).is_avaliable for sn in self._service_names),
            (ctx.get_service_reference(sn).is_avaliable for sn in self._service_dict.values()),
        ))


class ServiceReference(object):
    def __init__(self, bundle, cls, name=None, provides=None):
        self.__context__ = bundle
        self._cls = cls
        self._name = name or cls.__name__
        if isinstance(provides, (list, tuple)):
            self._provides = set(provides)
        elif isinstance(provides, set):
            self._provides = provides
        elif provides is not None:
            self._provides = {provides}
        else:
            self._provides = set()
        self._instance = None

        self._consumers = set()
        self._events = set()
        self._providing_consumers = set()

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

    @property
    def events(self):
        return self._events

    @property
    def is_avaliable(self):
        return bool(self._instance)

    @property
    def is_satisfied(self):
        return self._instance and all(c.is_satisfied for c in self._consumers)

    @property
    def __framework__(self):
        return self.__context__.__framework__

    @property
    def __executor__(self):
        return self.__context__.__framework__.__executor__

    def start(self):
        if not self._instance:
            if isinstance(self._cls, type):
                instance = self._cls.__new__(self._cls)
                instance.__context__ = self.__context__
                instance.__framework__ = self.__framework__
                instance.__executor__ = self.__executor__
                instance.__reference__ = self
                instance.__init__()
            elif isinstance(self._cls, types.FunctionType):
                kwargs = {}
                varnames = self._cls.__code__.co_varnames
                if '__context__' in varnames:
                    kwargs['__context__'] = self.__context__
                if '__framework__' in varnames:
                    kwargs['__framework__'] = self.__framework__
                if '__executor__' in varnames:
                    kwargs['__executor__'] = self.__executor__
                if '__reference__' in varnames:
                    kwargs['__reference__'] = self
                instance = self._cls(**kwargs)
                instance.__context__ = self.__context__
                instance.__framework__ = self.__framework__
                instance.__executor__ = self.__executor__
                instance.__reference__ = self
            instance_dir = _subtract_dir(instance, object)
            if 'on_start' in instance_dir:
                instance.on_start()
            self._instance = instance
            self._events = set(filter(
                lambda obj: isinstance(obj, EventSlot),
                (getattr(instance, an) for an in instance_dir)))
            self._consumers = set(filter(
                lambda obj: isinstance(obj, Consumer),
                (getattr(instance, an) for an in instance_dir)))

            if self._consumers:
                for c in self._consumers:
                    self.__framework__.digest(c)
            elif self._provides:
                self.__framework__.digest(self)

    def stop(self):
        if self._instance:
            if self._provides:
                self.__framework__.dismiss(self)
            self._consumers = set()
            self._events = set()
            if 'on_stop' in dir(self._instance):
                self._instance.on_stop()
            del self._instance
            self._instance = None

    def get_service(self):
        if self._instance:
            return self._instance
        else:
            raise ServiceUnavaliableError('{0}:{1}'.format(self.__context__.name, self._name))

    def check_requirement(self):
        instance_dir = dir(self._cls)
        requirements = filter(
            lambda r: r is not None and isinstance(r, Requirement),
            (getattr(self._cls, an) for an in instance_dir)
        )
        return all(
            filter(lambda r: r.check_satisfied(self.__context__), requirements)
        )


class BundleContext(object):
    ST_INSTALLED = _immutable_prop((0, 'INSTALLED'))
    ST_RESOLVED = _immutable_prop((1, 'RESOLVED'))
    ST_STARTING = _immutable_prop((2, 'STARTING'))
    ST_ACTIVE = _immutable_prop((3, 'ACTIVE'))
    ST_STOPING = _immutable_prop((4, 'STOPING'))
    ST_UNINSTALLED = _immutable_prop((5, 'UNINSTALLED'))

    def __init__(self, framework, uri):
        self._framework = framework
        self._uri = uri
        self._state = self.ST_INSTALLED
        self._service_references = {}
        self._activator = lambda: None
        self._deactivator = lambda: None
        self._module = None

        self._events = set()
        self._event_manager = _EventManager(self)

        abspath = os.path.abspath(uri)
        if os.path.isfile(abspath):
            fn, ext = os.path.splitext(os.path.basename(abspath))
            if ext == '.py':
                self._module = load_source(fn, abspath)
            elif ext == '.zip':
                self._module = zipimport.zipimporter(abspath).load_module(fn)
            self._path = abspath
        else:
            self._module = import_module(uri)
            reload(self._module)
            self._path = os.path.dirname(self._module.__file__)

        name = getattr(self._module, '__gum__', None)
        name = name or getattr(self._module, '__symbol__', None)
        self._name = name or self._module.__name__

        for attr_name in _subtract_dir(self._module, types.ModuleType):
            attr = getattr(self._module, attr_name)
            if isinstance(attr, Annotation):
                subject = attr.subject
                if isinstance(subject, Activator):
                    self._activator = subject
                elif isinstance(subject, Deactivator):
                    self._deactivator = subject
                elif isinstance(subject, ServiceReferenceFactory):
                    sr = subject.create(self)
                    self._service_references[sr.name] = sr

        self._state = self.ST_RESOLVED

    @property
    def __executor__(self):
        return self._framework.__executor__

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

    @property
    def configuration(self):
        return self._framework.configuration[self._name]

    @property
    def event_manager(self):
        return self._event_manager

    @property
    def em(self):
        return self._event_manager

    def events(self):
        if self.state == self.ST_ACTIVE:
            for sr in self.service_references.values():
                for e in sr.events: yield e
        else:
            raise StopIteration

    @async
    def start(self):
        if self._state == self.ST_RESOLVED:
            try:
                self._state = self.ST_STARTING
                self._activator()
                sr_list = collections.deque(self._service_references.values())
                while sr_list:
                    sr = sr_list.popleft()
                    if sr.check_requirement():
                        sr.start()
                    else:
                        sr_list.append(sr)
                    yield
                self._state = self.ST_ACTIVE
            except BaseException as err:
                logger.exception(err)
                self._state = self.ST_RESOLVED
                raise
        elif self._state == self.ST_STARTING:
            pass
        else:
            raise BundleUnavailableError('bundle {0} cannot start while {1}'.format(self.name, self.state[1]))

    @async
    def stop(self):
        if self._state == self.ST_ACTIVE:
            self._state = self.ST_STOPING
            for sr in self._service_references.values():
                sr.stop()
            self._deactivator()
            self._state = self.ST_RESOLVED
        elif self._state == self.ST_STOPING:
            pass
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

    def get_service(self, uri):
        sr = self.get_service_reference(uri)
        return sr.get_service() if sr else None

    def get(self, uri):
        u = service_uri(uri)
        if u.service:
            return self.__framework__.bundles[u.bundle].get_service_reference_by_name(u.service)
        else:
            return self.__framework__.bundles[u.bundle]


class Framework(object):
    def __init__(self, configuration=None, repo_path=None):
        self.__executor__ = Executor()
        self._repo_path = repo_path
        self._bundles = {}
        self._lock = threading.Lock()
        self._configuration = configuration or LocalConfiguration()
        self._state_conf = self.configuration['.state']
        self._event_manager = _EventManager(self)

    def dismiss(self, producer):
        for c in self.consumers():
            if c.unbind(producer) and (not c.is_filled()):
                # find another provider if instance become unfilled
                for p in filter(lambda sr, dismiss=producer: sr is not dismiss, self.producers()):
                    c.bind(p)

    def digest(self, entry):
        if isinstance(entry, ServiceReference):
            self._digest_from_producer(entry)
        elif isinstance(entry, Consumer):
            self._digest_from_consumer(entry)

    def _digest_from_producer(self, producer):
        if not producer.provides:
            return

        work_list = [producer, ]
        while work_list:
            p = work_list.pop(0)
            if p.is_satisfied:
                for c in self.consumers():
                    if c.bind(p) and c.__reference__.provides:
                        work_list.append(c.__reference__)

    def _digest_from_consumer(self, consumer):
        for p in self.producers():
            if p.is_satisfied:
                consumer.bind(p)
        self._digest_from_producer(consumer.__reference__)

    @property
    def repo_path(self):
        return self._repo_path

    @property
    def bundles(self):
        return self._bundles

    @property
    def configuration(self):
        return self._configuration

    def events(self):
        for bdl in self.bundles.values():
            for e in bdl.events():
                yield e

    @property
    def event_manager(self):
        return self._event_manager

    @property
    def em(self):
        return self._event_manager

    def producers(self):
        for bdl in self._bundles.values():
            for sr in bdl.service_references.values():
                if sr.is_avaliable and sr.provides: yield sr

    def consumers(self):
        for bdl in self._bundles.values():
            for sr in bdl.service_references.values():
                if sr.is_avaliable:
                    for c in sr.consumers:
                        yield c

    def get_bundle(self, uri, default=None):
        return self._bundles.get(uri, default)

    def get_repo_list(self):
        repo_list = {}
        is_bundle = lambda co: 'gumpy.deco' in co.co_names or '__gum__' in co.co_names
        for filename in os.listdir(self._repo_path):
            bn, ext = os.path.splitext(filename)
            if os.path.isdir(os.path.join(self._repo_path, filename)):
                # package
                init_pt = os.path.join(self._repo_path, filename, '__init__.py')
                if os.path.exists(init_pt):
                    with open(init_pt) as fd:
                        code = compile(fd.read(), init_pt, 'exec')
                        if is_bundle(code):
                            repo_list[filename] = dict(tp='PKG', uri=filename)
            elif ext == '.py':
                # module
                mod_pt = os.path.join(self._repo_path, filename)
                with open(mod_pt) as fd:
                    code = compile(fd.read(), mod_pt, 'exec')
                    if is_bundle(code):
                        repo_list[filename] = dict(tp='MOD', uri=bn)
            elif ext == '.zip':
                # zip
                init_pt = '/'.join((bn, '__init__.py'))
                with zipfile.ZipFile(os.path.join(self.repo_path, filename)) as zf:
                    code = compile(
                        zf.read(init_pt),
                        os.path.join(self._repo_path, filename, init_pt),
                        'exec'
                    )
                    if is_bundle(code):
                        repo_list[filename] = dict(tp='ZIP', uri=filename)
        return repo_list

    @async
    def install_bundle(self, uri):
        bdl = BundleContext(self, uri)
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

    def get_service(self, name):
        service = self.get_service_reference(name)
        return service.get_service() if service else None

    def get(self, uri):
        u = service_uri(uri, _BUNDLE_LEVEL)
        if u.service:
            return self._bundles[u.bundle].get_service_reference_by_name(u.service)
        else:
            return self._bundles[u.bundle]

    @async
    def restore_state(self):
        uri_dict = {bdl.uri: bdl for bdl in self.bundles.values()}
        invalid_uris = set()
        for uri, start in self._state_conf.items():
            try:
                if uri not in uri_dict:
                    def _start_later(f, b):
                        if f:
                            b.start()

                    f = self.install_bundle(uri)
                    f.add_consumer(functools.partial(_start_later, start))
                else:
                    bdl = uri_dict[uri]
                    if start:
                        bdl.start()
            except BaseException as err:
                logger.warning('bundle {0} init error:'.format(uri))
                logger.exception(err)
                invalid_uris.add(uri)
        for uri in invalid_uris:
            self._state_conf.pop(uri)

    def stop(self):
        for bdl in self.bundles.values():
            bdl.stop()
        self._save_status()

    def terminate(self):
        self._save_status()

    def _save_status(self):
        for bdl in self.bundles.values():
            self._state_conf[bdl.uri] = (bdl.state == bdl.ST_ACTIVE)
        self.configuration.close()

    def call(self, fn, *args, **kwargs):
        self.__executor__.call(functools.partial(fn, *args, **kwargs))


class DefaultFrameworkSingleton(object):
    _default_framework = None

    def __call__(self):
        if not self._default_framework:
            self._default_framework = Framework()
        return self._default_framework


default_framework = DefaultFrameworkSingleton()
