try:
    reload
except NameError:
    from imp import reload

from cffibuilder import Builder
from cffibuilder.api import FFI
from cffibuilder.cparser import Parser


_module_names = set()


def get_random_str(length=12):
    import random
    chars = 'abcdefghijklmnopqrstuvwxyz'
    return ''.join([random.choice(chars) for i in range(length)])


def build_module(cdef, source):
    name = get_random_str()
    while name in _module_names:
        name = get_random_str()
    _module_names.add(name)
    builder = Builder()
    builder.cdef(cdef)
    builder.build(name, source=source)
    pkg = __import__('build.%s' % name)
    module = getattr(pkg, name)
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


def teardown_module(module):
    import os, shutil
    for name in _module_names:
        shutil.rmtree(
            os.path.join(os.path.dirname(__file__), 'build/%s' % name),
            True
        )
    _module_names.clear()
