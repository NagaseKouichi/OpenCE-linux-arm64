# Linux ARM64 validation record

The initial milestone below is historical and applies to `c5fcfbd4` only.
Later upstream-sync checks are recorded separately; original fixture execution
never implies that the game was playable on a physical ARM64 device.

## Initial milestone

Upstream source baseline: `c5fcfbd4` (uncommitted Linux ARM64 changes applied).
Compiler actually exercised: Ubuntu Clang 18.1.3 plus AArch64 GNU tools.
Source/build documentation: [README.md](README.md).

## Executed checks

- Built the standalone `tools/linux_arm64_cross.Dockerfile` image; corrected
  its missing ARM64 XTest development dependency exposed by a cleaned build.
- Cleaned 1,478 Ninja outputs and rebuilt the actual guest/host in an isolated
  x86 cross environment with the repository owner's UID/GID. The SDL CMake
  cache from the older cross image was reset for accurate dependency detection.
- `halo_guest.elf`: ELF64 AArch64 ET_EXEC, static, entry `0x88000000`.
- `halo-host`: ELF64 AArch64 PIE, `/lib/ld-linux-aarch64.so.1` interpreter.
- 24 build/host/launcher/package/Linux regression tests passed together in
  the isolated image as the repository owner. Native host tests use explicit
  synthetic fixtures/shims and are not game-playability tests.
- AArch64 runtime container reports `uname -m=aarch64`, page size 4096.
  Execution is QEMU-backed on the x86 host, not a physical ARM64 device.
- Production `halo-host --preflight` passed low-address reservations.
- Original ILP32 ABI fixture passed low stack, boot argv, 4 resolved imports,
  host calls and thread-local-pointer checks.
- Original SDL fixture passed 14 resolved imports, low-stack SDL main-thread
  initialization, offscreen OpenGL ES 3.2 Mesa context creation and a guest
  audio callback using the dummy audio driver.
- Production loader loaded the full game guest and resolved 192 imports with
  zero unavailable. It then intentionally exited 1 with the diagnostic that
  `maps/ui.map` was missing. No invented data was supplied to claim success.
- Allowlisted runtime ZIP integrity, AArch64 architecture, executable modes
  and asset exclusion were tested. Extracted `Halo --preflight` passed.
- `git diff --check` passed.

Representative actual runtime output:

```text
ILP32 guest smoke passed: low stack, boot argv, host imports and TLS
OpenGL ES 3.2 Mesa 25.2.8-0ubuntu0.24.04.3
SDL guest audio callback passed: low stack and audio stream handle
```

Actual full-image startup:

```text
halo [info]: Halo Linux ARM64 host starting
halo [info]: guest image 88000000-88ddf000, 192 imports (0 unavailable)
halo [fatal]: Halo game data not found in /root/.local/share/halo/maps/ui.map; set HALO_DATA_ROOT to your extracted game data
```

## Upstream synchronization to build-201

The source tree was fast-forwarded to upstream `main`, commit
`b1ef7f7e7aff00f0efdca4d575f7d9196d0b1590` (build-201). Local Linux ARM64
changes were restored with deliberate conflict resolution in `configure.py`
and `host_memory.c`; the stash and a source-only backup under
`build/upstream-sync-backup/` were retained. No ISO was included in the backup.

The upstream ABI is now version 2 (including thread detach). Original smoke
fixtures now include the production ABI header rather than a hardcoded copy,
and link the new `host_watch_hash.c`. The updated ABI and SDL fixtures passed
again in the QEMU-backed ARM64 container, including GLES 3.2 and a dummy-audio
guest callback. Upstream host-watch/BMP/cache-format tests: 170 passed,
4 skipped. Additional profile/web tests: 34 passed, 3 skipped, 2 blocked by
missing x86 Clang sanitizer runtime libraries. The upstream x86 engine harness
could not link because this ARM64 cross image lacks x86 multilib libgcc;
these failures are not reported as passing ARM64 gameplay tests. A separate
throwaway cross-container was subsequently provisioned with x86 multilib and
Clang sanitizer libraries: engine harness plus profile tests reached 306
passed, 3 skipped, and 2 failures. The remaining failures were the upstream
`elevator_prediction/riding-up` exact-float assertion and ThreadSanitizer
being denied the `personality(ADDR_NO_RANDOMIZE)` operation by Docker.
No game/core code was changed to hide either test failure.

The complete updated ILP32 guest and LP64 host were cross-compiled with
`python3 tools/build_linux_arm64.py --image halo-linux-arm64-cross:local --jobs 4`.
Parent verification confirmed AArch64 ELF artifacts, guest ABI version 2,
30 passed / 5 skipped in the ARM64 build/host/launcher/package and Linux tooling
suite, and no remaining Git conflicts or whitespace errors. The production
host passed `--preflight` in the ARM64 runtime container and loaded the full
`0x88000000..0x8a70d000` guest with 223 imports and zero unavailable imports;
it then exited 1 because no extracted data directory was configured. The ISO
present in the source directory was left untouched (no implicit import).
The experimental runtime ZIP was regenerated from an explicit allowlist,
with new dependency/font notices and ABI validation before packaging.


## Retail UI BSP memory-layout fix

The user's Asia Xbox `maps/ui.map` matched the extracted original byte-for-byte.
The unchanged build reproduced the device failure under QEMU: a 0x800-byte BSP
at file offset 0x800 targeted 0x81A22800, outside the beta-sized tag cache.
The same address is present in the original decompressed map reference.
The 22 MB tag cache ended at 0x819A6000; the native game state started at
0x81A00000, overlapping this retail BSP. Enlarging only the check is unsafe.

