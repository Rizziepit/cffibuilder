try:
    reload
except NameError:
    from imp import reload

from cffibuilder import Builder
from cffibuilder.api import FFI
from cffibuilder.cparser import Parser


_module_cache = {}

def build_module(name, cdef, source):
    module_key = (cdef, name, source)
    if module_key not in _module_cache:
        builder = Builder()
        builder.cdef(cdef)
        builder.build(name, source=source)
    module = __import__(name)
    module = reload(module)
    return module


def ffi_from_module(mod, backend=None):
    if backend is not None:
        mod.ffi = FFI(mod.ffi._parser, backend)
        return mod.ffi
    return mod.ffi


def build_ffi(backend, parser=None, cdef=""):
    if parser is None:
        parser = Parser()
        if cdef:
            cdef = cdef.encode('ascii')
            parser.parse(cdef)
    elif cdef:
        raise ValueError("Cannot provide both 'parser' and 'cdef' arguments")
    return FFI(parser, backend)
