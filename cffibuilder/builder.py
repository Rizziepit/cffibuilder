import os

from . import cparser
from .lock import allocate_lock


class BuilderError(Exception):
    pass


class Builder(object):

    def __init__(self):
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
            # TODO: figure out the build dir
            pass
        modulepath = os.path.join(srcdir, modulename)
        with open(modulepath, 'w') as f:
            self._generate_code(self, modulename, f, source)
        self._verify(modulepath, tmpdir, **kwargs)

    def _generate_code(self, modulename, sourcefile, source):
        from .genengine_cpy import GenCPythonEngine
        pass

    def _verify(self, sourcefile, tmpdir=None, **kwargs):
        # compiles generated code to verify that it is valid
        if tmpdir is None:
            tmpdir = os.path.join(os.path.dirname(sourcefile), '__pycache__')
        # TODO: compile to tmpdir
        # TODO: load library
        pass

    def _load_library(self, libfile):
        # loads the generated library
        # this is the final verification step
        pass