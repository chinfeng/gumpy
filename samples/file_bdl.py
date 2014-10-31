from gumpy.deco import *
import logging
logger = logging.getLogger(__name__)

@activate
def on_activate():
    logger.debug('file_bdl activate')

@service
@provide('sample_res_one')
class SampleServiceA(object):
    @require('mod_bdl:SampleServiceA')
    def foo(self, sa):
        return sa

@provide('sample_res_two')
@service
class SampleServiceB(object):
    pass