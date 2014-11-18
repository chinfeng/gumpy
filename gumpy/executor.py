# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

try:
    from Queue import Queue
except ImportError:
    from queue import Queue
from collections import deque
import types
import inspect
import threading

import logging
logger = logging.getLogger(__name__)

class TimeoutError(RuntimeError):
    pass

class _Executor(object):
    def submit(self, func, *args, **kwds):
        raise NotImplementedError

    def exclusive_submit(self, func, *args, **kwds):
        raise NotImplementedError

    def wait_until_idle(self):
        raise NotImplementedError

class _Future(object):
    def result(self, timeout=None):
        return NotImplemented

    def exception(self, timeout=None):
        return NotImplemented

    @property
    def done(self):
        return NotImplemented

    def wait(self, timeout=None):
        raise NotImplementedError

    def add_done_callback(self, func, *args, **kwds):
        raise NotImplementedError

class _ThreadFuture(_Future):
    def __init__(self, worker):
        self._evt = threading.Event()
        self._done_callback = []
        self._result = None
        self._worker = worker
        self._exception = None

    def result(self, timeout=None):
        if self._evt.wait(timeout):
            if self._exception:
                raise self._exception
            else:
                return self._result
        else:
            raise TimeoutError('result')

    def set_result(self, result):
        self._result = result
        for func, args, kwds in self._done_callback:
            func(result, *args, **kwds)
        self._evt.set()

    def set_exception(self, exception):
        self._exception = exception
        self._evt.set()

    def exception(self, timeout=None):
        if self._evt.wait(timeout):
            return self._exception
        else:
            raise TimeoutError('exception')

    @property
    def done(self):
        return self._evt.is_set()

    def wait(self, timeout=None):
        return self._evt.wait(timeout)

    def add_done_callback(self, func, *args, **kwds):
        if self.done:
            self._worker.submit(func, self.result, *args, **kwds)
        else:
            self._done_callback.append((func, args, kwds))

class ThreadPoolExecutor(_Executor):
    def __init__(self, worker_size=5):
        super(self.__class__, self).__init__()
        self._worker_queue = Queue()
        self._dispatch_queue = Queue()
        for i in range(worker_size):
            t = threading.Thread(target=self._worker)
            t.setDaemon(True)
            t.start()
        self._dispatcher = threading.Thread(target=self._dispatch)
        self._dispatcher.setDaemon(True)
        self._dispatcher.start()

    def _worker(self):
        while True:
            _func, _args, _kwds, _future = self._worker_queue.get()
            try:
                _future.set_result(_func(*_args, **_kwds))
                self._worker_queue.task_done()
            except BaseException as e:
                # logger.exception(e)
                _future.set_exception(e)

    def _dispatch(self):
        while True:
            func, args, kwds, exclusive, future = self._dispatch_queue.get()
            if exclusive:
                self._worker_queue.join()
                self._worker_queue.put((func, args, kwds, future))
                self._worker_queue.join()
            else:
                self._worker_queue.put((func, args, kwds, future))

    def submit(self, func, *args, **kwds):
        future = _ThreadFuture(self)
        self._dispatch_queue.put((func, args, kwds, False, future))
        return future

    def exclusive_submit(self, func, *args, **kwds):
        future = _ThreadFuture(self)
        self._dispatch_queue.put((func, args, kwds, True, future))
        return future

    def wait_until_idle(self):
        self._worker_queue.join()

class _InlineFuture(_Future):
    def __init__(self, func, args, kwds):
        try:
            self._result = func(*args, **kwds)
            self._exception = None
        except BaseException as e:
            self._result = None
            self._exception = e

    def result(self, timeout=None):
        if self._exception:
            raise self._exception
        else:
            return self._result

    def exception(self, timeout=None):
        return self._exception

    @property
    def done(self):
        return True

    def wait(self, timeout=None):
        return True

    def add_done_callback(self, func, *args, **kwds):
        if self._result:
            func(self._result, *args, **kwds)

class InlineExecutor(_Executor):
    def __init__(self):
        pass

    def submit(self, func, *args, **kwds):
        return _InlineFuture(func, args, kwds)

    def exclusive_submit(self, func, *args, **kwds):
        return _InlineFuture(func, args, kwds)

    def wait_until_idle(self):
        return

