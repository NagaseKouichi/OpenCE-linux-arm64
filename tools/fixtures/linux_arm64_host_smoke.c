/* Original runtime test harness: shared production loader, memory and threads.
 * No SDL stubs are exercised; this isolates ILP32/LP64 ABI before rendering.
 */
#include "host.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
extern uint32_t host_get_tp(void);
extern void host_set_tp(uint32_t);
void host_debug_thread_started(void) {}
void host_debug_thread_exited(void) {}
#ifndef SMOKE_SDL
void *host_gl_resolve(const char *name) { (void)name; return NULL; }
#endif
void host_logf(int priority, const char *format, ...)
{
    (void)priority;
    va_list args; va_start(args, format); vfprintf(stderr, format, args);
    fputc('\n', stderr); va_end(args);
}
void host_log(int priority, const char *text) { host_logf(priority, "%s", text); }
void host_fatal(const char *format, ...)
{
    va_list args; va_start(args, format); vfprintf(stderr, format, args);
    fputc('\n', stderr); va_end(args); exit(9);
}
void host_exit(int status) { exit(status); }
#ifndef SMOKE_SDL
void *host_resolve_import(const char *name)
{
    if (!strcmp(name, "host_log")) return (void *)host_log;
    if (!strcmp(name, "host_exit")) return (void *)host_exit;
    if (!strcmp(name, "host_get_tp")) return (void *)host_get_tp;
    if (!strcmp(name, "host_set_tp")) return (void *)host_set_tp;
    return NULL;
}
#endif
static void *run(void *argument) {
#ifdef SMOKE_SDL
    extern void host_linux_sdl_main_ready(void);
    host_linux_sdl_main_ready();
#endif
    host_run_guest_main((uint32_t)(uintptr_t)argument);
}
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 3;
    if (fseek(f, 0, SEEK_END)) return 4;
    long length = ftell(f);
    if (length <= 0 || fseek(f, 0, SEEK_SET)) return 4;
    void *image = malloc((size_t)length);
    if (!image || fread(image, 1, (size_t)length, f) != (size_t)length) return 5;
    fclose(f);
    if (host_load_image(image, (size_t)length)) return 6;
    free(image);
    char *low = host_low_map(4096, PROT_READ | PROT_WRITE);
    if (!low) return 7;
    struct halo_guest_boot *boot = (struct halo_guest_boot *)low;
    uint32_t *guest_argv = (uint32_t *)(low + sizeof(*boot));
    char *name = (char *)(guest_argv + 2);
    strcpy(name, "abi-smoke");
    guest_argv[0] = (uint32_t)(uintptr_t)name;
    guest_argv[1] = 0;
    boot->argc = 1; boot->argv = (uint32_t)(uintptr_t)guest_argv;
    boot->environment = 0; boot->page_size = 4096;
    if (host_native_thread_create(run, boot, 1024 * 1024)) return 8;
    for (;;) pause();
}
