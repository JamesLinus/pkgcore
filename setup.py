#!/usr/bin/env python

from itertools import chain
import operator
import os
import subprocess
from stat import ST_MODE
import sys

from distutils import log
from distutils.command import build, build_scripts
from distutils.errors import DistutilsExecError
from distutils.util import byte_compile

from setuptools import Command, setup
from setuptools.command import install

from pkgdist import distutils_extensions as pkg_distutils

# These offsets control where we install the pkgcore config files and the EBD
# bits relative to the install-data path given to the install subcmd.
DATA_INSTALL_OFFSET = 'share/pkgcore'
CONFIG_INSTALL_OFFSET = os.path.join(DATA_INSTALL_OFFSET, 'config')
EBD_INSTALL_OFFSET = 'lib/pkgcore'

# top level repo/tarball directory
TOPDIR = os.path.dirname(os.path.abspath(__file__))


class mysdist(pkg_distutils.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    user_options = pkg_distutils.sdist.user_options + [
        ('build-docs', None, 'build docs (default)'),
        ('no-build-docs', None, 'do not build docs'),
        ]

    boolean_options = pkg_distutils.sdist.boolean_options + ['build-docs']
    package_namespace = 'pkgcore'

    negative_opt = pkg_distutils.sdist.negative_opt.copy()
    negative_opt.update({'no-build-docs': 'build-docs'})

    def initialize_options(self):
        pkg_distutils.sdist.initialize_options(self)
        self.build_docs = False

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """
        if self.build_docs:
            # need to make sure we're using a built version of pkgcore for the
            # current python version since doc/conf.py imports pkgcore modules
            build_py = self.get_finalized_command('build_py')
            build_py.run()
            # this is icky, but covers up cwd changing issues.
            cwd = os.getcwd()
            if subprocess.call([sys.executable, 'setup.py', 'build_man'], cwd=cwd):
                raise DistutilsExecError("build_man failed")
            import shutil
            shutil.copytree(os.path.join(cwd, "build/sphinx/man"),
                            os.path.join(base_dir, "man"))
        pkg_distutils.sdist.make_release_tree(self, base_dir, files)


class pkgcore_build_scripts(build_scripts.build_scripts):

    """Build (modify #! line) the pwrapper_installed script."""

    def finalize_options(self):
        build_scripts.build_scripts.finalize_options(self)
        self.scripts = [os.path.join('bin', 'pwrapper_installed')]


class pkgcore_build(build.build):

    user_options = build.build.user_options[:]
    user_options.append((
        'enable-man-pages', None,
        'install man pages (default)'))
    user_options.append((
        'disable-man-pages', None,
        'disable man page generation and installation'))
    user_options.append((
        'enable-html-docs', None,
        'install html docs'))
    user_options.append((
        'disable-html-docs', None,
        'disable installation of html docs (default)'))

    boolean_options = build.build.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    negative_opt = dict(getattr(build.build, 'negative_opt', {}))
    negative_opt.update({
        'disable-html-docs': 'enable-html-docs',
        'disable-man-pages': 'enable-man-pages',
    })

    sub_commands = build.build.sub_commands[:]
    sub_commands.append(('build_scripts', None))
    sub_commands.append(('build_docs', operator.attrgetter('enable_html_docs')))
    sub_commands.append(('build_man', operator.attrgetter('enable_man_pages')))

    def initialize_options(self):
        build.build.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        build.build.finalize_options(self)
        if self.enable_man_pages is None:
            path = os.path.dirname(os.path.abspath(__file__))
            self.enable_man_pages = not os.path.exists(os.path.join(path, 'man'))

        if self.enable_html_docs is None:
            self.enable_html_docs = False


class pkgcore_install_scripts(Command):

    """Install symlinks to the pwrapper_installed script.

    Adapted from distutils install_scripts.
    """

    user_options = [
        ('install-dir=', 'd', "directory to install scripts to"),
        ('build-dir=', 'b', "build directory (where to install from)"),
        ('force', 'f', "force installation (overwrite existing files)"),
        ('skip-build', None, "skip the build steps"),
    ]

    boolean_options = ['force', 'skip-build']

    def initialize_options(self):
        self.install_dir = None
        self.force = 0
        self.build_dir = None
        self.skip_build = None

    def finalize_options(self):
        self.set_undefined_options('build', ('build_scripts', 'build_dir'))
        self.set_undefined_options(
            'install',
            ('install_scripts', 'install_dir'),
            ('force', 'force'),
            ('skip_build', 'skip_build'),
        )
        self.scripts = [path for path in os.listdir('bin')
                        if path not in ('pwrapper', 'pwrapper_installed')]

    def run(self):
        if not self.skip_build:
            self.run_command('build_scripts')
        self.mkpath(self.install_dir)
        if os.name == 'posix':
            # Copy the wrapper once.
            copyname = os.path.join(self.install_dir, self.scripts[0])
            self.copy_file(os.path.join(self.build_dir, 'pwrapper_installed'),
                           copyname)
            # Set the executable bits (owner, group, and world).
            if self.dry_run:
                log.info("changing mode of %s", copyname)
            else:
                # note, we use the int here for python3k compatibility.
                # 365 == 0555, 4095 = 0777
                mode = ((os.stat(copyname)[ST_MODE]) | 365) & 4095
                log.debug("changing mode of %s to %o", copyname, mode)
                os.chmod(copyname, mode)
            # Use symlinks for the other scripts.
            for script in self.scripts[1:]:
                # We do not use self.copy_file(link='sym') because we
                # want to make a relative link and copy_file requires
                # the "source" to be an actual file.
                dest = os.path.join(self.install_dir, script)
                log.info('symlinking %s to %s', dest, self.scripts[0])
                try:
                    os.symlink(self.scripts[0], dest)
                except EnvironmentError:
                    # yes, it would be best to examine the exception...
                    # but that makes this script non py3k sourcable
                    if not os.path.exists(dest):
                        raise
                    os.remove(dest)
                    os.symlink(self.scripts[0], dest)
        else:
            # Just copy all the scripts.
            for script in self.scripts:
                self.copy_file(
                    os.path.join(self.build_dir, 'pwrapper_installed'),
                    os.path.join(self.install_dir, script))

    def get_inputs(self):
        return self.scripts

    def get_outputs(self):
        return self.scripts


def _get_files(path):
    for root, dirs, files in os.walk(path):
        for f in files:
            yield os.path.join(root, f)[len(path):].lstrip('/')

def _get_data_mapping(host_path, path):
    for root, dirs, files in os.walk(path):
        yield (os.path.join(host_path, root.partition(path)[2].lstrip('/')),
               [os.path.join(root, x) for x in files])

class pkgcore_install_docs(Command):

    """Install html documentation"""

    content_search_path = ('build/sphinx/html', 'html')
    user_options = [('path=', None,
                     "Final path to install to; else it's calculated")]
    build_command = 'build_docs'

    def initialize_options(self):
        self.root = None
        self.prefix = None
        self.path = None
        self.content = []
        self.source_path = None

    def finalize_options(self):
        self.set_undefined_options(
            'install',
            ('root', 'root'),
            ('install_base', 'prefix'),
        )
        if not self.root:
            self.root = '/'
        if self.path is None:
            self.path = os.path.join(
                self.root, self.calculate_install_path().lstrip(os.path.sep))

    def calculate_install_path(self):
        return os.path.join(
            self.prefix, 'share', 'doc', 'pkgcore-%s' % __version__, 'html')

    def find_content(self):
        for possible_path in self.content_search_path:
            possible_path = os.path.join(TOPDIR, possible_path)
            if os.path.isdir(possible_path):
                return possible_path
        else:
            return None

    def _map_paths(self, content):
        return {x: x for x in content}

    def scan_content(self):
        self.content = self._map_paths(_get_files(self.source_path))
        return self.content

    def run(self, firstrun=True):
        self.source_path = self.find_content()
        if self.source_path is None:
            if not firstrun:
                raise DistutilsExecError(
                    "no pregenerated sphinx content, and sphinx isn't available "
                    "to generate it; bailing")
            self.run_command(self.build_command)
            return self.run(False)

        content = self.scan_content()

        content = self.content
        directories = set(map(os.path.dirname, content.values()))
        directories.discard('')
        for x in sorted(directories):
            self.mkpath(os.path.join(self.path, x))

        for src, dst in sorted(content.items()):
            self.copy_file(
                os.path.join(self.source_path, src),
                os.path.join(self.path, dst))

    def get_inputs(self):
        # Py3k compatibility- force list so behaviour is the same.
        return list(self.content)

    def get_outputs(self):
        # Py3k compatibility- force list so behaviour is the same.
        return list(self.content.values())


class pkgcore_install_man(pkgcore_install_docs):

    """Install man pages"""

    content_search_path = ('build/sphinx/man', 'man')
    user_options = [('path=', None,
                     "Final path to install to; else it's calculated")]
    build_command = 'build_man'

    def calculate_install_path(self):
        return os.path.join(self.prefix, 'share', 'man')

    def _map_paths(self, content):
        d = {}
        for x in content:
            if len(x) >= 3 and x[-2] == '.' and x[-1].isdigit():
                # Only consider extensions .1, .2, .3, etc, and files that
                # have at least a single char beyond the extension (thus ignore
                # .1, but allow a.1).
                d[x] = 'man%s/%s' % (x[-1], os.path.basename(x))
        return d

_base_install = getattr(pkg_distutils, 'install', install.install)

class pkgcore_install(_base_install):

    user_options = _base_install.user_options[:]
    user_options.append((
        'enable-man-pages', None,
        'install man pages'))
    user_options.append((
        'disable-man-pages', None,
        'disable man page generation and installation (default)'))
    user_options.append((
        'enable-html-docs', None,
        'Install html docs.'))
    user_options.append((
        'disable-html-docs', None,
        'disable installation of html docs (default)'))

    boolean_options = _base_install.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    negative_opt = _base_install.negative_opt.copy()
    negative_opt.update({
        'disable-html-docs': 'enable-html-docs',
        'disable-man-pages': 'enable-man-pages',
    })

    def initialize_options(self):
        _base_install.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        build_options = self.distribution.command_options.setdefault('build', {})
        build_options['enable_html_docs'] = ('command_line', self.enable_html_docs and 1 or 0)
        man_pages = self.enable_man_pages
        if man_pages and os.path.exists('man'):
            man_pages = False
        build_options['enable_man_pages'] = ('command_line', man_pages and 1 or 0)
        _base_install.finalize_options(self)

    sub_commands = _base_install.sub_commands[:]
    sub_commands.append(('install_scripts', None))
    sub_commands.append(('install_man', operator.attrgetter('enable_man_pages')))
    sub_commands.append(('install_docs', operator.attrgetter('enable_html_docs')))

    def run(self):
        _base_install.run(self)
        target = self.install_data
        root = self.root or '/'
        if target.startswith(root):
            target = os.path.join('/', os.path.relpath(target, root))
        if not self.dry_run:
            # Install configuration data so pkgcore knows where to find it's content,
            # rather than assuming it is running from a tarball/git repo.
            write_pkgcore_lookup_configs(self.install_purelib, target)

            # Generate ebd function lists used for environment filtering.
            write_pkgcore_ebd_funclists(
                os.path.join(root, target.lstrip('/'), EBD_INSTALL_OFFSET))


def write_pkgcore_ebd_funclists(ebd_dir):
    log.info("Writing ebd function lists to %s" % os.path.join(ebd_dir, 'funcnames'))

    # generate global function list
    with open(os.devnull, 'w') as devnull:
        if subprocess.call(
                [os.path.join(os.getcwd(), 'bash', 'regenerate_dont_export_func_list.bash'),
                 os.path.join(ebd_dir, 'funcnames', 'global')],
                cwd=ebd_dir, stderr=devnull):
            raise DistutilsExecError("generating global function list failed")

    # generate EAPI specific function lists
    eapis = (x.split('.')[0] for x in os.listdir(os.path.join(ebd_dir, 'eapi'))
             if x.split('.')[0].isdigit())
    for eapi in sorted(eapis):
        with open(os.path.join(ebd_dir, 'funcnames', eapi), 'w') as f:
            if subprocess.call(
                    [os.path.join(os.getcwd(), 'bash', 'generate_eapi_func_list.bash'), eapi],
                    cwd=ebd_dir, stdout=f):
                raise DistutilsExecError(
                    "generating EAPI %s function list failed" % eapi)


def write_pkgcore_lookup_configs(python_base, install_prefix, injected_bin_path=()):
    path = os.path.join(python_base, "pkgcore", "_const.py")
    log.info("Writing lookup configuration to %s" % path)
    with open(path, "w") as f:
        os.chmod(path, 0o644)
        f.write("INSTALL_PREFIX=%r\n" % install_prefix)
        f.write("DATA_PATH=%r\n" %
                os.path.join(install_prefix, DATA_INSTALL_OFFSET))
        f.write("CONFIG_PATH=%r\n" %
                os.path.join(install_prefix, CONFIG_INSTALL_OFFSET))
        f.write("EBD_PATH=%r\n" %
                os.path.join(install_prefix, EBD_INSTALL_OFFSET))
        # This is added to suppress the default behaviour of looking
        # within the repo for a bin subdir.
        f.write("INJECTED_BIN_PATH=%r\n" % (tuple(injected_bin_path),))
    byte_compile([path], prefix=python_base)
    byte_compile([path], optimize=2, prefix=python_base)


class pkgcore_build_py(pkg_distutils.build_py):

    package_namespace = 'pkgcore'
    generate_verinfo = True


class test(pkg_distutils.test):

    default_test_namespace = 'pkgcore.test'

    def run(self):
        # This is fairly hacky, but is done to ensure that the tests
        # are ran purely from what's in build, reflecting back to the source
        # only for misc bash scripts or config data.
        key = 'PKGCORE_OVERRIDE_DATA_PATH'
        original = os.environ.get(key)
        try:
            os.environ[key] = os.path.dirname(os.path.realpath(__file__))
            return pkg_distutils.test.run(self)
        finally:
            if original is not None:
                os.environ[key] = original
            else:
                os.environ.pop(key, None)


def _find_modules(location):
    return [root.replace(os.path.sep, '.')
            for root, dirs, files in os.walk(location)
            if '__init__.py' in files]


packages = _find_modules('pkgcore')

extensions = []
if not pkg_distutils.is_py3k:
    extensions.extend([
        pkg_distutils.OptionalExtension(
            'pkgcore.ebuild._atom', ['src/atom.c']),
        pkg_distutils.OptionalExtension(
            'pkgcore.ebuild._cpv', ['src/cpv.c']),
        pkg_distutils.OptionalExtension(
            'pkgcore.ebuild._depset', ['src/depset.c']),
        pkg_distutils.OptionalExtension(
            'pkgcore.ebuild._filter_env', [
                'src/filter_env.c', 'src/bmh_search.c']),
        pkg_distutils.OptionalExtension(
            'pkgcore.restrictions._restrictions', ['src/restrictions.c']),
        pkg_distutils.OptionalExtension(
            'pkgcore.ebuild._misc', ['src/misc.c']),
    ])

from pkgcore import __version__

cmdclass = {
    'sdist': mysdist,
    'build': pkgcore_build,
    'build_py': pkgcore_build_py,
    'build_ext': pkg_distutils.build_ext,
    'test': test,
    'install': pkgcore_install,
    'build_scripts': pkgcore_build_scripts,
    'install_scripts': pkgcore_install_scripts,
    'install_man': pkgcore_install_man,
    'install_docs': pkgcore_install_docs,
}
command_options = {}

with open('README.rst', 'r') as f:
    readme = f.read()

setup(
    name='pkgcore',
    version=__version__,
    description='package managing framework',
    long_description=readme,
    url='https://github.com/pkgcore/pkgcore',
    license='BSD/GPLv2',
    author='Brian Harring, Tim Harder',
    author_email='pkgcore-dev@googlegroups.com',
    packages=packages,
    install_requires=['snakeoil>=0.6.4'],
    data_files=list(chain(
        _get_data_mapping(CONFIG_INSTALL_OFFSET, 'config'),
        _get_data_mapping(EBD_INSTALL_OFFSET, 'bash'),
    )),
    ext_modules=extensions, cmdclass=cmdclass, command_options=command_options,
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 2.7',
    ],
)
