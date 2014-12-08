# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

__gum__ = 'storage'

import os, sys
from storage.mock import Storage
from gumpy.deco import service, provide

@service
@provide('huacaya.storage')
class MockStorageService(Storage):
    def __init__(self):
        from tempfile import gettempdir
        path = os.path.join(os.path.abspath(gettempdir()), '.mock_storage_{0}'.format(sys.version_info.major))
        super(self.__class__, self).__init__(path)

