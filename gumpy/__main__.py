# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from .console import GumCmd
from .framework import default_framework

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--path',
                        dest='plugins_path', default='.',
                        help='plugins directory')
    args = parser.parse_args()

    cmd = GumCmd(default_framework(), args.plugins_path)
    cmd.cmdloop()

if __name__ == '__main__':
    main()