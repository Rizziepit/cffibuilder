import imp, os, shutil, sys

from . import ffiplatform
from .lock import allocate_lock


class BuilderError(Exception):
    pass


class CDefError(Exception):
    def __str__(self):
        try:
            line = 'line %d: ' % (self.args[1].coord.line,)
        except (AttributeError, TypeError, IndexError):
            line = ''
        return '%s%s' % (line, self.args[0])


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
        if srcdir is None:
            srcdir = os.path.join(
                os.path.abspath(os.path.dirname(sys._getframe(1).f_code.co_filename)),
                'build/'
            )
        _ensure_dir(srcdir)
        modulename = os.path.splitext(modulename)[0]
        sourcepath = os.path.join(srcdir, modulename + '.c')

        with self._lock:
            self._generate_code(modulename, sourcepath, source)
            self._verify(sourcepath, tmpdir, **kwargs)

    def _generate_code(self, modulename, sourcepath, source):
        from .genengine_cpy import GenCPythonEngine
        cdir = _get_c_dir()
        backendpath = os.path.join(cdir, '_cffi_backend.c')
        engine = GenCPythonEngine(modulename, sourcepath, backendpath,
                                  source, self._parser)
        engine.write_source_to_f()

    def _verify(self, sourcepath, tmpdir=None, **kwargs):
        # figure out some file paths
        if tmpdir is None:
            tmpdir = os.path.join(os.path.dirname(sourcepath), '__pycache__')
        _ensure_dir(tmpdir)
        suffix = _get_so_suffixes()[0]
        modpath = os.path.splitext(sourcepath)[0] + suffix
        modulename = _get_module_name(modpath)
        # update compiler args with libraries and dirs to compile _cffi_backend.c
        kw = kwargs.copy()
        kw['include_dirs'] = [_get_c_dir()] + kwargs['include_dirs']
        kw['libraries'] = ['ffi'] + kwargs['libraries']
        extension = ffiplatform.get_extension(sourcepath, modulename, **kw)
        outputpath = ffiplatform.compile(tmpdir, extension)
        try:
            same = ffiplatform.samefile(outputpath, modpath)
        except OSError:
            same = False
        if not same:
            _ensure_dir(modpath)
            shutil.move(outputpath, modpath)
        self._load_library(modpath, modulename)

    def _load_library(self, modulepath, modulename):
        # loads the generated library
        # this is the final verification step
        try:
            imp.load_dynamic(modulename, modulepath)
        except ImportError as e:
            error = "importing %r: %s" % (modulepath, e)
            raise ffiplatform.VerificationError(error)


def _get_so_suffixes():
    suffixes = []
    for suffix, mode, type in imp.get_suffixes():
        if type == imp.C_EXTENSION:
            suffixes.append(suffix)

    if not suffixes:
        # bah, no C_EXTENSION available.  Occurs on pypy without cpyext
        if sys.platform == 'win32':
            suffixes = [".pyd"]
        else:
            suffixes = [".so"]

    return suffixes


def _ensure_dir(filename):
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError:
        pass


def _get_module_name(modulepath):
    basename = os.path.basename(modulepath)
    # kill both the .so extension and the other .'s, as introduced
    # by Python 3: 'basename.cpython-33m.so'
    basename = basename.split('.', 1)[0]
    # and the _d added in Python 2 debug builds --- but try to be
    # conservative and not kill a legitimate _d
    if basename.endswith('_d') and hasattr(sys, 'gettotalrefcount'):
        basename = basename[:-2]
    return basename

def _get_c_dir():
    relativedir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'c/')
    return os.path.abspath(relativedir)
