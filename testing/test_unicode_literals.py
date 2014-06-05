#
# ----------------------------------------------
# WARNING, ALL LITERALS IN THIS FILE ARE UNICODE
# ----------------------------------------------
#
from __future__ import unicode_literals
#
#
#
import sys, math
from testing.utils import build_ffi, build_module

lib_m = "m"
if sys.platform == 'win32':
    #there is a small chance this fails on Mingw via environ $CC
    import distutils.ccompiler
    if distutils.ccompiler.get_default_compiler() == 'msvc':
        lib_m = 'msvcrt'


def test_cast():
    ffi = build_ffi(None)
    assert int(ffi.cast("int", 3.14)) == 3        # unicode literal

def test_new():
    ffi = build_ffi(None)
    assert ffi.new("int[]", [3, 4, 5])[2] == 5    # unicode literal

def test_typeof():
    ffi = build_ffi(None)
    tp = ffi.typeof("int[51]")                    # unicode literal
    assert tp.length == 51

def test_sizeof():
    ffi = build_ffi(None)
    assert ffi.sizeof("int[51]") == 51 * 4        # unicode literal

def test_alignof():
    ffi = build_ffi(None)
    assert ffi.alignof("int[51]") == 4            # unicode literal

def test_getctype():
    ffi = build_ffi(None)
    assert ffi.getctype("int**") == "int * *"     # unicode literal
    assert type(ffi.getctype("int**")) is str

def test_cdef():
    ffi = build_ffi(None, cdef="typedef int foo_t[50];")            # unicode literal

def test_offsetof():
    ffi = build_ffi(None, cdef="typedef struct { int x, y; } foo_t;")
    assert ffi.offsetof("foo_t", "y") == 4        # unicode literal

def test_enum():
    ffi = build_ffi(None, cdef="enum foo_e { AA, BB, CC };")        # unicode literal
    x = ffi.cast("enum foo_e", 1)
    assert int(ffi.cast("int", x)) == 1

def test_dlopen():
    ffi = build_ffi(None, cdef="double sin(double x);")
    m = ffi.dlopen(lib_m)                           # unicode literal
    x = m.sin(1.23)
    assert x == math.sin(1.23)

def test_verify():
    lib = build_module("lib", 
        cdef="double test_verify_1(double x);",
        source="double test_verify_1(double x) { return x * 42.0; }"
    ).lib   # unicode literal
    assert lib.test_verify_1(-1.5) == -63.0

def test_callback():
    ffi = build_ffi(None)
    cb = ffi.callback("int(int)",                 # unicode literal
                      lambda x: x + 42)
    assert cb(5) == 47
