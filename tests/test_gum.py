# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from unittest import TestCase

import os
import samples
from gumpy import default_framework, BundleInstallError


import logging
logger = logging.getLogger(__name__)

class GumTestCase(TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG, format='[%(asctime)-15s %(levelname)s:%(module)s] %(message)s')
        fmk = default_framework()
        fmk.install_bundle('samples.mod_bdl').result()
        fmk.install_bundle('samples.pkg_bdl').result()
        fmk.install_bundle(os.path.join(os.path.dirname(samples.__file__), 'file_bdl.py')).result()
        fmk.install_bundle(os.path.join(os.path.dirname(samples.__file__), 'zip_bdl.zip')).result()
        self._fmk = fmk

    def test_gumpy(self):
        fmk = self._fmk

        bdl = fmk.get_bundle('mod_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        _f = bdl.start()
        _f.wait()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get_bundle('pkg_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        _f = bdl.start()
        _f.wait()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get_bundle('file_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        _f = bdl.start()
        _f.wait()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get_bundle('zip_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        _f = bdl.start()
        _f.wait()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        try:
            fmk.install_bundle('something_not_exists').result()
            self.assertIs(False, True)
        except BundleInstallError:
            self.assertIs(True, True)

        # Require test
        sa = fmk.get_service('mod_bdl:SampleServiceA')
        sb = fmk.get_service('mod_bdl:SampleServiceB')
        self.assertEqual(sa, sb.foo1())
        self.assertEqual(sa, sb.foo2())

        sa = fmk.get_service('mod_bdl:SampleServiceA')
        sb = fmk.get_service('file_bdl:SampleServiceA')
        self.assertEqual(sa, sb.foo())

        # Bind test
        msa = fmk.get_service('mod_bdl:SampleServiceA')
        msb = fmk.get_service('mod_bdl:SampleServiceB')     # sample_res_two
        fsa = fmk.get_service('file_bdl:SampleServiceA')    # sample_res_one
        fsb = fmk.get_service('file_bdl:SampleServiceB')    # sample_res_two

        self.assertIn(fsa, msa.ones)
        self.assertIn(msb, msa.twos)
        self.assertIn(fsb, msa.twos)

        _f = fmk.get_bundle('file_bdl').stop()
        _f.wait()
        self.assertNotIn(fsa, msa.ones)
        self.assertNotIn(fsb, msa.twos)

