# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import traceback
from cmd import Cmd

class GumCmd(Cmd):
    def __init__(self, framework, plugins_path):
        Cmd.__init__(self)
        self._framework = framework
        self._plugins_path = os.path.abspath(plugins_path)

        self._framework.restore_state()

        self.intro = 'Gumpy runtime console'
        self.prompt = '>>> '

    def do_EOF(self, line):
        self._framework.close()
        return True

    def do_exit(self, line):
        self._framework.close()
        return True

    def do_repo(self, line):
        for repo in self._framework.get_repo_list().values():
            uri = repo.get('uri')
            tp = repo.get('tp')

            for bdl in self._framework.bundles.values():
                if bdl.uri == uri:
                    st = '[%s]' % bdl.state[1]
                    break
            else:
                st = ''

            print('  {:<24}{:<24}{:<24}'.format(uri, '[%s]' % tp, st))

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
        except:
            print(traceback.format_exc())

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
            except:
                print(traceback.format_exc())
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
            except:
                print(traceback.format_exc())
        else:
            print('bundle not found')

    def do_call(self, line):
        try:
            service_uri, call_caluse = line.split('.', 1)
            print(eval('self._framework.get_service(\'{0}\').{1}'.format(service_uri, call_caluse)))
        except:
            print(traceback.format_exc())

    def do_conf(self, line):
        try:
            bn, key, value = line.split(' ')
            conf = self._framework.configuration[bn]
            val = value if not value.isdigit() else int(value)
            conf[key] = val
            evt = self._framework.bundles[bn].em.on_configuration_changed
            evt.send(key, val)
            conf.persist()
        except:
            print(traceback.format_exc())

    def do_fireall(self, line):
        try:
            evt, values = line.split(' ', 1)
            evt = self._framework.em[evt]
            evt.send(*(int(arg) if arg.isdigit() else arg  for arg in values.split(' ')))
        except:
            print(traceback.format_exc())

    def do_fire(self, line):
        try:
            bn, evt, values = line.split(' ', 2)
            evt = self._framework.bundles[bn].em[evt]
            evt.send(*(int(arg) if arg.isdigit() else arg  for arg in values.split(' ')))
        except:
            print(traceback.format_exc())

    def do_step(self, line):
        n = int(line) if line.isdigit() else 1
        for i in range(n):
            self._framework.__executor__.step()

    def emptyline(self):
        self._framework.__executor__.step()
