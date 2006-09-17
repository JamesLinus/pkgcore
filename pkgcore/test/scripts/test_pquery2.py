# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest

from pkgcore.scripts import pquery2
from pkgcore.test.scripts import helpers
from pkgcore.config import basics, ConfigHint, configurable
from pkgcore.test.repository import util


class FakeDomain(object):

    pkgcore_config_type = ConfigHint({'repos': 'refs:repo',
                                      'vdb': 'refs:repo'},
                                     typename='domain')

    def __init__(self, repos, vdb):
        object.__init__(self)
        self.repos = repos
        self.vdb = vdb


@configurable(typename='repo')
def fake_repo():
    return util.SimpleTree({'spork': {'foon': ('1', '2')}})


@configurable(typename='repo')
def fake_vdb():
    return util.SimpleTree({})


domain_config = basics.HardCodedConfigSection({
        'class': FakeDomain,
        'repos': [basics.HardCodedConfigSection({'class': fake_repo})],
        'vdb': [basics.HardCodedConfigSection({'class': fake_vdb})],
        'default': True,
        })


class pquery2Test(unittest.TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pquery2.OptionParser())
    main = staticmethod(pquery2.main)

    def test_parser(self):
        self.assertError(
            '--noversion with --min or --max does not make sense.',
            '--noversion', '--max', '--min')
        self.assertTrue(self.parser.parse_args([]))

    def test_no_domain(self):
        self.assertErr(
            ['No default domain found, fix your configuration or '
             'pass --domain',
             'Valid domains: ',
             ],
            {})

    def test_no_description(self):
        self.assertOut(
            [' * spork/foon-2',
             '     description: MISSING',
             '     homepage: MISSING',
             '',
             ],
            {'test domain': domain_config},
            '-v', '--max')

    def test_no_contents(self):
        self.assertOut(
            [],
            {'test domain': domain_config},
            '--contents')
