# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

__gum__ = 'storage'

import os, sys
from .mock import Storage
from gumpy.deco import service, provide

@service
@provide('huacaya.storage')
def StorageService():
    from tempfile import gettempdir
    path = os.path.join(os.path.abspath(gettempdir()), '.mock_storage_{0}'.format(sys.version_info.major))
    return Storage(path)

