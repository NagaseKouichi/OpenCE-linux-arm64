/*
 * First Linux AArch64 host executable.
 *
 * The full port will load an ILP32 AArch64 guest image at fixed low addresses.
 * Before SDL, audio, or game-data code runs, verify the two kernel guarantees
 * that make that ABI possible: 4 KiB pages and an unoccupied Xbox window.
 */

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define HALO_GUEST_WINDOW_BASE ((void *)0x80000000UL)
#define HALO_GUEST_WINDOW_SIZE (0x08000000UL)

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

int main(void)
{
    long page_size = sysconf(_SC_PAGESIZE);
    void *mapping;

    if (page_size != 4096) {
        fprintf(stderr, "halo ARM64 requires 4 KiB pages; this kernel uses %ld bytes\n", page_size);
        return 2;
    }

    mapping = mmap(HALO_GUEST_WINDOW_BASE, HALO_GUEST_WINDOW_SIZE, PROT_NONE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
    if (mapping == MAP_FAILED) {
        fprintf(stderr, "cannot reserve Xbox guest window at 0x80000000: %s\n", strerror(errno));
        return 3;
    }
    if (mapping != HALO_GUEST_WINDOW_BASE) {
        fprintf(stderr, "kernel reserved the Xbox guest window at an unexpected address\n");
        munmap(mapping, HALO_GUEST_WINDOW_SIZE);
        return 4;
    }

    puts("Linux ARM64 guest preflight passed: 4 KiB pages and Xbox window available");
    munmap(mapping, HALO_GUEST_WINDOW_SIZE);
    return 0;
}
