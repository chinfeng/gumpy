# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from setuptools import setup, find_packages

setup(
    name='gumpy',
    version='0.1',
    description='An dynamic component framework',
    author='Chinfeng Chung',
    author_email='chinfeng.chung@gmail.com',
    packages=find_packages(exclude=['tests']),
    classifiers=['Programming Language :: Python :: 2.7'],
    classifiers=['Programming Language :: Python :: 3.4'],
    test_suite = 'tests',
)