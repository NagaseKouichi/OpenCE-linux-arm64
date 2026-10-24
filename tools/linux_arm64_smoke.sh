#!/usr/bin/env bash
# Build original, game-data-free ABI/SDL fixtures against production host code.
set -euo pipefail
cd "$(dirname "$0")/.."
B=build/linux_arm64
S="$B/smoke"
mkdir -p "$S"
export TMPDIR="$PWD/$S"
CLANG=${CLANG:-clang}
CROSS_CC=${CROSS_CC:-aarch64-linux-gnu-gcc}
CROSS_LD=${CROSS_LD:-aarch64-linux-gnu-ld}
GUEST_FLAGS=(--target=arm64_32-apple-watchos -mcpu=cortex-a53 -ffreestanding -fno-stack-protector -O2)
HOST_FLAGS=(-O2 -D_GNU_SOURCE -DHALO_LINUX_ARM64_HOST -Iport/android/host -Iport/android/include)
HOST_CORE=(port/android/host/host_memory.c port/android/host/host_loader.c port/android/host/host_thread.c port/android/host/host_watch_hash.c)
for mode in abi sdl; do
    extra_guest=()
    extra_host=()
    if [[ "$mode" == sdl ]]; then
        extra_guest=(-DSMOKE_SDL -U__APPLE__ -U__MACH__ -fno-define-target-os-macros -D__linux__ -nostdinc
            -isystem "$B/guest/libc_include" -isystem port/android/guest/libc/arch/arm64_32
            -isystem "$B/third_party/musl-1.2.5/arch/generic" -isystem "$B/third_party/musl-1.2.5/include"
            -I"$B/third_party/SDL3/include" -Iport/android/guest/runtime)
        extra_host=(-DSMOKE_SDL -I"$B/third_party/SDL3/include" port/android/host/host_sdl.c
            port/android/host/host_gl.c "$S/$mode-host-imports.c" -L"$B/sdl3-build"
            '-Wl,-rpath,$ORIGIN/../sdl3-build' -lSDL3 -lEGL -lGLESv2)
        python3 tools/android_imports.py --host-table "$S/$mode-host-imports.c" "$S/$mode-imports.s" \
            tools/fixtures/linux_arm64_sdl_smoke_imports.list
    else
        printf '%s\n' host_log host_exit host_get_tp host_set_tp > "$S/$mode-imports.list"
        python3 tools/android_imports.py "$S/$mode-imports.s" "$S/$mode-imports.list"
    fi
    "$CLANG" "${GUEST_FLAGS[@]}" "${extra_guest[@]}" -S tools/fixtures/linux_arm64_guest_smoke.c -o "$S/$mode-guest.darwin.s"
    python3 tools/android_asm_convert.py "$S/$mode-guest.darwin.s" "$S/$mode-guest.s"
    "$CLANG" --target=aarch64-linux-gnu -c "$S/$mode-guest.s" -o "$S/$mode-guest.o"
    "$CLANG" --target=aarch64-linux-gnu -c "$S/$mode-imports.s" -o "$S/$mode-imports.o"
    "$CROSS_LD" -static -T port/android/guest/guest.ld -o "$S/$mode-guest.elf" "$S/$mode-guest.o" "$S/$mode-imports.o"
    "$CROSS_CC" "${HOST_FLAGS[@]}" tools/fixtures/linux_arm64_host_smoke.c "${HOST_CORE[@]}" \
        "${extra_host[@]}" -pthread -o "$S/host-$mode-test"
done
if [[ "${1:-}" == --build-only ]]; then exit 0; fi
if [[ $(uname -m) != aarch64 ]]; then
    printf '%s\n' 'Fixtures built. Run host-abi-test/host-sdl-test in an AArch64 environment, or use --build-only.' >&2
    exit 2
fi
"$S/host-abi-test" "$S/abi-guest.elf"
SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1 \
    "$S/host-sdl-test" "$S/sdl-guest.elf"
