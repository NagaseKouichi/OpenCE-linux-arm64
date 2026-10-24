/* LP64 adapters for the production desktop importer, not the game ABI. */
#include "host_startup.h"
#include "posix.h"
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
void platform_log(const char *format, ...) {
    va_list args; va_start(args,format);
    fputs("halo: ",stderr); vfprintf(stderr,format,args); fputc('\n',stderr); va_end(args);
}
/* posix_files.c supplies these in the host; standalone tests use this adapter. */
#ifndef HALO_HOST_POSIX_FILES
int posix_seek(int fd, posix_long low, posix_long high, int whence, posix_ulong *lo, posix_ulong *hi) {
    int64_t offset=(int64_t)(((uint64_t)(uint32_t)high<<32)|(uint32_t)low);
    off_t result=lseek(fd,(off_t)offset,whence);
    if (result<0) return -1;
    *lo=(uint32_t)result; *hi=(uint32_t)((uint64_t)result>>32); return 0;
}
int posix_make_directory(const char *path) { return mkdir(path,0755); }
#endif
