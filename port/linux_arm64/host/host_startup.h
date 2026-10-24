/* LP64-only startup; no game/XDK ABI types cross this boundary. */
#ifndef HALO_HOST_STARTUP_H
#define HALO_HOST_STARTUP_H
#include <stddef.h>
#include <limits.h>
struct host_startup { char data[PATH_MAX], saves[PATH_MAX], config[PATH_MAX]; int maps_found; };
struct host_import_ui {
    int (*ask)(void *, const char *);
    int (*choose)(void *, char *, size_t);
    int (*extract)(void *, const char *, const char *, char *, size_t);
    void *context;
};
int host_startup_resolve(struct host_startup *, const char *, char *, size_t);
/* 1 ready, 0 cancelled, -1 error. ISO override deliberately needs no dialog. */
int host_startup_import(struct host_startup *, const char *, const struct host_import_ui *, char *, size_t);
int host_startup_mkdir(const char *, char *, size_t);
int host_startup_sdl_import(struct host_startup *, const char *, char *, size_t);
void platform_log(const char *, ...) __attribute__((format(printf,1,2)));
#endif
