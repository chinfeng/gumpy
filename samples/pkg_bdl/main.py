# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from gumpy.deco import *
import logging
logger = logging.getLogger(__name__)

@activate
def on_activate():
    logger.debug('pkg_bdl activate')

