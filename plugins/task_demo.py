# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import *

import logging
logger = logging.getLogger(__name__)

@service
class TaskDemo(object):
    def __init__(self):
        self._msg = None
        self.message_task.spawn()
        self.counter_task.spawn()

    @task
    def message_task(self):
        while True:
            if self._msg:
                print('TaskDemo on_message: {0}'.format(self._msg))
                self._msg = None
            yield

    @task
    def counter_task(self):
        counter = 0
        while True:
            yield
            print('TaskDemo counter: {0}'.format(counter))
            counter += 1

    @event
    def on_message(self, msg):
        self._msg = msg
