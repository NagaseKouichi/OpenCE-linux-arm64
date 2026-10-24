# Experimental Linux AArch64 port

This is a Linux LP64 host plus an AArch64 **ILP32** game guest. It is not an
ARM32 emulator and does not require Linux kernel ILP32 syscall support. The
game's pointers stay 32-bit; host libc/SDL/EGL run as ordinary 64-bit Linux.

## Status

The local ARM64 delta is synchronized with upstream build-268 (`5e27f3a2`).
The guest/host contract is ABI version 2; older version-1 guest images must
not be paired with the new host. Rebuild and package both together.
See [VALIDATION.md](VALIDATION.md) for separate historical and updated checks.

The first source/build/runtime-bridge milestone is implemented. Both real
AArch64 artifacts build, and the production host loads the full game ELF with
223 imports resolved. Original, game-data-free fixtures execute guest code,
boot arguments, low stacks, imports and TLS in an AArch64 userspace environment.
An additional offscreen test creates an OpenGL ES 3.2 context and executes a
guest audio callback through SDL's low-stack bridge.

**This is still an experimental release.** Initial runtime checks used
QEMU-backed AArch64 environments, Mesa software rendering and dummy audio.
After the retail BSP memory-layout fix, the user confirmed that the ARM64
handheld reached the main menu and played menu music normally (Adreno 830).
Campaign gameplay, physical controller behavior, saves and sustained stability
remain unverified; menu/audio success is not a complete gameplay acceptance.

## Build on an x86_64 Linux host

Clone recursively. Docker is the only host-side build dependency (plus Python):

```sh
python3 tools/build_linux_arm64.py --jobs 4
```

The helper builds `tools/linux_arm64_cross.Dockerfile`, runs regression tests
and configures/builds with `--linux-arm64 --pgo=off --lto=off`. Toolchains and
ARM64 graphics/audio development packages are installed **inside the container
only**. No host or handheld system packages are installed. Temporary files live
in `build/tmp`, not the host's `/tmp`.

A provisioned image can be reused:

```sh
python3 tools/build_linux_arm64.py --image halo-linux-arm64-cross:local --jobs 4
```

Direct invocation in the provisioned cross environment:

```sh
python3 configure.py --linux-arm64 --pgo=off --lto=off
ninja -j4 linux_arm64
```

Targets: `linux_arm64_guest`, `linux_arm64_host`, `linux_arm64`.
Tool overrides: `--linux-arm64-cc`, `--linux-arm64-guest-cc`,
`--linux-arm64-ld`, `--linux-arm64-ar`, `--linux-arm64-gl-include`.
Existing i686 Linux and Android targets are retained; normal configure does
not download Linux ARM64 dependencies unless `--linux-arm64` is explicit.

The SDL dependency is pinned to release-3.4.16 and musl to 1.2.5. The tested
container provides LLVM 18 and an AArch64 GNU toolchain. The default container
recipe supplies X11 and offscreen drivers; native Wayland availability depends
on the target development libraries used when SDL is built (XWayland is a
fallback). After switching build images, remove only the generated
`build/linux_arm64/sdl3-build/CMakeCache.txt` to avoid stale feature detection.
Do not mix root-generated Ninja logs with unprivileged builds.

Outputs:

```text
build/linux_arm64/halo-host
build/linux_arm64/halo_guest.elf
build/linux_arm64/sdl3-build/libSDL3.so.0
```

## Runtime requirements

- Linux AArch64 with **4096-byte pages**; 16KB/64KB kernels are rejected.
- The Xbox window at `0x80000000` and guest image at `0x88000000` must be free.
  Existing mappings are never forcibly overwritten.
- The supplied host/SDL require glibc 2.38 or newer, EGL and OpenGL ES 3.x.
  Do not replace the target's libc, EGL or graphics drivers with cross-host libs.
- The first port retains Android's gamepad-first/fullscreen guest path. Desktop
  keyboard/mouse completeness, windowing/F11, hardware audio and controller
  behavior need further real-device validation.

The game is built from the public source. Runtime packages contain **no disc
images, maps, caches or saves**. Import game data only from a copy you own;
follow the upstream extraction instructions, including any required resources
besides `maps/ui.map`.

