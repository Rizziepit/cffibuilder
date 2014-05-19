from cffibuilder import Builder


builder = Builder()
builder.cdef("""
    typedef uint8_t Uint8;
    Uint8 _pygame_SDL_BUTTON(Uint8 X);
""")
builder.build(
    "_sdl",
    libraries=['SDL'],
    include_dirs=['/usr/include/SDL', '/usr/local/include/SDL'],
    source="""
    #include <SDL.h>

    Uint8 _pygame_SDL_BUTTON(Uint8 X) {
        return SDL_BUTTON(X);
    }
""")

import _sdl
print dir(_sdl.lib)
print dir(_sdl.ffi)
