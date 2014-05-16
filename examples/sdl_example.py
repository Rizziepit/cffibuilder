from cffibuilder import Builder


builder = Builder()
builder.cdef("""
    typedef uint8_t Uint8;
    Uint8 _pygame_SDL_BUTTON(Uint8 X);
""")
builder.build(
    "sdllib",
    libraries=['SDL'],
    include_dirs=['/usr/include/SDL', '/usr/local/include/SDL'],
    source="""
    #include <SDL.h>

    Uint8 _pygame_SDL_BUTTON(Uint8 X) {
        return SDL_BUTTON(X);
    }
""")

import sdllib
print sdllib._pygame_SDL_BUTTON
print sdllib.new
print sdllib.NULL
