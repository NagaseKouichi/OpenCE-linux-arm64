"""Package the actual locally built artifacts, never assets from a game disc."""
import json
import re
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

class RuntimePackageTests(unittest.TestCase):
    def test_reads_guest_abi_from_actual_elf(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('arm64_package', ROOT / 'tools/package_linux_arm64.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        guest_path = ROOT / 'build/linux_arm64/smoke/abi-guest.elf'
        if not guest_path.exists():
            self.skipTest('requires built original ABI fixture')
        self.assertEqual(module.guest_abi_version(guest_path.read_bytes()), 2)

    def test_runtime_allowlist_and_architecture(self):
        if not (ROOT / 'build/linux_arm64/halo-host').exists():
            self.skipTest('requires real built ARM64 artifacts')
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/tmp') as temp:
            path = Path(temp) / 'runtime.zip'
            result = subprocess.run([sys.executable, str(ROOT / 'tools/package_linux_arm64.py'),
                                     '--output', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                for name in ['halo-host', 'halo_guest.elf', 'Halo', 'sdl3-build/libSDL3.so.0', 'README.md', 'manifest.json']:
                    self.assertIn('halo-linux-arm64/' + name, names)
                self.assertFalse(any('/maps/' in n or n.endswith(('.map', '.iso', '.xiso', '.xbe')) for n in names))
                for name in ['halo-host', 'halo_guest.elf', 'sdl3-build/libSDL3.so.0']:
                    binary = z.read('halo-linux-arm64/' + name)
                    self.assertEqual(binary[:4], b'\x7fELF')
                    self.assertEqual(int.from_bytes(binary[18:20], 'little'), 183)
                manifest = json.loads(z.read('halo-linux-arm64/manifest.json'))
                abi_match = re.search(r'#define HALO_GUEST_ABI_VERSION (\d+)',
                    (ROOT / 'port/android/include/halo_android_abi.h').read_text())
                assert abi_match is not None
                expected_abi = int(abi_match.group(1))
                self.assertEqual(manifest['guest_abi_version'], expected_abi)
                guest = z.read('halo-linux-arm64/halo_guest.elf')
                offset = struct.unpack_from('<Q', guest, 32)[0]
                size, count = struct.unpack_from('<HH', guest, 54)
                actual_abi = None
                for i in range(count):
                    kind, flags, file_offset, address, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', guest, offset + i * size)
                    if kind == 1 and address == 0x88000000:
                        actual_abi = struct.unpack_from('<II', guest, file_offset)[1]
                self.assertEqual(actual_abi, expected_abi)
                self.assertTrue(z.getinfo('halo-linux-arm64/Halo').external_attr >> 16 & 0o111)

if __name__ == '__main__':
    unittest.main()
