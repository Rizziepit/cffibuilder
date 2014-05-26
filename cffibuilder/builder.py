import imp, os, pickle, shutil, sys

from . import ffiplatform
from .lock import allocate_lock


class Builder(object):

    def __init__(self):
        from . import cparser
        self._lock = allocate_lock()
        self._parser = cparser.Parser()
        self._cdefsources = []

    def cdef(self, csource, override=False, packed=False):
        if not isinstance(csource, str):    # unicode, on Python 2
            if not isinstance(csource, basestring):
                raise TypeError("cdef() argument must be a string")
            csource = csource.encode('ascii')

        with self._lock:
            self._parser.parse(csource, override=override, packed=packed)
            self._cdefsources.append(csource)

    def build(self, modulename, source='', srcdir=None, tmpdir=None, **kwargs):
        modulename = os.path.splitext(modulename)[0]
        if srcdir is None:
            srcdir = os.path.join(
                os.path.abspath(os.path.dirname(sys._getframe(1).f_code.co_filename)),
                'build/%s/' % modulename
            )
        _ensure_dir(srcdir)

        with self._lock:
            self._generate_code(modulename, srcdir, source)
            self._verify(modulename, srcdir, tmpdir, **kwargs)

    def _generate_code(self, modulename, srcdir, source):
        # copy all the C
        srcdir_c = os.path.join(srcdir, 'c/')
        shutil.rmtree(srcdir_c, True)
        shutil.copytree(_get_c_dir(), srcdir_c)
        # generate library C extension code
        modulename_lib = '%s_lib' % modulename
        sourcepath_lib = os.path.join(srcdir_c, '%s_lib.c' % modulename)
        from .genengine_cpy import GenCPythonEngine
        engine = GenCPythonEngine(modulename_lib, sourcepath_lib, source, self._parser)
        engine.write_source_to_f()
        # store the parser
        self._write_parser(self._parser, modulename, srcdir)
        # copy some Python code
        for filename in ('api.py', 'lock.py', 'model.py', 'cparser.py',
                         'commontypes.py', 'error.py', 'gc_weakref.py'):
            shutil.copy(os.path.join(os.path.dirname(__file__), filename), srcdir)
        # write code to put ffi object and lib at top level
        with open(os.path.join(srcdir, '__init__.py'), 'w') as f:
            f.write(module_init % modulename)

    def _write_parser(self, parser, modulename, srcdir):
        datadir = os.path.join(srcdir, 'data/')
        _ensure_dir(datadir)
        with open(os.path.join(datadir, 'parser.dat'), 'w') as f:
            picklestr = pickle.dumps(parser, 0)
            picklestr = picklestr.replace('cffibuilder', modulename)
            f.write(picklestr)

    def _verify(self, modulename, srcdir, tmpdir=None, **kwargs):
        # figure out some file paths
        if tmpdir is None:
            tmpdir = os.path.join(srcdir, '../__pycache__/')
        _ensure_dir(tmpdir)
        modulename_lib = '%s_lib' % modulename
        sourcepath_lib = os.path.join(srcdir, 'c/%s_lib.c' % modulename)
        sourcepath_lib = ffiplatform.maybe_relative_path(sourcepath_lib)
        modulename_ffi = '_cffi_backend'
        sourcepath_ffi = os.path.join(srcdir, 'c/_cffi_backend.c')
        sourcepath_ffi = ffiplatform.maybe_relative_path(sourcepath_ffi)
        # update compiler args with libraries and dirs to compile _cffi_backend
        kw = kwargs.copy()
        kw['include_dirs'] = ['/usr/include/ffi', '/usr/include/libffi'] \
                             + kwargs.get('include_dirs', [])
        kw['libraries'] = ['ffi'] + kwargs.get('libraries', [])
        # compile and load the 2 extension modules
        extension_ffi = ffiplatform.get_extension(sourcepath_ffi, modulename_ffi, **kw)
        extension_lib = ffiplatform.get_extension(sourcepath_lib, modulename_lib, **kw)
        for extension, modname in ((extension_ffi, modulename_ffi),
                                   (extension_lib, modulename_lib)):
            outputpath = ffiplatform.compile(tmpdir, extension)
            self._load_library(outputpath, modname)
        # import the top level module
        sys.path.insert(0, os.path.dirname(srcdir.rstrip('/')))
        imp.load_module(modulename, *imp.find_module(modulename))

    def _load_library(self, modulepath, modulename):
        # loads the generated library
        try:
            imp.load_dynamic(modulename, modulepath)
        except ImportError as e:
            error = "importing %r: %s" % (modulepath, e)
            raise ffiplatform.VerificationError(error)


def _ensure_dir(filename):
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError:
        pass


def _get_c_dir():
    relativedir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'c/')
    return os.path.abspath(relativedir)


module_init = '''
import os, pickle

import %s_lib as lib
from api import FFI


_parserfile = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                           'data/parser.dat')
with open(_parserfile) as f:
    _parserstr = f.read()
ffi = FFI(parser=pickle.loads(_parserstr))


__all__ = ['lib', 'ffi']
'''