The cache is now 23 MB, ending at 0x81AA6000, and game state starts at
0x81B00000. Cache clearing/protection uses TAG_CACHE_SIZE consistently;
existing file/tag/BSP safety validation remains enabled. The numeric layout
regression failed before the change and passed afterwards. Cross-build and
regression results: 31 passed, 5 skipped. With the same original maps the
rebuilt guest reached saved-game enumeration and `starting main menu music`
without another BSP error. Execution used offscreen llvmpipe/dummy audio in
QEMU, not physical-device display/audio/input validation. The timed runtime
was closed by timeout and ultimately logged game exit 0; timeout itself is
not a gameplay pass. Bink intro movies are still skipped.

Game-state base addresses changed: earlier experimental campaign checkpoints
may not be compatible. Back up saves and use a separate HALO_SAVE_ROOT for
initial testing; no user game data or save was modified by this fix.

## Desktop startup parity

Linux ARM64 now reads `config.toml` beside the executable, matching the x86
port's actual `config_path` (not an unrelated cwd config). HALO_DATA_ROOT and
HALO_SAVE_ROOT remain optional overrides; `[paths] data` / `saves` are read
with the upstream TOML parser. The selected config path reaches the ILP32
guest so its display/debug settings are not lost when data is elsewhere.
Search order is configured data, cwd maps, executable maps, cwd assets and
repository assets. Default saves use XDG_DATA_HOME/halo-linux or
HOME/.local/share/halo-linux. No existing data/save directory is moved.

First-start UI uses SDL's Yes/No dialog, ISO/XISO file picker, and background
extraction with progress. The production upstream XDVDFS extractor is reused
via LP64 POSIX adapters; it publishes maps only after maps.partial is complete.
Explicit --import-iso bypasses graphical initialization entirely and can be
combined with --print-paths for import only. Preflight still needs no data.

Independent checks executed the actual AArch64 host under a user-local QEMU
sysroot. An actual import of the user's ISO produced 25 files, all matching the
prior independent extraction's file sizes and SHA-256 sums. Startup from an
unrelated cwd found executable-local maps, and config/env path selection was
verified. SDL's real X11 message-box cancel branch was exercised in Xvfb and
returned 0 without importing. File-picker usability in the target handheld's
desktop session still requires device verification (portal/zenity availability
is environment dependent). Asset-free tests also cover truncated images,
whole-disc offsets, traversal names, picker cancellation and config forwarding.
The final startup/ARM64/Linux/retail-layout regression suite reported
44 passed and 5 skipped; no game-derived data is shipped in the ZIP.
A full original-game run without HALO_DATA_ROOT/HALO_SAVE_ROOT read the
executable-local config, loaded the UI map, enumerated saves and reached
`starting main menu music`; this was offscreen/dummy-audio QEMU execution,
not another physical-handheld validation. This bounded run was terminated by
its timeout (exit 137 after forced termination), so it proves path/config and
menu initialization only, not a successful sustained session or clean exit.

## Build-268 upstream synchronization

Updated the upstream baseline from build-201 to build-268,
`5e27f3a27b2d3c27d3edeb450fe40c24defb9c15`, retaining the local ARM64
LP64 host / ILP32 guest architecture, retail BSP layout fix and desktop-style
startup. A tracked binary patch, untracked source backup (excluding the ISO)
and a retained Git stash preserve the pre-update state. The xiso conflict was
resolved against the rewritten upstream importer, retaining only the LP64
platform include adaptation.

Independent regression: 50 passed, 4 skipped for ARM64 build/host/launcher/
startup/package, Linux tooling and retail cache layout. New upstream
assembly/CE texture cache/mirror upload/text filter/network comparison/checkpoint
tests: 82 passed, 3 skipped after provisioning test-only multilib/Pillow in a
throwaway Docker container. Engine harness: 842 passed, 1 failed. The lone
`elevator_prediction[riding-up]` exact-float assertion was reproduced separately
on a pristine git archive of the same upstream commit; no local ARM64 changes
were present in that baseline reproduction.

The parent independently ran the rebuilt AArch64 host under local qemu-user
with the same original Asian Xbox maps and an isolated save directory.
Preflight and desktop config/path lookup passed. The guest reached structure
culling, save enumeration and `starting main menu music`, with no BSP bounds
failure. The bounded QEMU run timed out after 100 seconds; it is not a clean-exit,
sustained gameplay, physical graphics/audio/controller or network acceptance.
Existing game-data and device-save directories were not migrated or overwritten.

Upstream now uses AGPL-3.0-or-later; runtime notices include AGPL, CC0 and the
moved stb_vorbis license. A matching working-tree source archive (including
local ARM64 changes/build scripts and downloaded SDL/musl sources) accompanies
the allowlisted runtime archive. Neither contains disc images, extracted
maps, game caches or saves. This build still requires device retesting.

## Unverified acceptance gates

The user confirmed normal main-menu display and music on the ARM64 handheld
with the BSP-fix package. This startup update still needs device revalidation
for dialogs and physical controls. Campaign/level gameplay, audible gameplay
sound, sustained performance, suspend/resume, saves/checkpoints and network
play remain acceptance gates. Menu success alone is not full gameplay validation.