class _BaseCoroutineFuture(_Future):
    def __init__(self, executor):
        self._executor = executor
        self._done = False
        self._exception = None
        self._done_callbacks = []
    def result(self, timeout=None):
        return NotImplemented
    def exception(self, timeout=None):
        return self._exception
    @property
    def done(self):
        return self._done
    def add_done_callback(self, fn, *args, **kwds):
        if self.done:
            fn(*args, **kwds)
        else:
            self._done_callbacks.append((fn, args, kwds))
    def set_exception(self, exception):
        self._done = True
        self._exception = exception

class _GeneralCoroutineFuture(_BaseCoroutineFuture):
    def __init__(self, executor):
        super(self.__class__, self).__init__(executor)
    def result(self, timeout=None):
        while not self._done:
            self._executor.step()
        if self._exception:
            raise self._exception
        else:
            return getattr(self, '_result')
    def wait(self, timeout=None):
        while not self._done:
            self._executor.step()
    def send_result(self, result):
        if not self._done:
            setattr(self, '_result', result)
            self._done = True
            for fn, args, kwds in self._done_callbacks:
                fn(result, *args, **kwds)

class _GeneratorCoroutineFuture(_BaseCoroutineFuture):
    def __init__(self, executor):
        super(self.__class__, self).__init__(executor)
        self._result_list = []
        self._got = False
    def result(self, timeout=None):
        for rt in self._result_list:
            yield rt
        while not self._done:
            self._executor.step()
            if self._got:
                self._got = False
                yield self._result_list[-1]
    def wait(self, timeout=None):
        while not self._done:
            self._executor.step()
    def send_result(self, result):
        if not self._done:
            if type(result) is StopIteration or result is StopIteration:
                self._done = True
                for fn, args, kwds in self._done_callbacks:
                    fn(iter(self._result_list), *args, **kwds)
            else:
                self._result_list.append(result)
                self._got = True
        else:
            raise RuntimeError('cannot send result after done.')
    def __iter__(self):
        return self.result()

class CoroutineExecutor(_Executor):
    def __init__(self):
        self._tasks = deque()
    def _generator_wrapper(self, fn, args, kwds):
        yield fn(*args, **kwds)
    def _submit(self, fn, exclusive, args, kwds):
        if inspect.isgeneratorfunction(fn):
            f = _GeneratorCoroutineFuture(self)
            self._tasks.append((fn(*args, **kwds), f, exclusive))
            return f
        else:
            f = _GeneralCoroutineFuture(self)
            self._tasks.append((self._generator_wrapper(fn, args, kwds), f, exclusive))
            return f
    def submit(self, fn, *args, **kwds):
        return self._submit(fn, False, args, kwds)
    def exclusive_submit(self, fn, *args, **kwds):
        return self._submit(fn, True, args, kwds)
    def step(self):
        try:
            gen, f, exclusive = self._tasks.popleft()
        except IndexError:
            return
        try:
            f.send_result(next(gen))
            if exclusive:
                self._tasks.appendleft((gen, f, exclusive))
            else:
                self._tasks.append((gen, f, exclusive))
        except StopIteration:
            f.send_result(StopIteration)
        except BaseException as err:
            f.set_exception(err)
    def wait_until_idle(self):
        while self._tasks:
            self.step()

_default_executor_class = CoroutineExecutor

class ExecutorHelper(object):
    def __init__(self, executor=_default_executor_class()):
        self._executor = executor
    @property
    def __executor__(self):
        return self._executor
    @__executor__.setter
    def __executor__(self, executor):
        self._executor = executor
    def wait_until_idle(self):
        self._executor.wait_until_idle()

def async(func):
    def _async_callable(instance, *args, **kwargs):
        if isinstance(instance, ExecutorHelper):
            method = types.MethodType(func, instance)
            return instance.__executor__.submit(method, *args, **kwargs)
        else:
            return func
    return _async_callable

def exclusive(func):
    def _exclusive_callable(instance, *args, **kwargs):
        if isinstance(instance, ExecutorHelper):
            method = types.MethodType(func, instance)
            return instance.__executor__.exclusive_submit(method, *args, **kwargs)
        else:
            return func
    return _exclusive_callable
