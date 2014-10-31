# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import sys
import os
from cmd import Cmd

class GumCmd(Cmd):
    def __init__(self, framework, plugins_path):
        Cmd.__init__(self)
        self._framework = framework
        self._plugins_path = os.path.abspath(plugins_path)
        sys.path.append(self._plugins_path)

        self.intro = 'Gumpy runtime console'
        self.prompt = '>>> '

    def do_EOF(self, line):
        return True

    def do_repo(self, line):
        for fn in os.listdir(self._plugins_path):
            fp = os.path.join(self._plugins_path, fn)
            bn, ext = os.path.splitext(fn)
            name = bn
            if bn[:2] == '__':
                continue
            if os.path.isdir(fp) and bn[0] != '.':
                tp = '[PKG]'
                abs_fn = os.path.join(self._plugins_path, fn, '__init__.py')
            elif ext == '.zip':
                tp = '[ZIP]'
                name = fn
                abs_fn = os.path.join(self._plugins_path, fn)
            elif ext == '.py':
                tp = '[MOD]'
                abs_fn = os.path.join(self._plugins_path, fn)
            else:
                continue

            for bdl in self._framework.bundles.values():
                if bdl.path == abs_fn:
                    st = '[%s]' % bdl.state[1]
                    break
            else:
                st = ''

            print('  {:<15}{:<15}{:<15}'.format(name, tp, st))

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
        except BaseException as e:
            print(e)

    def do_list(self, line):
        for bdl in self._framework.bundles.values():
            print('  {:<15}{:<15}'.format(
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
            except BaseException as err:
                print(err)
        else:
            print('bundle not found')

    def do_call(self, line):
        service_uri, call_caluse = line.split('.', 1)
        print(eval('self._framework.get_service(\'{0}\').{1}'.format(service_uri, call_caluse)))

