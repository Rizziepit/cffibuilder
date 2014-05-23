from operator import itemgetter

from cffibuilder import Builder


def memoize(func):

    memo = {}

    def inner(*args, **kwargs):
        key = args
        key += tuple(map(itemgetter(1), sorted(kwargs.items(), key=itemgetter(0))))
        return memo.get(key, func(*args, **kwargs))

    return inner


@memoize
def build_module(name, cdef, source):
    builder = Builder()
    builder.cdef(cdef)
    builder.build(name, source=source)
    return __import__(name)
