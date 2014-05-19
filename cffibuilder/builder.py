import imp, os, sys

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
            self._verify(modulename, sourcepath, tmpdir, **kwargs)

    def _generate_code(self, modulename, sourcepath, source):
        from .genengine_cpy import GenCPythonEngine
        cdir = _get_c_dir()
        backendpath = os.path.join(cdir, '_cffi_backend.c')
        engine = GenCPythonEngine(modulename, sourcepath, backendpath,
                                  source, self._parser)
        engine.write_source_to_f()

    def _verify(self, modulename, sourcepath, tmpdir=None, **kwargs):
        # figure out some file paths
        if tmpdir is None:
            tmpdir = os.path.join(os.path.dirname(sourcepath), '__pycache__')
        _ensure_dir(tmpdir)
        sourcepath = ffiplatform.maybe_relative_path(sourcepath)
        # update compiler args with libraries and dirs to compile _cffi_backend.c
        kw = kwargs.copy()
        kw['include_dirs'] = [_get_c_dir()] + kwargs['include_dirs']
        kw['libraries'] = ['ffi'] + kwargs['libraries']
        extension = ffiplatform.get_extension(sourcepath, modulename, **kw)
        outputpath = ffiplatform.compile(tmpdir, extension)
        self._load_library(outputpath, modulename)

    def _load_library(self, modulepath, modulename):
        # loads the generated library
        # this is the final verification step
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