## Run on ARM64

Keep the guest beside the host and `sdl3-build/libSDL3.so.0` beside that directory
(or put SDL in `lib/` when using the `Halo` launcher, which adds a local library
path). Copy `port/linux_arm64/Halo` into the runtime directory and make it
executable.

```sh
./Halo --preflight
HALO_DATA_ROOT=/path/to/extracted-halo HALO_SAVE_ROOT=/path/to/halo-saves ./Halo
```

You can also run `./halo-host --preflight`, `./halo-host --help` or
`./halo-host --guest /absolute/path/halo_guest.elf`.

Startup is intended to follow the x86 desktop port: `config.toml` beside the
executable selects `[paths] data` and `saves`; environment overrides remain
optional. Data discovery checks the current directory, executable directory,
and the upstream `assets/` locations. Without configured saves the desktop
location is `$XDG_DATA_HOME/halo-linux` (usually `~/.local/share/halo-linux`).
Existing save directories are not automatically moved from the older ARM64
`~/.local/state/halo` default; set `paths.saves` to retain them.

For an existing installation with `data/maps/` and `saves-bsp-fix/`, put this
in `config.toml` beside `Halo` and `halo-host` (use your own absolute paths):

```toml
[paths]
data = '/var/home/armada/Applications/halo-linux-arm64/data'
saves = '/var/home/armada/Applications/halo-linux-arm64/saves-bsp-fix'
```

Merge this section into an existing config rather than duplicating `[paths]`.
Then launch `./Halo` with no environment assignments. Alternatively, place
`maps/` directly beside the executable. Keep `config.toml` beside the executable
for desktop settings; old settings in `data/config.toml` may need to be copied
or merged there. Do not overwrite your current config without backing it up.

On a first start with no maps, the importer asks for an Xbox ISO/XISO and copies
`maps/` beside the executable with a progress display, using `maps.partial/`
until the complete copy can be renamed. The destination must be writable.
A desktop file picker requires a suitable graphical session/backend; headless
runs should use the explicit command-line importer instead. Neither normal
startup nor importing writes game files into the runtime ZIP.

Headless/terminal import is also available:

```sh
./Halo --import-iso '/path/to/Halo.iso' --print-paths
```

`--print-paths` alone prints the selected data, save and config paths without
launching the game. The command-line ISO option skips the file picker;
normal `./Halo` still offers the graphical prompt when no data is found.

## Game-data-free ABI/GLES/audio tests

In the cross environment, after a normal build:

```sh
bash tools/linux_arm64_smoke.sh --build-only
```

On an AArch64 machine/userspace with the same runtime libraries:

```sh
build/linux_arm64/smoke/host-abi-test build/linux_arm64/smoke/abi-guest.elf
SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1 \
  build/linux_arm64/smoke/host-sdl-test build/linux_arm64/smoke/sdl-guest.elf
```

Fixtures are original test code, not a substitute for Halo data or a claim of
playability. The audio test proves callback execution, not audible output.

## Experimental runtime package

After building, run `python3 tools/package_linux_arm64.py`. It creates
`build/linux_arm64/halo-linux-arm64-experimental-runtime.zip` with a fixed
allowlist of the host, guest, SDL, launcher, notices and a SHA-256 manifest.
No system libc/graphics libraries or game data are included. ZIP extractors
must preserve executable permissions; otherwise run `chmod +x Halo halo-host`.

Upstream build-268 is licensed under AGPL-3.0-or-later; the runtime includes
that license plus CC0 and third-party notices. The matching
`halo-linux-arm64-build268-source.tar.gz` source snapshot accompanies this
local build, including the ARM64 changes, build scripts and SDL/musl sources.
It contains no user's ISO, extracted maps, caches or saves. This is a modified
experimental ARM64 build, not an official upstream ARM64 release.

## Remaining acceptance gates

1. Load legitimate complete game data and reach menu and a playable level.
2. Launch on a real ARM64 device display and verify GPU-rendered frames.
3. Verify speaker output and physical controls/InputPlumber as applicable.
4. Check suspend/resume, saves and sustained gameplay; then network determinism.
5. Refine the desktop input/windowing path and portability beyond the initial
   glibc/4KB-page target before calling this a supported release.
