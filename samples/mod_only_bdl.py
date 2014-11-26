# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import *
import logging
logger = logging.getLogger(__name__)

__symbol__ = 'mod_only_bdl'

@activate
def on_activate():
    logger.debug('mod_only_bd activate')

@provide('sample_only')
@service
class SampleServiceOnly(object):
    pass

