"""Executable build graph contracts for the Linux ARM64 ILP32 port."""
import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from tools import linux_arm64_build
from tools.ninja_syntax import Writer

ROOT = Path(__file__).resolve().parent.parent


def test_linux_arm64_graph_compiles_real_guest_and_native_host():
    output = io.StringIO()
    solution = SimpleNamespace(build_dir=Path('build'), linux_arm64=True,
                               linux_arm64_cc='aarch64-linux-gnu-gcc', port_pgo='off')
    linux_arm64_build.generate_linux_arm64_build(Writer(output), solution)
    graph = output.getvalue().replace(' $\n    ', ' ')
    assert 'build build/linux_arm64/halo_guest.elf: linux_arm64_guest_link ' in graph
    assert '--target=arm64_32-apple-watchos' in graph
    assert '-DHALO_ANDROID=1' in graph
    assert '-DHALO_LINUX_ARM64=1' in graph
    assert 'tools/android_asm_convert.py' in graph
    assert 'source/ai/ai.c' in graph
    assert 'build build/linux_arm64/halo-host: linux_arm64_host_link ' in graph
    for source in ['port/linux_arm64/host/host_main.c', 'host_memory.c', 'host_loader.c',
                   'host_thread.c', 'host_debug.c', 'host_sdl.c', 'host_gl.c', 'host_syscall.c',
                   'host_watch_hash.c', 'host_touch.c', 'posix_files.c', 'posix_net.c',
                   'posix_upnp.c', 'posix_dtls.c', 'tomlc17.c']:
        assert source in graph
    for source in ['port/third_party/expat/xmlparse.c',
                   'port/third_party/monocypher/monocypher.c',
                   'port/third_party/monocypher/monocypher-ed25519.c',
                   'port/third_party/opus/src/opus.c', 'port/third_party/zlib/inflate.c',
                   'port/third_party/mbedtls/library/ssl_tls.c',
                   'guest/gen/hud_hires_assets.c', 'port/third_party/stb_vorbis/stb_vorbis.c']:
        assert source in graph
    normalized_graph = ' '.join(graph.replace('$\n', '').split())
    assert '-iquote port/linux/game' in normalized_graph
    assert '-Iport/third_party/monocypher' in normalized_graph
    assert 'PKG_CONFIG_LIBDIR=/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig' in graph
    assert '-DHALO_LINUX_ARM64_HOST=1' in graph
    assert 'build linux_arm64_guest: phony build/linux_arm64/halo_guest.elf' in graph
    assert 'android_ndk' not in graph
    assert 'gradle' not in graph.lower()
    assert 'host_preflight.c' not in graph


def test_linux_arm64_profile_uses_shared_configuration_defines():
    output = io.StringIO()
    solution = SimpleNamespace(build_dir=Path('build'), linux_arm64=True,
                               port_pgo='off', port_profile=True, port_release=True)
    linux_arm64_build.generate_linux_arm64_build(Writer(output), solution)
    graph = ' '.join(output.getvalue().replace('$\n', '').split())
    assert '-DHALO_PROFILE' in graph
    assert '-DHALO_RELEASE' in graph


def test_linux_arm64_is_explicitly_opt_in(monkeypatch):
    def forbidden_fetch():
        raise AssertionError('disabled port must not download dependencies')
    monkeypatch.setattr(linux_arm64_build, 'fetch_third_party', forbidden_fetch)
    output = io.StringIO()
    linux_arm64_build.generate_linux_arm64_build(Writer(output), SimpleNamespace())
    assert not output.getvalue()


def test_configure_exposes_explicit_linux_arm64_enable():
    result = subprocess.run([sys.executable, 'configure.py', '--help'], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '--linux-arm64 ' in result.stdout or '[--linux-arm64]' in result.stdout


def test_isolated_container_build_entry_point():
    result = subprocess.run([sys.executable, 'tools/build_linux_arm64.py', '--help'],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '--image' in result.stdout
    assert '--target' in result.stdout
    recipe = (ROOT / 'tools/linux_arm64_cross.Dockerfile').read_text()
    assert 'gcc-aarch64-linux-gnu' in recipe
    assert 'python3-pytest' in recipe
    assert 'libx11-dev:arm64' in recipe

