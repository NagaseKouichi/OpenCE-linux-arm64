#!/usr/bin/env python3
"""Allowlisted experimental ARM64 runtime zip, with no game assets or libc."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/linux_arm64'

def guest_abi_version(data):
    """Read the guest contract from the load segment, not the source version."""
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    for i in range(count):
        kind, flags, file_offset, address, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
        if kind == 1 and address == 0x88000000 and length >= 8:
            magic, version = struct.unpack_from('<II', data, file_offset)
            if magic == 0x4f4c4148:
                return version
    raise ValueError('guest ABI header not found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BUILD / 'halo-linux-arm64-experimental-runtime.zip')
    args = parser.parse_args()
    files = {
        'Halo': ROOT / 'port/linux_arm64/Halo',
        'halo-host': BUILD / 'halo-host',
        'halo_guest.elf': BUILD / 'halo_guest.elf',
        'sdl3-build/libSDL3.so.0': BUILD / 'sdl3-build/libSDL3.so.0',
        'README.md': ROOT / 'port/linux_arm64/README.md',
        'licenses/AGPL-3.0.txt': ROOT / 'LICENSE',
        'licenses/CC0-1.0.txt': ROOT / 'LICENSES/CC0-1.0.txt',
        'licenses/stb_vorbis.txt': ROOT / 'port/third_party/stb_vorbis/LICENSE',
        'licenses/SDL.txt': BUILD / 'third_party/SDL3/LICENSE.txt',
        'licenses/musl.txt': BUILD / 'third_party/musl-1.2.5/COPYRIGHT',
        'licenses/tomlc17.txt': ROOT / 'port/third_party/tomlc17/LICENSE',
        'licenses/miniupnpc.txt': ROOT / 'port/third_party/miniupnpc/LICENSE',
        'licenses/kcp.txt': ROOT / 'port/third_party/kcp/LICENSE',
        'licenses/mbedtls.txt': ROOT / 'port/third_party/mbedtls/LICENSE',
        'licenses/expat.txt': ROOT / 'port/third_party/expat/COPYING',
        'licenses/opus.txt': ROOT / 'port/third_party/opus/COPYING',
        'licenses/monocypher.md': ROOT / 'port/third_party/monocypher/LICENCE.md',
        'licenses/zlib.txt': ROOT / 'port/third_party/zlib/LICENSE',
        'licenses/stb.txt': ROOT / 'port/third_party/stb/LICENSE',
        'licenses/smaa.txt': ROOT / 'port/third_party/smaa/LICENSE',
        'licenses/Overpass.txt': ROOT / 'port/assets/fonts/Overpass-OFL.txt',
        'licenses/OpenCE.txt': ROOT / 'port/assets/fonts/OpenCE-OFL.txt',
        'licenses/Newtown.txt': ROOT / 'port/assets/fonts/Newtown-LICENSE.txt',
        'licenses/art-authors.md': ROOT / 'AUTHORS.md',
    }
    contents = {name: path.read_bytes() for name, path in files.items()}
    for name in ['halo-host', 'halo_guest.elf', 'sdl3-build/libSDL3.so.0']:
        data = contents[name]
        if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
            parser.error(f'{name} is not an ELF64 little-endian AArch64 artifact')
    abi_version = guest_abi_version(contents['halo_guest.elf'])
    match = re.search(r'#define HALO_GUEST_ABI_VERSION (\d+)',
                      (ROOT / 'port/android/include/halo_android_abi.h').read_text())
    if match is None or abi_version != int(match.group(1)):
        parser.error('stale guest ABI; rebuild host and guest together before packaging')
    manifest = {
        'guest_abi_version': abi_version,
        'status': 'experimental; not real-device gameplay validated',
        'upstream_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_working_tree_modified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
        'requires': ['Linux AArch64', '4096-byte pages', 'glibc >= 2.38', 'EGL / OpenGL ES 3.x', 'user-owned game data'],
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
        'excluded': ['disc images', 'maps', 'caches', 'saves', 'target libc / graphics drivers'],
    }
    contents['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            info = zipfile.ZipInfo('halo-linux-arm64/' + name)
            info.create_system = 3
            mode = 0o755 if name in ('Halo', 'halo-host', 'sdl3-build/libSDL3.so.0') else 0o644
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    print(args.output.resolve())
    print('sha256=' + hashlib.sha256(args.output.read_bytes()).hexdigest())

if __name__ == '__main__':
    main()
