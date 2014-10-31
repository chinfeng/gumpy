# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import *
import logging
logger = logging.getLogger(__name__)

__symbol__ = 'mod_bdl'

@activate
def on_activate():
    logger.debug('mod_bdl activate')

@provide('sample_res_two')
@service
class SampleServicePre(object):
    pass

@service
class SampleServiceA(object):
    def initialize(self):
        self.ones = set()
        self.twos = set()

    @bind('sample_res_one')
    def sr_one(self, res):
        logger.debug('sr_one bind: {0}'.format(res))
        self.ones.add(res)

    @sr_one.unbind
    def unbind_sr_one(self, res):
        logger.debug('sr_one unbind: {0}'.format(res))
        self.ones.remove(res)

    @bind('sample_res_two')
    def sr_two(self, res):
        logger.debug('sr_two bind: {0}'.format(res))
        self.twos.add(res)

    @sr_two.unbind
    def unbind_sr_two(self, res):
        logger.debug('sr_two unbind: {0}'.format(res))
        self.twos.remove(res)

@service
@provide('sample_res_two')
class SampleServiceB(object):
    @require('SampleServiceA')
    def foo1(self, sa):
        return sa

    @require(sa='mod_bdl:SampleServiceA')
    def foo2(self, sa):
        return sa