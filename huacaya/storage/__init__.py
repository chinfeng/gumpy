# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

__gum__ = 'storage'

import os
import sys
from gumpy.deco import service, provide

@service
@provide('huacaya.storage')
def StorageService():
    try:
        from pymongo.mongo_client import MongoClient
        from .mongo import MongoStorage
        client = MongoClient(connectTimeoutMS=3000)
        return MongoStorage(client.huacaya)
    except:
        from .mock import MockStorage
        from tempfile import gettempdir
        path = os.path.join(os.path.abspath(gettempdir()), '.mock_storage_{0}'.format(sys.version_info.major))
        return MockStorage(path)

