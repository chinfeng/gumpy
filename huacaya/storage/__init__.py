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
        return MockStorage()

