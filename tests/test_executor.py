__author__ = 'Chinfeng'

import gumpy
import unittest
import functools
try:
    from Queue import Empty
except ImportError:
    from queue import Empty


class ExecutorTestCase(unittest.TestCase):
    def setUp(self):
        self._executor = gumpy.Executor()

    def test_something(self):
        def foo(v, msg):
            return v

        def foo_yield(v, msg):
            for i in range(v):
                yield i

        def foo_exc(msg):
            raise RuntimeError('foo_exc')

        extr = self._executor
        f1 = extr.call(functools.partial(foo_yield, 10, 'f1'))
        f2 = extr.call(functools.partial(foo_yield, 20, 'f2'))

        f3 = extr.call(functools.partial(foo_exc, 'f3'))

        def _consumer(tc=self):
            for i in range(999):
                tc.assertEqual(i, (yield))

        def _f3_exception(exception, tc=self):
            tc.assertIsInstance(exception, RuntimeError)
            tc.assertEqual('foo_exc', exception.args[0])

        f1.add_consumer(_consumer)
        f2.add_consumer(_consumer)
        f3.add_error_callback(_f3_exception)

        f4 = extr.call(functools.partial(foo_yield, 4, 'f4'))
        q = f4.result_queue()

        def _f5_consumer(v, tc=self):
            tc.assertEqual(v, (yield))
        f5 = extr.call(functools.partial(foo, 999, 'f5'))
        f5.add_consumer(functools.partial(_f5_consumer, 999))

        extr.loop()

        i = 0
        while True:
            try:
                self.assertEqual(i, q.get())
                i += 1
            except Empty:
                break

if __name__ == '__main__':
    unittest.main()
