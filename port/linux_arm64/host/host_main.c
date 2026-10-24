/*
 * Linux ARM64 LP64 host for the ILP32 Halo guest. No Android/JVM bootstrap.
 * SDL is initialized on the low-stack game thread, which becomes SDL's main
 * thread; the original launcher thread never initializes or pumps SDL video.
 */
#include "host.h"
#include "tomlc17.h"
#include "host_startup.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

void host_install_signal_handlers(void);
void host_linux_sdl_main_ready(void);

static struct host_startup startup;
#define data_root startup.data
#define save_root startup.saves
static const char *import_iso;
static int print_paths;

void host_logf(int priority, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    flockfile(stderr);
    fprintf(stderr, "halo [%s]: ", priority >= HOST_LOG_ERROR ? "error" :
            priority >= HOST_LOG_WARN ? "warning" : "info");
    vfprintf(stderr, format, arguments);
    fputc('\n', stderr);
    funlockfile(stderr);
    va_end(arguments);
}

void host_log(int priority, const char *text)
{
    host_logf(priority, "%s", text);
}

void host_fatal(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    fputs("halo [fatal]: ", stderr);
    vfprintf(stderr, format, arguments);
    fputc('\n', stderr);
    va_end(arguments);
    exit(1);
}

void host_abort(const char *reason)
{
    host_logf(HOST_LOG_ERROR, "guest abort: %s", reason);
    abort();
}

void host_exit(int code)
{
    host_logf(HOST_LOG_INFO, "the game exited (%d)", code);
    exit(code);
}

int host_errno(void) { return errno; }

/* Keep this ABI import: the HALO_ANDROID guest asks for these two paths. */
void host_android_path(int which, char *buffer, uint32_t size)
{
    snprintf(buffer, size, "%s", which ? save_root : data_root);
}

/* Linux has no Android system-gesture exclusion edges. */
void host_gesture_insets(int *insets)
{
    memset(insets, 0, 4 * sizeof(*insets));
}

static void path_format(char *out, size_t capacity, const char *root, const char *suffix)
{
    if (snprintf(out, capacity, "%s%s", root, suffix) >= (int)capacity)
        host_fatal("path is too long: %s", root);
}

/* All pointers inside the boot contract, argv, and environ must be low. */
static uint32_t make_boot(void)
{
    const size_t size = 0x10000;
    char *memory = host_low_map(size, PROT_READ | PROT_WRITE);
    struct halo_guest_boot *boot;
    uint32_t *argv, *env;
    char *strings;
    char zone[64];
    time_t now = time(NULL);
    struct tm local;
    long offset;
    const char *names[] = { "HOME", "HALO_DATA_ROOT", "HALO_SAVE_ROOT", "TZ",
        "SDL_VIDEODRIVER", "SDL_AUDIODRIVER", "HALO_DISPLAY_WIDTH", "LANG", "HALO_CONFIG_PATH", NULL };
    const char *values[] = { save_root, data_root, save_root, zone,
        getenv("SDL_VIDEODRIVER"), getenv("SDL_AUDIODRIVER"),
        getenv("HALO_DISPLAY_WIDTH"), getenv("LANG"), startup.config };
    unsigned count = 0;
    if (!memory) host_fatal("cannot allocate the guest's environment");
    localtime_r(&now, &local);
    offset = -local.tm_gmtoff;
    snprintf(zone, sizeof(zone), "<L>%s%ld:%02ld", offset < 0 ? "-" : "", labs(offset) / 3600, (labs(offset) / 60) % 60);
    boot = (struct halo_guest_boot *)memory;
    argv = (uint32_t *)(memory + sizeof(*boot));
    env = argv + 2;
    extern char **environ;
    size_t environment_count = 0;
    while (environ[environment_count]) environment_count++;
    if ((environment_count + 16) * sizeof(*env) > size / 2) host_fatal("guest environment is too large");
    strings = (char *)(env + environment_count + 16);
    strcpy(strings, "halo");
    argv[0] = (uint32_t)(uintptr_t)strings;
    argv[1] = 0;
    strings += 5;
    for (unsigned i = 0; names[i]; i++) {
        if (!values[i]) continue;
        size_t length = strlen(names[i]) + strlen(values[i]) + 2;
        if (length > (size_t)(memory + size - strings)) host_fatal("guest environment is too large");
        env[count++] = (uint32_t)(uintptr_t)strings;
        snprintf(strings, length, "%s=%s", names[i], values[i]);
        strings += length;
    }
    /* Preserve desktop settings and SDL driver overrides without high pointers. */
    for (size_t i = 0; environ[i]; i++) {
        const char *entry = environ[i];
        if (strncmp(entry, "HALO_", 5) && strncmp(entry, "SDL_", 4)) continue;
        int duplicate = 0;
        for (unsigned j = 0; names[j]; j++) {
            size_t name_length = strlen(names[j]);
            if (!strncmp(entry, names[j], name_length) && entry[name_length] == '=') duplicate = 1;
        }
        if (duplicate) continue;
        size_t length = strlen(entry) + 1;
        if (length > (size_t)(memory + size - strings)) host_fatal("guest environment is too large");
        env[count++] = (uint32_t)(uintptr_t)strings;
        memcpy(strings, entry, length);
        strings += length;
    }
    env[count] = 0;
    boot->argc = 1;
    boot->argv = (uint32_t)(uintptr_t)argv;
    boot->environment = (uint32_t)(uintptr_t)env;
    boot->page_size = 4096;
    return (uint32_t)(uintptr_t)boot;
}

