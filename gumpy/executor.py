# -*- coding: utf-8 -*-
__author__ = 'Chinfeng'

from types import GeneratorType
from collections import deque
from inspect import isgeneratorfunction
from functools import partial
from threading import current_thread, Lock, Event, ThreadError
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

def _is_gen(fn):
    return isgeneratorfunction(fn) or (isinstance(fn, partial) and isgeneratorfunction(fn.func))


def _gen(fn):
    if _is_gen(fn):
        for i in fn():
            yield i
    else:
        yield fn()


class _EndOfQueue(object):
    pass


class CloseableQueue(Queue):
    def __init__(self, *args, **kwargs):
        Queue.__init__(self, *args, **kwargs)
        self._close_event = Event()
        self._close_event.clear()

    def close(self):
        self.put(_EndOfQueue())
        self._close_event.set()

    def get(self, block=True, timeout=None):
        r = Queue.get(self, block, timeout)
        self.task_done()
        if isinstance(r, _EndOfQueue):
            self.put(r)
            raise Empty('future has been closed')
        else:
            return r

    def wait(self):
        self._close_event.wait()


class Future(object):
    def __init__(self, executor):
        self._executor = executor
        self._exc = None
        self._done = False
        self._lock = Lock()
        self._consumers = []
        self._error_callbacks = []
        self._result_cache = []

    def set_done(self):
        for c in self._consumers:
            if isinstance(c, GeneratorType):
                c.close()
        self._done = True

    def consume_result(self, result):
        if self._done:
            raise RuntimeError('result receive after future close')
        else:
            for c in self._consumers:
                if isinstance(c, GeneratorType):
                    c.send(result)
                else:
                    c(result)
            self._result_cache.append(result)

    def set_exception(self, exc):
        self._exc = exc
        for cb in self._error_callbacks:
            cb(exc)
        self.set_done()

    def add_consumer(self, callback):
        if _is_gen(callback):
            c = callback()
            next(c)
            for result in self._result_cache:
                c.send(result)
        else:
            c = callback
            for result in self._result_cache:
                c(result)
        self._consumers.append(c)

    def add_error_callback(self, callback):
        if self._exc:
            for cb in self._error_callbacks:
                cb(self._exc)
        else:
            self._error_callbacks.append(callback)

    def result_queue(self):
        queue = CloseableQueue()
        def _put_to_sync_queue(q):
            try:
                while True:
                    q.put((yield))
            finally:
                q.close()

        self.add_consumer(partial(_put_to_sync_queue, queue))
        return queue

    def wait(self):
        self.result_queue().wait()
        if self._exc:
            raise self._exc


class Executor(object):
    def __init__(self):
        self._task_deque = deque()
        self._lock = Lock()
        self._thread_ident = None
        self._closed = False

    def _step(self):
        try:
            future, gen = self._task_deque.popleft()
            future.consume_result(next(gen))
            self._task_deque.append((future, gen))
            return True
        except StopIteration:
            future.set_done()
            return True
        except IndexError:
            return False
        except BaseException as err:
            future.set_exception(err)
            return True

    def loop(self, forever=False):
        with self._lock:
            if not self._thread_ident:
                self._thread_ident = current_thread().ident
            if self._thread_ident != current_thread().ident:
                # ensure same thread for loop
                raise ThreadError('Executor.loop for one thread only.')
        while (self._step() or forever) and (not self._closed):
            pass

        self._thread_ident = None

    def close(self):
        self._closed = True

    def call(self, fn):
        return self.call_posterior(fn)

    def call_prior(self, fn):
        future = Future(self)
        self._task_deque.appendleft((future, _gen(fn)))
        return future

    def call_posterior(self, fn):
        future = Future(self)
        self._task_deque.append((future, _gen(fn)))
        return future