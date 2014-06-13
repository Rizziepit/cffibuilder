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
                'build/'
            )
        try:
            # can't use unicode file names with distutils.core.Extension
            encoding = sys.getfilesystemencoding()
            if type(modulename) is unicode:
                modulename = modulename.encode(encoding)
            if type(srcdir) is unicode:
                srcdir = srcdir.encode(encoding)
            if type(tmpdir) is unicode:
                tmpdir = tmpdir.encode(encoding)
        except NameError:
            pass
        srcdir_module = os.path.join(srcdir, '%s/' % modulename)
        _ensure_dir(srcdir_module)
        # copy C header files to build folder
        srcdir_c = os.path.join(srcdir, 'c/')
        shutil.rmtree(srcdir_c, True)
        shutil.copytree(_get_c_dir(), srcdir_c)
        # write build package init
        with open(os.path.join(srcdir, '__init__.py'), 'w') as f:
            f.write(build_init)
        # write original kwargs to file
        with open(os.path.join(srcdir_module, 'BUILD-ARGS.txt'), 'w') as f:
            f.write('%r' % kwargs)

        with self._lock:
            self._generate_code(modulename, srcdir_module, source, **kwargs)
            self._verify(modulename, srcdir_module, tmpdir, **kwargs)

    def _generate_code(self, modulename, srcdir, source, **kwargs):
        # create the C source dir
        srcdir_c = os.path.join(srcdir, 'c/')
        _ensure_dir(srcdir_c)
        # generate C extension code
        modulename_lib = '%s_lib' % modulename
        sourcepath_lib = os.path.join(srcdir_c, '%s_lib.c' % modulename)
        from .genengine_cpy import GenCPythonEngine
        engine = GenCPythonEngine(modulename_lib, sourcepath_lib, source, self._parser)
        engine.write_source_to_f()
        # store the parser
        self._write_parser(self._parser, modulename, srcdir)
        # write library module init
        # it puts ffi and lib objects at top level
        with open(os.path.join(srcdir, '__init__.py'), 'w') as f:
            f.write(module_init % {'modulename': modulename})
            f.write(library_init)

    def _write_parser(self, parser, modulename, srcdir):
        datadir = os.path.join(srcdir, 'data/')
        _ensure_dir(datadir)
        with open(os.path.join(datadir, 'parser.dat'), 'wb') as f:
            pickle.dump(parser, f)

    def _verify(self, modulename, srcdir, tmpdir=None, **kwargs):
        # figure out some file paths
        if tmpdir is None:
            tmpdir = os.path.join(srcdir, '../__pycache__/')
        _ensure_dir(tmpdir)
        # import the build package to use its get_extensions
        # function and get the Extension objects
        packagedir = os.path.dirname(srcdir.rstrip('/'))
        packagename = os.path.basename(packagedir)
        sys.path.insert(0, os.path.dirname(packagedir))
        build_package = __import__(packagename)
        # compile _cffi_backend module if necessary
        extension_backend = build_package.get_extensions('_cffi_backend')
        if extension_backend:
            # only load if the extension isn't installed (for tests)
            try:
                import _cffi_backend
            except ImportError:
                outputpath = ffiplatform.compile(tmpdir, extension_backend[0])
                self._load_library(outputpath, '_cffi_backend')
        # compile the C extension module
        extension = build_package.get_extensions(modulename)[0]
        outputpath = ffiplatform.compile(tmpdir, extension)
        # make sure the latest version of the module is loaded
        self._load_library(outputpath, '%s_lib' % modulename)
        pkginfo = imp.find_module(packagename)
        modinfo = imp.find_module(modulename, [pkginfo[1]])
        imp.load_module(modulename, *modinfo)
        imp.load_module(packagename, *pkginfo)

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


build_init = '''
import glob, os, sys
from distutils.core import Extension


libraries = ['ffi']
include_dirs = ['/usr/include/ffi',
                '/usr/include/libffi',
                os.path.join(os.path.dirname(__file__), 'c')]


# TODO: compile libffi on Windows
# TODO: use pkg-config


def get_extensions(*module_names):
    build_folder = os.path.dirname(__file__)
    extensions = []
    module_names = set(module_names)
    for fp in glob.glob('%s/*/BUILD-ARGS.txt' % build_folder):
        module_name = fp.rsplit('/', 2)[1]
        if module_names and module_name not in module_names:
            continue
        module_dir = os.path.dirname(fp)
        sources = [os.path.join(module_dir, 'c/%s_lib.c' % module_name)]
        with open(fp) as f:
            build_args = f.read()
            build_args = eval(build_args)
        extensions.append(Extension(
            '%s_lib' % module_name,
            sources=sources,
            **build_args
        ))

    if (not module_names or '_cffi_backend' in module_names) and \\
            '__pypy__' not in sys.modules:
        extensions.append(Extension(
            name='_cffi_backend',
            include_dirs=include_dirs,
            sources=[os.path.join(build_folder, 'c/_cffi_backend.c')],
            libraries=libraries,
        ))

    return extensions
'''


