# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import sys
import os
from cmd import Cmd
from . import LocalConfiguration

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

class GumCmd(Cmd):
    def __init__(self, framework, plugins_path):
        Cmd.__init__(self)
        self._framework = framework
        self._plugins_path = os.path.abspath(plugins_path)

        self._framework.restore_state()

        self.intro = 'Gumpy runtime console'
        self.prompt = '>>> '

    def _save_config(self):
        self._framework.save_state()

    def do_EOF(self, line):
        return True

    def do_exit(self, line):
        return True

    def do_repo(self, line):
        for fn in os.listdir(self._plugins_path):
            fp = os.path.join(self._plugins_path, fn)
            bn, ext = os.path.splitext(fn)
            uri = fn
            if bn[:2] == '__':
                continue
            if os.path.isdir(fp) and bn[0] != '.':
                tp = '[PKG]'
            elif ext == '.zip':
                tp = '[ZIP]'
            elif ext == '.py':
                tp = '[MOD]'
                uri = bn
            else:
                continue

            for bdl in self._framework.bundles.values():
                if bdl.uri == uri:
                    st = '[%s]' % bdl.state[1]
                    break
            else:
                st = ''

            print('  {:<24}{:<24}{:<24}'.format(uri, tp, st))

    def do_install(self, line):
        if line[-1] == '&':
            async = True
            uri = line[:-1]
        else:
            async = False
            uri = line

        bn, ext = os.path.splitext(uri)
        if ext in ('.py', '.zip') and not os.path.exists(uri):
            uri = os.path.join(self._plugins_path, uri)

        try:
            f = self._framework.install_bundle(uri)
            if not async:
                f.result()
            self._save_config()
        except BaseException as e:
            print(e)

    def do_list(self, line):
        for bdl in self._framework.bundles.values():
            print('  {:<24}{:<24}'.format(
                bdl.name, '[%s]' % bdl.state[1]))

    def do_start(self, line):
        if line[-1] == '&':
            async = True
            bn = line[:-1]
        else:
            async = False
            bn = line

        if bn in self._framework.bundles:
            try:
                bdl = self._framework.bundles[bn]
                f = bdl.start()
                if not async:
                    f.result()
                self._save_config()
            except BaseException as err:
                print(err)
        else:
            print('bundle not found')

    def do_stop(self, line):
        if line[-1] == '&':
            async = True
            bn = line[:-1]
        else:
            async = False
            bn = line

        if bn in self._framework.bundles:
            try:
                bdl = self._framework.bundles[bn]
                f = bdl.stop()
                if not async:
                    f.result()
                self._save_config()
            except BaseException as err:
                print(err)
        else:
            print('bundle not found')

    def do_call(self, line):
        service_uri, call_caluse = line.split('.', 1)
        print(eval('self._framework.get_service(\'{0}\').{1}'.format(service_uri, call_caluse)))

    def do_conf(self, line):
        bn, key, value = line.split(' ')
        conf = self._framework.configuration[bn]
        conf[key] = value if not value.isdigit() else int(value)
        conf.persist()

