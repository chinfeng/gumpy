# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from flask import Flask
from gumpy.deco import *

app = Flask(__name__)

@app.route('/')
def index():
  return 'demo web bundle using flask'

@service
@provide('wsgi.application')
class FlaskApplication(object):
    __route__ = 'flask'

    def __call__(self, *args, **kwds):
        return app.wsgi_app(*args, **kwds)