module_init = '''
import os, pickle

import %(modulename)s_lib as _libmodule
from cffibuilder.api import FFI


__all__ = ['lib', 'ffi']


# load the serialized parser
_parserfile = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                           'data/parser.dat')
with open(_parserfile, 'rb') as f:
    _parser = pickle.load(f)


ffi = FFI(parser=_parser)
'''


library_init = '''
from cffibuilder import ffiplatform, model
from cffibuilder.genengine_cpy import GenCPythonEngine


class FFILibraryMeta(type):

    def __init__(self, name, bases, attrs):
        self._struct_pending_verification = {}
        self._types_of_builtin_functions = {}

        # build the FFILibrary class
        self._cffi_python_module = _libmodule
        self._cffi_dir = []

        _libmodule._cffi_original_ffi = ffi
        _libmodule._cffi_types_of_builtin_funcs = self._types_of_builtin_functions

        # call loading_cpy_struct() to get the struct layout inferred by
        # the C compiler
        self._load('loading')
        # the C code will need the <ctype> objects.  Collect them in
        # order in a list.
        engine = GenCPythonEngine('', '', '', _parser)
        engine.collect_types()
        revmapping = dict([(value, key)
                           for (key, value) in engine._typesdict.items()])
        lst = [revmapping[i] for i in range(len(revmapping))]
        with ffi._lock:
            self._ctypes_ordered = list(map(ffi._get_cached_btype, lst))
        super(FFILibraryMeta, self).__init__(name, bases, attrs)

    def _get_declarations(self):
        return sorted(_parser._declarations.items())

    def _load(self, step_name, **kwds):
        for name, tp in self._get_declarations():
            kind, realname = name.split(' ', 1)
            method = getattr(self, '_%s_cpy_%s' % (step_name, kind))
            try:
                method(tp, realname, **kwds)
            except Exception as e:
                model.attach_exception_info(e, name)
                raise

    def _loaded_noop(self, tp, name, **kwds):
        pass

    _loading_cpy_typedef = _loaded_noop
    _loaded_cpy_typedef = _loaded_noop
    _loading_cpy_function = _loaded_noop
    _loading_cpy_constant = _loaded_noop
    _loaded_cpy_constant = _loaded_noop
    _loading_cpy_macro = _loaded_noop
    _loaded_cpy_macro  = _loaded_noop
    _loading_cpy_variable = _loaded_noop

    def _loaded_cpy_function(self, tp, name, library):
        if tp.ellipsis:
            return
        func = getattr(_libmodule, name)
        setattr(library, name, func)
        self._types_of_builtin_functions[func] = tp

    def _loading_cpy_struct(self, tp, name):
        self._loading_struct_or_union(tp, 'struct', name)
    def _loaded_cpy_struct(self, tp, name, **kwds):
        self._loaded_struct_or_union(tp)
    def _loading_cpy_union(self, tp, name):
        self._loading_struct_or_union(tp, 'union', name)
    def _loaded_cpy_union(self, tp, name, **kwds):
        self._loaded_struct_or_union(tp)

    def _loading_struct_or_union(self, tp, prefix, name):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        layoutfuncname = '_cffi_layout_%s_%s' % (prefix, name)
        #
        function = getattr(_libmodule, layoutfuncname)
        layout = function()
        if isinstance(tp, model.StructOrUnion) and tp.partial:
            # use the function()'s sizes and offsets to guide the
            # layout of the struct
            totalsize = layout[0]
            totalalignment = layout[1]
            fieldofs = layout[2::2]
            fieldsize = layout[3::2]
            tp.force_flatten()
            assert len(fieldofs) == len(fieldsize) == len(tp.fldnames)
            tp.fixedlayout = fieldofs, fieldsize, totalsize, totalalignment
        else:
            cname = ('%s %s' % (prefix, name)).strip()
            self._struct_pending_verification[tp] = layout, cname

    def _loaded_struct_or_union(self, tp):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        ffi._get_cached_btype(tp)   # force 'fixedlayout' to be considered

        if tp in self._struct_pending_verification:
            # check that the layout sizes and offsets match the real ones
            def check(realvalue, expectedvalue, msg):
                if realvalue != expectedvalue:
                    raise ffiplatform.VerificationError(
                        "%s (we have %d, but C compiler says %d)"
                        % (msg, expectedvalue, realvalue))
            BStruct = ffi._get_cached_btype(tp)
            layout, cname = self._struct_pending_verification.pop(tp)
            check(layout[0], ffi.sizeof(BStruct), "wrong total size")
            check(layout[1], ffi.alignof(BStruct), "wrong total alignment")
            i = 2
            for fname, ftype, fbitsize in tp.enumfields():
                if fbitsize >= 0:
                    continue        # xxx ignore fbitsize for now
                check(layout[i], ffi.offsetof(BStruct, fname),
                      "wrong offset for field %r" % (fname,))
                if layout[i+1] != 0:
                    BField = ffi._get_cached_btype(ftype)
                    check(layout[i+1], ffi.sizeof(BField),
                          "wrong size for field %r" % (fname,))
                i += 2
            assert i == len(layout)

    def _loading_cpy_anonymous(self, tp, name):
        if isinstance(tp, model.EnumType):
            self._loading_cpy_enum(tp, name)
        else:
            self._loading_struct_or_union(tp, '', name)

    def _loaded_cpy_anonymous(self, tp, name, **kwds):
        if isinstance(tp, model.EnumType):
            self._loaded_cpy_enum(tp, name, **kwds)
        else:
            self._loaded_struct_or_union(tp)

    def _loading_cpy_enum(self, tp, name):
        if tp.partial:
            enumvalues = [getattr(_libmodule, enumerator)
                          for enumerator in tp.enumerators]
            tp.enumvalues = tuple(enumvalues)
            tp.partial_resolved = True

    def _loaded_cpy_enum(self, tp, name, library):
        for enumerator, enumvalue in zip(tp.enumerators, tp.enumvalues):
            setattr(library, enumerator, enumvalue)

    def _loaded_cpy_variable(self, tp, name, library):
        value = getattr(library, name)
        if isinstance(tp, model.ArrayType):   # int a[5] is "constant" in the
                                              # sense that "a=..." is forbidden
            if tp.length == '...':
                assert isinstance(value, tuple)
                (value, size) = value
                BItemType = ffi._get_cached_btype(tp.item)
                length, rest = divmod(size, ffi.sizeof(BItemType))
                if rest != 0:
                    raise ffiplatform.VerificationError(
                        "bad size: %r does not seem to be an array of %s" %
                        (name, tp.item))
                tp = tp.resolve_length(length)
            # 'value' is a <cdata 'type *'> which we have to replace with
            # a <cdata 'type[N]'> if the N is actually known
            if tp.length is not None:
                BArray = ffi._get_cached_btype(tp)
                value = ffi.cast(BArray, value)
                setattr(library, name, value)
            return
        # remove ptr=<cdata 'int *'> from the library instance, and replace
        # it by a property on the class, which reads/writes into ptr[0].
        ptr = value
        delattr(library, name)
        def getter(library):
            return ptr[0]
        def setter(library, value):
            ptr[0] = value
        setattr(type(library), name, property(getter, setter))
        type(library)._cffi_dir.append(name)


class FFILibrary(object):
    __metaclass__ = FFILibraryMeta

    def __init__(self):
        # Build FFILibrary instance and call _cffi_setup().
        # this will set up some fields like '_cffi_types', and only then
        # it will invoke the chained list of functions that will really
        # build (notably) the constant objects, as <cdata> if they are
        # pointers, and store them as attributes on the 'library' object.
        super(FFILibrary, self).__init__()
        if _libmodule._cffi_setup(FFILibrary._ctypes_ordered,
                                  ffiplatform.VerificationError,
                                  self):
            import warnings
            warnings.warn("reimporting %r might overwrite older definitions"
                          % (_libmodule.__name__))
        # finally, call the loaded_cpy_xxx() functions.  This will perform
        # the final adjustments, like copying the Python->C wrapper
        # functions from the module to the 'library' object, and setting
        # up the FFILibrary class with properties for the global C variables.
        with ffi._lock:
            FFILibrary._load('loaded', library=self)


lib = FFILibrary()
'''
