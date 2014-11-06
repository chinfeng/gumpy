# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

import os
import sys
from .console import GumCmd
from .framework import Framework
from .configuration import LocalConfiguration

def main():
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
    cmd.cmdloop()

if __name__ == '__main__':
    main()