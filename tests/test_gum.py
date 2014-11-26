# -*- coding: utf-8 -*-
__author__ = 'chinfeng'

from unittest import TestCase

import os
import samples
from gumpy import default_framework


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
        bdl.start().result()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get_bundle('pkg_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        bdl.start().result()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get_bundle('file_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        bdl.start().result()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        bdl = fmk.get('zip_bdl')
        self.assertEqual(bdl.state, bdl.ST_RESOLVED)
        bdl.start().result()
        self.assertEqual(bdl.state, bdl.ST_ACTIVE)

        self.assertRaises(fmk.install_bundle('something_not_exists').result)

        # Require test
        sa = fmk.get_service('mod_bdl:SampleServiceA')
        sb = fmk.get('mod_bdl:SampleServiceB').get_service()
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

        bdl = fmk.get_bundle('file_bdl')
        bdl.em.on_test_event.send('file_test')
        self.assertEqual(fsa.evt_msg, 'file_test')
        self.assertEqual(fsb.evt_msg, 'file_test')

        fmk.em.on_test_event.send('global_evt_test')
        self.assertEqual(msa.evt_msg, 'global_evt_test')
        self.assertEqual(msb.evt_msg, 'global_evt_test')
        self.assertEqual(fsa.evt_msg, 'global_evt_test')
        self.assertEqual(fsb.evt_msg, 'global_evt_test')

        fmk.install_bundle('samples.mod_only_bdl').result().start().wait()
        sample_only = [
            fmk.get_service('file_bdl:SampleServiceOnly'),
            fmk.get_service('mod_only_bdl:SampleServiceOnly')
        ]
        self.assertEqual(len(msa.only), 1)
        self.assertIn(list(msa.only)[0], sample_only)
        fmk.get_bundle('file_bdl').stop().result()
        sample_only.pop(0)  # file_bdl:SampleServiceOnly has been removed
        self.assertNotIn(fsa, msa.ones)
        self.assertNotIn(fsb, msa.twos)
        self.assertEqual(len(msa.only), 1)
        self.assertIn(list(msa.only)[0], sample_only)


