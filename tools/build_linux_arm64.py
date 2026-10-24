#!/usr/bin/env python3
"""Repeatable native ARM64 cross build in an isolated Docker container.

    python3 tools/build_linux_arm64.py
    python3 tools/build_linux_arm64.py --target linux_arm64_guest

The default builds the compiler image from the adjacent Dockerfile. --image
uses an already provisioned image (and does not install anything on the host).
Game assets are not needed to compile, and are not copied into the image.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', help='existing x86_64 cross-toolchain Docker image')
    parser.add_argument('--target', choices=['linux_arm64', 'linux_arm64_guest', 'linux_arm64_host'],
                        default='linux_arm64')
    parser.add_argument('--jobs', type=int, default=4, help='parallel compile jobs (default: 4)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    root = Path(__file__).resolve().parent.parent
    tmp = root / 'build/tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    image = args.image or 'halo-linux-arm64-cross:local'
    if not args.image:
        subprocess.run(['docker', 'build', '--platform=linux/amd64', '-t', image,
                        '-f', str(root / 'tools/linux_arm64_cross.Dockerfile'),
                        str(root / 'tools')], check=True)
    commands = [
        'python3 -m pytest tools/test_linux_port.py tools/test_linux_arm64_port.py '
        'tools/test_linux_arm64_host.py tools/test_linux_arm64_launcher.py tools/test_linux_arm64_startup.py -q -p no:cacheprovider',
        'python3 configure.py --linux-arm64 --pgo=off --lto=off',
        f'ninja -j{args.jobs} {shlex.quote(args.target)}',
    ]
    if args.target != 'linux_arm64_host':
        commands.append('aarch64-linux-gnu-readelf -h build/linux_arm64/halo_guest.elf')
    if args.target != 'linux_arm64_guest':
        commands.append('aarch64-linux-gnu-readelf -h build/linux_arm64/halo-host')
    subprocess.run(['docker', 'run', '--rm', '--platform=linux/amd64',
                    '--user', f'{os.getuid()}:{os.getgid()}',
                    '-e', 'HOME=/repo/build/tmp', '-e', 'TMPDIR=/repo/build/tmp',
                    '-v', f'{root}:/repo', '-w', '/repo', image,
                    'sh', '-ec', ' && '.join(commands)], check=True)


if __name__ == '__main__':
    main()
