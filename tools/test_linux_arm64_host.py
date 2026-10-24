#!/usr/bin/env python3
"""Native CLI/mapping tests of the Linux host (no SDL/game assets required).

The link shim replaces only graphics and sampling dependencies unavailable on
CI. Main, ELF loader, low-memory allocator and low-stack threading are real C.
A synthetic test trampoline proves boot ABI plumbing, not game execution.
"""
import os
import platform
import struct
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HostRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = ROOT / 'build/tmp/host-tests/halo-host'
        cls.binary.parent.mkdir(parents=True, exist_ok=True)
        shim = cls.binary.parent / 'dependency_shim.c'
        shim.write_text('''#include "host.h"
#include "host_startup.h"
#include <string.h>
#include <stdlib.h>
void host_android_path(int which, char *buffer, uint32_t size);
static void host_test_start(uint32_t address)
{
    struct halo_guest_boot *boot = (void *)(uintptr_t)address;
    uint32_t *argv = (void *)(uintptr_t)boot->argv;
    uint32_t *env = (void *)(uintptr_t)boot->environment;
    char stack_marker;
    char path[4096];
    if ((uintptr_t)&stack_marker >= 0x100000000ULL ||
        boot->argc != 1 || boot->page_size != 4096 || argv[1] ||
        strcmp((char *)(uintptr_t)argv[0], "halo")) host_exit(90);
    unsigned found = 0;
    for (unsigned i = 0; env[i]; i++) {
        char *entry = (char *)(uintptr_t)env[i];
        if (!strncmp(entry, "HALO_DATA_ROOT=", 15)) {
            host_android_path(0, path, sizeof(path));
            if (strcmp(path, entry + 15)) host_exit(91);
            found |= 1;
        }
        if (!strncmp(entry, "HALO_SAVE_ROOT=", 15)) {
            host_android_path(1, path, sizeof(path));
            if (strcmp(path, entry + 15)) host_exit(92);
            found |= 2;
        }
        if (!strncmp(entry, "HALO_CONFIG_PATH=", 17)) found |= 4;
        if (!strcmp(entry, "HALO_TEST_SENTINEL=preserved")) found |= 8;
    }
    if (found != 15) host_exit(93);
    host_logf(HOST_LOG_INFO, "synthetic guest boot OK: low stack, argv, environment, paths");
    host_exit(0);
}
int host_startup_sdl_import(struct host_startup *p, const char *i, char *e, size_t n) {
    (void)i; (void)e; (void)n; return p->maps_found ? 1 : 0;
}
void host_linux_sdl_main_ready(void) {}
void host_debug_start_sampler(const char *s) {(void)s;}
void host_debug_thread_started(void) {}
void host_debug_thread_exited(void) {}
void *host_resolve_import(const char *s) {return !strcmp(s, "host_test_start") ? (void *)host_test_start : 0;}
void *host_gl_resolve(const char *s) {(void)s; return 0;}
''')
        env = dict(os.environ, TMPDIR=str(ROOT / 'build/tmp'))
        command = [os.environ.get('CC', 'gcc'), '-D_GNU_SOURCE', '-DHALO_LINUX_ARM64_HOST',
                   '-Wall', '-Wextra', '-Werror', '-pthread',
                   '-Iport/android/host', '-Iport/android/include', '-Iport/third_party/tomlc17',
                   '-Iport/linux_arm64/host',
                   'port/linux_arm64/host/host_startup.c',
                   'port/linux_arm64/host/host_main.c', 'port/android/host/host_memory.c',
                   'port/android/host/host_loader.c', 'port/android/host/host_thread.c',
                   'port/android/host/host_watch_hash.c',
                   'port/third_party/tomlc17/tomlc17.c', str(shim), '-o', str(cls.binary)]
        subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True, text=True)

    def run_host(self, *args):
        self.assertTrue(self.binary.is_file(), 'Linux host executable has not been implemented/built')
        return subprocess.run([str(self.binary), *args], text=True, capture_output=True, timeout=10)

    def test_preflight_without_game_files(self):
        result = self.run_host('--preflight')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('page_size=4096', result.stdout)
        self.assertIn('window=0x80000000', result.stdout)
        self.assertIn('image=0x88000000', result.stdout)

    def preload_probe(self, name, source):
        path = self.binary.parent / (name + '.c')
        library = path.with_suffix('.so')
        path.write_text(source)
        subprocess.run([os.environ.get('CC', 'gcc'), '-shared', '-fPIC', '-D_GNU_SOURCE',
                        '-Wall', '-Wextra', '-Werror', str(path), '-ldl', '-o', str(library)],
                       env=dict(os.environ, TMPDIR=str(ROOT / 'build/tmp')), check=True)
        return subprocess.run([str(self.binary), '--preflight'], text=True,
                              capture_output=True, timeout=10,
                              env=dict(os.environ, LD_PRELOAD=str(library)))

    def test_non_4kb_pages_rejected_before_mapping(self):
        result = self.preload_probe('pages16k', '''#include <unistd.h>
#include <dlfcn.h>
#include <sys/mman.h>
long sysconf(int name) {
    if (name == _SC_PAGESIZE) return 16384;
    long (*real)(int) = dlsym(RTLD_NEXT, "sysconf");
    return real(name);
}
void *mmap(void *a, size_t n, int p, int f, int d, off_t o) {
    (void)a; (void)n; (void)p; (void)f; (void)d; (void)o;
    _exit(95); /* No mapping may occur after an incompatible-page decision. */
}
''')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('requires 4096-byte pages', result.stderr)
        self.assertIn('16384', result.stderr)

    def test_fixed_window_collision_preserves_existing_mapping(self):
        result = self.preload_probe('collision', '''#include <stdio.h>
#include <unistd.h>
#include <sys/mman.h>
static volatile unsigned *marker;
__attribute__((constructor)) static void occupy(void) {
    marker = mmap((void *)0x80000000UL, 4096, PROT_READ | PROT_WRITE,
                  MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (marker != (void *)0x80000000UL) _exit(96);
    *marker = 0x12345678;
}
__attribute__((destructor)) static void verify(void) {
    if (*marker != 0x12345678) _exit(97);
    fputs("existing mapping preserved\\n", stderr);
}
''')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('cannot reserve the Xbox memory window', result.stderr)
        self.assertIn('existing mapping preserved', result.stderr)

    def test_missing_guest_is_diagnosed(self):
        result = self.run_host('--guest', str(ROOT / 'build/tmp/host-tests/missing.elf'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot read guest image', result.stderr)

    def test_default_guest_is_beside_executable(self):
        result = self.run_host()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.binary.parent / 'halo_guest.elf'), result.stderr)

    def test_invalid_guest_is_rejected_by_loader(self):
        path = self.binary.parent / 'invalid.elf'
        path.write_bytes(b'not an ELF')
        result = self.run_host('--guest', str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not an AArch64 executable', result.stderr)

    def test_truncated_program_headers_are_rejected(self):
        ident = b'\x7fELF' + bytes([2, 1, 1, 0]) + bytes(8)
        path = self.binary.parent / 'truncated.elf'
        path.write_bytes(struct.pack('<16sHHIQQQIHHHHHH', ident, 2, 183, 1, 0,
                                     0x100000, 0, 0, 64, 56, 1, 0, 0, 0))
        result = self.run_host('--guest', str(path))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('invalid guest ELF program headers', result.stderr)

    def test_low_stack_guest_boot_with_xdg_paths(self):
        if platform.machine() != 'x86_64':
            self.skipTest('the synthetic native test trampoline is x86_64, not game code')
        base = 0x88000000
        payload = bytearray(4096)
        struct.pack_into('<11I', payload, 0, 0x4F4C4148, 2, base + 4096,
                         base + 128, base + 160, base + 144, base + 256, 0, 0, 0, 0)
        struct.pack_into('<I', payload, 144, 1)
        payload[160:176] = b'host_test_start\0'
        # Jump through the loader-populated LP64 import slot with boot in rdi.
        payload[256:268] = b'\x48\xb8' + struct.pack('<Q', base + 128) + b'\xff\x20'
        ident = b'\x7fELF' + bytes([2, 1, 1, 0]) + bytes(8)
        elf = struct.pack('<16sHHIQQQIHHHHHH', ident, 2, 183, 1, base + 256,
                          64, 0, 0, 64, 56, 1, 0, 0, 0)
        ph = struct.pack('<IIQQQQQQ', 1, 7, 4096, base, base, 4096, 4096, 4096)
        guest = self.binary.parent / 'synthetic.elf'
        guest.write_bytes(elf + ph + bytes(4096 - len(elf) - len(ph)) + payload)
        data = self.binary.parent / 'data'
        (data / 'maps').mkdir(parents=True, exist_ok=True)
        (data / 'maps/ui.map').write_bytes(b'')  # only a path marker; never game data
        state = self.binary.parent / 'xdg-state'
        save = self.binary.parent / 'xdg-data/halo-linux'
        save.mkdir(parents=True, exist_ok=True)
        save.chmod(0o750)
        env = dict(os.environ, XDG_DATA_HOME=str(save.parent), XDG_STATE_HOME=str(state), HALO_DATA_ROOT=str(data), HALO_TEST_SENTINEL='preserved')
        env.pop('HALO_SAVE_ROOT', None)
        result = subprocess.run([str(self.binary), '--guest', str(guest)], cwd=self.binary.parent,
                                env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('synthetic guest boot OK', result.stderr)
        self.assertIn('data ' + str(data), result.stderr)
        self.assertIn('saves ' + str(save), result.stderr)
        self.assertEqual(save.stat().st_mode & 0o777, 0o750, 'existing save permissions changed')

    def test_help(self):
        result = self.run_host('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--guest', result.stdout)
        self.assertIn('--preflight', result.stdout)

    def test_print_paths_does_not_require_guest_or_create_saves(self):
        result = self.run_host('--print-paths')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('config=', result.stdout)
        self.assertIn('saves=', result.stdout)


if __name__ == '__main__':
    unittest.main()
