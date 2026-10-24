/* Original ABI smoke payload: no Halo data or game source required.
 * Built with the same arm64_32 -> ELF pipeline as the game guest.
 * It exercises low stacks, boot pointers, LP64 imports and guest TLS.
 */
#include "../../port/android/include/halo_android_abi.h"
#ifdef SMOKE_SDL
#include <SDL3/SDL.h>
#include "guest_host.h"
#endif
typedef unsigned int u32;
typedef unsigned long long u64;
_Static_assert(sizeof(void *) == 4, "guest must have ILP32 pointers");
_Static_assert(sizeof(long) == 4, "guest long must be 32 bits");
extern void host_log(int, const char *);
extern void host_exit(int) __attribute__((noreturn));
extern u32 host_get_tp(void);
extern void host_set_tp(u32);
extern char __guest_image_end[];
extern u64 __host_import_table[];
extern char __host_import_names[];
extern u32 __host_import_count;
extern void (*__guest_init_start[])(void);
extern void (*__guest_init_end[])(void);
struct boot { u32 argc, argv, environment, page_size; };
#ifdef SMOKE_SDL
static void audio_callback(void *userdata, u32 stream, int additional, int total)
{
    char marker;
    static float silence[4096];
    (void)userdata; (void)total;
    if ((u64)&marker >= 0x100000000ULL) host_exit(51);
    int size = additional > (int)sizeof(silence) ? (int)sizeof(silence) : additional;
    if (size > 0 && !host_sdl_put_audio_stream_data(stream, silence, size)) host_exit(52);
    host_log(4, "SDL guest audio callback passed: low stack and audio stream handle");
    host_exit(0);
}
static void smoke_sdl(void)
{
    if (!host_sdl_init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMEPAD)) host_exit(45);
    host_sdl_gl_set_attribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    host_sdl_gl_set_attribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    host_sdl_gl_set_attribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
    u32 window = host_sdl_create_window("Halo ABI smoke", 64, 64, SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN);
    if (!window) host_exit(46);
    u32 context = host_sdl_gl_create_context(window);
    if (!context || !host_sdl_gl_make_current(window, context)) host_exit(47);
    char version[128];
    host_gl_get_string(0x1F02, -1, version, sizeof(version)); /* GL_VERSION */
    host_log(4, version);
    SDL_AudioSpec spec = { SDL_AUDIO_F32, 2, 48000 };
    u32 stream = host_sdl_open_audio_stream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, (u32)audio_callback, 0);
    if (!stream || !host_sdl_resume_audio_stream_device(stream)) host_exit(48);
    long long deadline = host_sdl_ticks() + 10000;
    while (host_sdl_ticks() < deadline) {}
    host_exit(49); /* no callback */
}
#endif
static void smoke_start(const struct boot *boot)
{
    char marker;
    if ((u64)&marker >= 0x100000000ULL || !boot || boot->page_size != 4096)
        host_exit(41);
    if (!boot->argc || !boot->argv || !((char **)boot->argv)[0])
        host_exit(42);
    host_set_tp(0x1234);
    if (host_get_tp() != 0x1234)
        host_exit(43);
    host_log(4, "ILP32 guest smoke passed: low stack, boot argv, host imports and TLS");
#ifdef SMOKE_SDL
    smoke_sdl();
#endif
    host_exit(0);
}
static u32 attach(void) { return 0; }
static void detach(void) {}
__attribute__((section("__TEXT,__guest_header"), used))
const struct halo_guest_header __guest_header = {
    HALO_GUEST_MAGIC, HALO_GUEST_ABI_VERSION, (u32)__guest_image_end,
    (u32)__host_import_table, (u32)__host_import_names,
    (u32)&__host_import_count, (u32)smoke_start, 0, (u32)attach,
    (u32)detach, (u32)__guest_init_start, (u32)__guest_init_end
};
