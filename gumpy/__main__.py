# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import sys
import threading
from .console import GumCmd
from .framework import Framework
from .configuration import LocalConfiguration

def _framework_loop(framework):
    while True:
        framework.step(True)

def main(autostep=False):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--path',
                        dest='plugins_path', default='plugins',
                        help='plugins directory')
    args = parser.parse_args()
    pt = os.path.abspath(args.plugins_path)

    sys.path.append(pt)

    conf_pt = os.path.join(pt, '.configuration')
    if not os.path.isdir(conf_pt):
        os.mkdir(conf_pt)
    fmk = Framework(LocalConfiguration(conf_pt))
    cmd = GumCmd(fmk, pt)
    if autostep:
        t = threading.Thread(target=_framework_loop, args=(fmk, ))
        t.setDaemon(True)
        t.start()
    cmd.cmdloop()

if __name__ == '__main__':
    main()