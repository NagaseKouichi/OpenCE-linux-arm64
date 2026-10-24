# OpenCE — experimental Linux ARM64 port

[中文说明](README-CN.md) · [Upstream README](docs/README.upstream.md)

Native Linux AArch64 port of [OpenCE](https://github.com/OpenCommunityEdition/OpenCE), based on upstream **build-268** (`5e27f3a2`). This is an unofficial, experimental port, not an emulator or an official upstream ARM64 release.

The game is an AArch64 ILP32 guest with 32-bit pointers; a Linux AArch64 LP64 host supplies SDL3, GLES and operating-system services. Xbox game data is not included. Provide your own original Xbox Halo: Combat Evolved disc image or extracted maps.

## Download and run

Download the runtime ZIP from [Releases](https://github.com/NagaseKouichi/OpenCE-linux-arm64/releases), unpack it into a writable directory and run:

```sh
chmod +x Halo halo-host
./Halo --preflight
./Halo
```

Requirements: Linux AArch64, **4096-byte pages**, glibc **2.38 or newer**, EGL/OpenGL ES 3.x, and a working SDL desktop backend (X11/XWayland supported by this build). Do not replace system libc or GPU drivers with cross-build libraries.

Startup reads `config.toml` beside the executable. It discovers `maps/` in the working/executable directories and upstream assets locations. If missing, it offers an Xbox ISO/XISO picker and progress display; the destination must be writable. File-picker availability depends on the desktop portal/zenity. Headless fallback:

```sh
./Halo --import-iso '/path/to/Halo.iso' --print-paths
```

To retain an existing separate data/save installation, create or merge this configuration (do not duplicate `[paths]`):

```toml
[paths]
data = '/absolute/path/to/data' # contains maps/
saves = '/absolute/path/to/saves'
```

Otherwise saves default to `$XDG_DATA_HOME/halo-linux` or `~/.local/share/halo-linux`. `HALO_DATA_ROOT` / `HALO_SAVE_ROOT` remain optional overrides. Previous ARM64 releases used a different default; existing saves are not automatically migrated. Back them up before upgrading. Always update host and guest together.

## Validation and limitations

A user confirmed main-menu display and music on an Adreno 830 ARM64 handheld with the retail-BSP fix. Build-268 itself still requires handheld retesting. Campaign gameplay, physical controller behavior, checkpoint compatibility, networking and sustained stability are not certified. QEMU/offscreen/dummy audio tests are not physical-device validation. Intro Bink movies are skipped.

- ARM64/startup/package/Linux regression: 50 passed, 4 skipped.
- Additional upstream tests: 82 passed, 3 skipped.
- Engine harness: 842 passed, one exact-float elevator-prediction assertion failed, also reproduced on pristine upstream.

See [ARM64 guide](port/linux_arm64/README.md) and [validation record](port/linux_arm64/VALIDATION.md).

## Build on x86_64 Linux

Python 3 and Docker are required; no handheld development packages are installed:

```sh
python3 tools/build_linux_arm64.py --jobs 4
python3 tools/package_linux_arm64.py
```

The build uses `--linux-arm64 --pgo=off --lto=off`. See the ARM64 guide for toolchain and smoke-test details.

## License and source

Upstream is **AGPL-3.0-or-later**; see [LICENSE](LICENSE), [CC0 notice](LICENSES/CC0-1.0.txt) and third-party notices. Releases include a matching source archive with local changes and build dependency sources. No release contains disc images, maps, game caches or saves. Original upstream documentation is preserved at [docs/README.upstream.md](docs/README.upstream.md).
