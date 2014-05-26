try:
    reload
except NameError:
    from imp import reload

from cffibuilder import Builder
from cffibuilder.api import FFI
from cffibuilder.cparser import Parser


_module_cache = {}
_module_by_name = {}

def build_module(name, cdef, source):
    module_key = (cdef, name, source)
    if module_key not in _module_cache:
        builder = Builder()
        builder.cdef(cdef)
        builder.build(name, source=source)
        if name in _module_by_name:
            module = reload(_module_by_name[name])
        else:
            module = __import__(name)
            module = reload(module)
        _module_cache[module_key] = module
        _module_by_name[name] = module
    return _module_by_name[name]


def ffi_from_module(name, backend=None):
    if backend is not None:
        try:
            mod = _module_by_name[name]
        except KeyError:
            mod = __import__(name)
            mod = reload(mod)
        mod.ffi = FFI(mod.ffi._parser, backend)
        return mod.ffi
    try:
        return _module_by_name[name].ffi
    except KeyError:
        mod = __import__(name)
        return reload(mod).ffi


def build_ffi(backend, parser=None, cdef=""):
    if parser is None:
        parser = Parser()
        if cdef:
            cdef = cdef.encode('ascii')
            parser.parse(cdef)
    elif cdef:
        raise ValueError("Cannot provide both 'parser' and 'cdef' arguments")
    return FFI(parser, backend)