static void start_sampler(void)
{
    char path[PATH_MAX], seconds[32];
    path_format(path, sizeof(path), startup.config, "");
    toml_result_t result = toml_parse_file_ex(path);
    if (!result.ok) return;
    toml_datum_t value = toml_seek(result.toptab, "debug.sample_seconds");
    double interval = value.type == TOML_FP64 ? value.u.fp64 :
        value.type == TOML_INT64 ? (double)value.u.int64 : 0;
    if (interval > 0) {
        snprintf(seconds, sizeof(seconds), "%g", interval);
        host_debug_start_sampler(seconds);
    }
    toml_free(result);
}

static void *game_main(void *argument)
{
    char error[1024] = "";
    (void)argument;
    host_linux_sdl_main_ready();
    int result = host_startup_sdl_import(&startup, import_iso, error, sizeof(error));
    if (result < 0) host_fatal("%s", error);
    if (!result) host_exit(0);
    if (print_paths) {
        printf("data=%s\nsaves=%s\nconfig=%s\n", data_root, save_root, startup.config);
        host_exit(0);
    }
    if (!host_startup_mkdir(save_root, error, sizeof(error))) host_fatal("%s", error);
    uint32_t boot = make_boot();
    host_logf(HOST_LOG_INFO, "data %s, saves %s", data_root, save_root);
    start_sampler();
    host_run_guest_main(boot);
}

static void load_guest(const char *path)
{
    FILE *file = fopen(path, "rb");
    long length;
    void *image;
    if (!file) host_fatal("cannot read guest image %s: %s", path, strerror(errno));
    if (fseek(file, 0, SEEK_END) || (length = ftell(file)) <= 0 || fseek(file, 0, SEEK_SET))
        host_fatal("cannot read guest image %s: empty or unseekable file", path);
    image = malloc((size_t)length);
    if (!image) host_fatal("cannot allocate guest image buffer");
    if (fread(image, 1, (size_t)length, file) != (size_t)length)
        host_fatal("cannot read guest image %s: %s", path, strerror(errno));
    fclose(file);
    if (host_load_image(image, (size_t)length)) host_fatal("cannot load guest image %s; see diagnostics above", path);
    free(image);
}

int main(int argc, char **argv)
{
    const char *guest = NULL;
    char default_guest[PATH_MAX];
    int preflight = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--help")) {
            puts("Usage: halo [--guest PATH] [--preflight]\n"
                 "  --guest PATH  Load this guest ELF instead of halo_guest.elf beside the binary\n"
                 "  --preflight   Check 4KB pages and fixed guest address reservations (no game data)\n"
                 "  --help        Show this help\n"
                 "  --print-paths Print selected paths without starting the game\n"
                 "  --import-iso PATH Extract an Xbox ISO/XISO (combine with --print-paths for import only)\n"
                 "Data: HALO_DATA_ROOT, config paths.data, cwd maps/, exe maps/, assets/\n"
                 "Saves: HALO_SAVE_ROOT, config paths.saves, or $XDG_DATA_HOME/halo-linux");
            return 0;
        } else if (!strcmp(argv[i], "--preflight")) preflight = 1;
        else if (!strcmp(argv[i], "--print-paths")) print_paths = 1;
        else if (!strcmp(argv[i], "--import-iso") && i + 1 < argc) import_iso = argv[++i];
        else if (!strcmp(argv[i], "--guest") && i + 1 < argc) guest = argv[++i];
        else { fprintf(stderr, "halo: unknown or incomplete option %s (see --help)\n", argv[i]); return 2; }
    }
    if (preflight) {
        if (host_memory_initialize(HALO_GUEST_IMAGE_BASE, HALO_GUEST_IMAGE_RESERVE)) return 1;
        printf("preflight OK: page_size=%ld window=0x%08x image=0x%08x (64 MiB reservation)\n",
               sysconf(_SC_PAGESIZE), HALO_GUEST_WINDOW_BASE, HALO_GUEST_IMAGE_BASE);
        return 0;
    }
    char executable[PATH_MAX], error[1024];
    ssize_t exe_length = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (exe_length < 0 || exe_length >= (ssize_t)sizeof(executable) - 1) host_fatal("cannot resolve executable path");
    executable[exe_length] = 0;
    if (!host_startup_resolve(&startup, executable, error, sizeof(error))) host_fatal("%s", error);
    if (print_paths && !import_iso) {
        printf("data=%s\nsaves=%s\nconfig=%s\n", data_root, save_root, startup.config);
        return 0;
    }
    if (!guest) {
        ssize_t length = readlink("/proc/self/exe", default_guest, sizeof(default_guest) - 1);
        if (length < 0 || length >= (ssize_t)sizeof(default_guest) - 1)
            host_fatal("cannot resolve executable path: %s", strerror(errno));
        default_guest[length] = '\0';
        char *slash = strrchr(default_guest, '/');
        if (!slash || (size_t)(slash - default_guest) + sizeof("/halo_guest.elf") > sizeof(default_guest))
            host_fatal("executable path is too long");
        strcpy(slash, "/halo_guest.elf");
        guest = default_guest;
    }
    host_logf(HOST_LOG_INFO, "Halo Linux ARM64 host starting");
    host_install_signal_handlers();
    if (print_paths && import_iso) {
        if (host_memory_initialize(HALO_GUEST_IMAGE_BASE, HALO_GUEST_IMAGE_RESERVE)) return 1;
    } else load_guest(guest);
    int thread_error = host_native_thread_create(game_main, NULL, 16 * 1024 * 1024);
    if (thread_error) host_fatal("cannot start the low-stack game thread: %s", strerror(thread_error));
    for (;;) pause(); /* guest host_exit terminates the process */
}
