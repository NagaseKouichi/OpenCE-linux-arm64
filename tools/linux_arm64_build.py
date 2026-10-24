"""Native Linux ARM64 graph, sharing the Android ILP32 ABI, not its SDK.

C is compiled for arm64_32, converted to ELF AArch64 assembly and linked
below 4 GiB. The separate Linux LP64 host loads that image. No NDK or
Gradle is used; --linux-arm64 is required before downloading dependencies.
"""
import json
import subprocess
from pathlib import Path
from typing import Any, List

from .android_build import (GUEST_ABI_FLAGS, GUEST_CODE_FLAGS, MUSL_DIRECTORIES,
                            MUSL_FILES, MUSL_THREAD_PREFIXES, MUSL_EXCLUDE,
                            VARIADIC_PROTOTYPE_FILES, MUSL_VERSION, MUSL_URL,
                            SDL_TAG, SDL_URL, TOML_DIR, KCP_DIR)
from .linux_build import (LINUX_PROFILE, MINIUPNPC_DEFINES, MINIUPNPC_DIR,
                         MUSL_MATH_DIR, STB_VORBIS_SOURCE, XDK_INCLUDE, compile_launcher, configuration_defines,
                         game_defines_and_includes, game_sources, miniupnpc_sources,
                         musl_math_sources, pgo_mode, pgo_profile,
                         profile_use_flags, xdk_headers)
from .ninja_syntax import Writer
from .embed_assets import hud_assets_build, hud_configure_inputs
from .linux_build import EXPAT_DIR, EXPAT_SOURCES, MONOCYPHER_DIR, ZLIB_DIR, ZLIB_SOURCES, ZLIB_DEFINES
from .android_build import MBEDTLS_DIR
from .linux_build import opus_cflags, opus_sources, updater_defines

PORT_DIR = Path("port/android")  # existing ILP32 ABI/runtime shared with Linux
LINUX_DIR = Path("port/linux")
NATIVE_DIR = Path("port/linux_arm64")
BUILD = Path("build/linux_arm64")
THIRD_PARTY = BUILD / "third_party"
MUSL_DIR = THIRD_PARTY / f"musl-{MUSL_VERSION}"
SDL_DIR = THIRD_PARTY / "SDL3"


def fetch_third_party() -> None:
    """Fetch pinned source dependencies only for the explicitly enabled port."""
    THIRD_PARTY.mkdir(parents=True, exist_ok=True)
    if not MUSL_DIR.is_dir():
        archive = THIRD_PARTY / f"musl-{MUSL_VERSION}.tar.gz"
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(archive), MUSL_URL], check=True)
        subprocess.run(["tar", "xzf", str(archive), "-C", str(THIRD_PARTY)], check=True)
        archive.unlink()
    if not SDL_DIR.is_dir():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", SDL_TAG,
                        SDL_URL, str(SDL_DIR)], check=True)


def _musl_sources() -> List[Path]:
    src = MUSL_DIR / "src"
    result = set()
    for directory in MUSL_DIRECTORIES:
        result.update((src / directory).glob("*.c"))
    result.update(src / name for name in MUSL_FILES)
    result.update(p for p in (src / "thread").glob("*.c")
                  if p.name.startswith(MUSL_THREAD_PREFIXES))
    return [p for p in sorted(result)
            if not any(p.relative_to(src).as_posix() == e or
                       p.relative_to(src).as_posix().startswith(e + "/")
                       for e in MUSL_EXCLUDE)]


def linux_arm64_configure_inputs() -> List[Path]:
    return [Path(__file__), NATIVE_DIR, PORT_DIR / "guest" / "runtime",
            PORT_DIR / "host", LINUX_DIR / "src", *hud_configure_inputs()]


def generate_linux_arm64_build(n: Writer, sln: Any) -> None:
    if not getattr(sln, "linux_arm64", False):
        return
    fetch_third_party()  # failure is fatal, never silently emit a phony guest
    config = json.loads((LINUX_DIR / "port.json").read_text(encoding="utf-8"))
    sysroot_include = Path(getattr(sln, "linux_arm64_gl_include", None) or "/usr/include")
    for header in ("GLES3/gl32.h", "GLES2/gl2ext.h", "KHR/khrplatform.h"):
        if not (sysroot_include / header).is_file():
            raise FileNotFoundError(f"Linux ARM64 GLES headers missing: {sysroot_include / header}")
    host_cc = getattr(sln, "linux_arm64_cc", None) or "aarch64-linux-gnu-gcc"
    guest_cc = getattr(sln, "linux_arm64_guest_cc", None) or "clang"
    guest_dir = BUILD / "guest"
    obj_dir = guest_dir / "obj"
    gen_dir = guest_dir / "gen"
    libc_include = guest_dir / "libc_include"
    libc_internal = guest_dir / "libc_internal"
    gl_include = guest_dir / "gl_include"
    arch = PORT_DIR / "guest" / "libc" / "arch" / "arm64_32"
    semantics_header = Path("build/linux/halo_msvc_semantics.h")
    platform_semantics_header = Path("build/linux/platform_msvc_semantics.h")
    prefix_header = LINUX_DIR / "include" / "halo_linux_prefix.h"
    image = BUILD / "halo_guest.elf"
    sdl_build = BUILD / "sdl3-build"
    libsdl = sdl_build / "libSDL3.so"
    libmain = BUILD / "halo-host"
    python = "$python"

    n.comment("Linux ARM64: ILP32 guest and native LP64 host")
    n.variable("linux_arm64_guest_cc", guest_cc)
    n.variable("linux_arm64_host_cc", str(host_cc))
    n.variable("linux_arm64_cc", str(host_cc))
    n.variable("linux_arm64_ar", getattr(sln, "linux_arm64_ar", None) or "llvm-ar")
    n.variable("linux_arm64_ld", getattr(sln, "linux_arm64_ld", None) or "ld.lld")

    # ---------- generated headers and sources

    alltypes = libc_include / "bits" / "alltypes.h"
    syscall_h = libc_include / "bits" / "syscall.h"
    version_h = libc_internal / "version.h"
    n.rule(
        name="linux_arm64_alltypes",
        command=f"sed -f {MUSL_DIR}/tools/mkalltypes.sed $in > $out",
        description="LINUX ARM64 MUSL $out",
    )
    n.build(outputs=alltypes, rule="linux_arm64_alltypes",
            inputs=[arch / "bits" / "alltypes.h.in", MUSL_DIR / "include" / "alltypes.h.in"])
    n.rule(
        name="linux_arm64_syscall_h",
        command="cp $in $out && sed -n -e s/__NR_/SYS_/p < $in >> $out",
        description="LINUX ARM64 MUSL $out",
    )
    n.build(outputs=syscall_h, rule="linux_arm64_syscall_h", inputs=arch / "bits" / "syscall.h.in")
    n.rule(
        name="linux_arm64_version_h",
        command=f"echo '#define VERSION \"{MUSL_VERSION}\"' > $out",
        description="LINUX ARM64 MUSL $out",
    )
    n.build(outputs=version_h, rule="linux_arm64_version_h")

    # Linux OpenGL ES headers (C declarations only) for the ILP32 guest
    gl_stamp = gl_include / "stamp"
    n.rule(
        name="linux_arm64_gl_include",
        command=(f"mkdir -p {gl_include} && ln -sfn {sysroot_include}/GLES2 {gl_include}/GLES2 && "
                 f"ln -sfn {sysroot_include}/GLES3 {gl_include}/GLES3 && "
                 f"ln -sfn {sysroot_include}/KHR {gl_include}/KHR && touch $out"),
        description="LINUX ARM64 GL HEADERS",
    )
    n.build(outputs=gl_stamp, rule="linux_arm64_gl_include")

    guest_gl_c = gen_dir / "guest_gl.c"
    gl_imports = gen_dir / "gl_imports.list"
    n.rule(
        name="linux_arm64_gl_stubs",
        command=(f"{python} tools/android_gl_stubs.py {LINUX_DIR}/src/gl.h {sysroot_include}/GLES3/gl32.h "
                 f"{sysroot_include}/GLES2/gl2ext.h {guest_gl_c} {gl_imports}"),
        description="LINUX ARM64 GL STUBS",
    )
    n.build(outputs=[guest_gl_c, gl_imports], rule="linux_arm64_gl_stubs",
            implicit=[Path("tools/android_gl_stubs.py"), LINUX_DIR / "src" / "gl.h"])

    guest_posix_c = gen_dir / "guest_posix.c"
    posix_imports = gen_dir / "posix_imports.list"
    n.rule(
        name="linux_arm64_posix_stubs",
        command=f"{python} tools/android_posix_stubs.py {LINUX_DIR}/src/posix.h {guest_posix_c} {posix_imports}",
        description="LINUX ARM64 POSIX STUBS",
    )
    n.build(outputs=[guest_posix_c, posix_imports], rule="linux_arm64_posix_stubs",
            implicit=[Path("tools/android_posix_stubs.py"), LINUX_DIR / "src" / "posix.h"])

    imports_s = gen_dir / "imports.s"
    host_table_c = BUILD / "host" / "host_import_table.c"
    host_imports_list = PORT_DIR / "host_imports.list"
    n.rule(
        name="linux_arm64_imports",
        command=f"{python} tools/android_imports.py --host-table {host_table_c} {imports_s} $in",
        description="LINUX ARM64 IMPORTS",
    )
    n.build(outputs=[imports_s, host_table_c], rule="linux_arm64_imports",
            inputs=[host_imports_list, posix_imports, gl_imports],
            implicit=[Path("tools/android_imports.py")])

    generated_headers = [*xdk_headers(), alltypes, syscall_h, version_h, gl_stamp,
                         semantics_header, platform_semantics_header]

    # ---------- guest compilation: C -> Darwin assembly -> ELF assembly -> object

    n.rule(
        name="linux_arm64_guest_cc",
        command=(f"{compile_launcher(sln)}$linux_arm64_guest_cc -MMD -MF $out.d $cflags -S $in -o $out.darwin.s && "
                 f"{python} tools/android_asm_convert.py $out.darwin.s $out.s && "
                 f"$linux_arm64_guest_cc --target=aarch64-linux-gnu -c $out.s -o $out"),
        description="LINUX ARM64 CC $out",
        depfile="$out.d",
        deps="gcc",
    )
    n.rule(
        name="linux_arm64_guest_as",
        command="$linux_arm64_guest_cc --target=aarch64-linux-gnu -c $in -o $out",
        description="LINUX ARM64 AS $out",
    )

    libc_includes = [
        f"-isystem {libc_include}", f"-isystem {arch}", f"-isystem {MUSL_DIR}/arch/generic",
        f"-isystem {MUSL_DIR}/include",
    ]
    guest_abi = " ".join([*GUEST_ABI_FLAGS, "-DHALO_LINUX_ARM64=1", *configuration_defines(sln)])
    guest_code = " ".join(GUEST_CODE_FLAGS)
    tool_implicit = [Path("tools/android_asm_convert.py"), *generated_headers]
    # profile-guided optimisation with the Linux build's profile (committed,
    # or trained by the Linux build with --pgo=train): the game and platform
    # code are the same, and functions that differ simply go without
    profile = pgo_profile(sln, LINUX_PROFILE if pgo_mode(sln) == "train" else None, [LINUX_PROFILE], guest_cc)
    profile_flags = " ".join(profile_use_flags(profile))
    if profile:
        tool_implicit.append(profile)

    def guest_object(source: Path, cflags: str, prefix: str = "") -> Path:
        obj = obj_dir / prefix / Path(str(source).lstrip("/")).with_suffix(".o")
        if str(source).startswith(str(BUILD)):
            obj = obj_dir / prefix / source.relative_to(BUILD).with_suffix(".o")
        n.build(outputs=obj, rule="linux_arm64_guest_cc", inputs=source, implicit=tool_implicit,
                variables={"cflags": cflags})
        return obj

    # musl
    musl_cflags = " ".join([
        guest_abi, "-std=c99", "-ffreestanding", "-fno-common", "-D_XOPEN_SOURCE=700", "-w",
        f"-I{arch}", f"-I{MUSL_DIR}/arch/generic", f"-I{libc_internal}",
        f"-I{PORT_DIR}/guest/libc/src_include", f"-I{MUSL_DIR}/src/include",
        f"-I{MUSL_DIR}/src/internal", f"-I{libc_include}", f"-I{MUSL_DIR}/include",
    ])
    musl_objects = [guest_object(source, musl_cflags, "musl") for source in _musl_sources()]
    libguestc = guest_dir / "libguestc.a"
    n.rule(
        name="linux_arm64_ar",
        command="rm -f $out && $linux_arm64_ar rcs $out @$out.rsp",
        description="LINUX ARM64 AR $out",
        rspfile="$out.rsp",
        rspfile_content="$in_newline",
    )
    n.build(outputs=libguestc, rule="linux_arm64_ar", inputs=musl_objects)

    # the game
    objects: List[Path] = []
    game_flags = [
        "-std=gnu89", "-D__STRICT_ANSI__", "-w",
        "-Wno-error=incompatible-pointer-types",
        "-Wno-error=incompatible-function-pointer-types",
        "-Wno-error=int-conversion",
        "-Wno-error=implicit-function-declaration",
        "-Wno-error=implicit-int",
        "-Wno-error=return-type",
    ]
    game_cflags = " ".join([
        guest_abi, guest_code, " ".join(game_flags), profile_flags,
        f"-include {prefix_header}", f"-include {semantics_header}",
        f"-I{LINUX_DIR}/include", f"-iquote {Path(config['game_sources'])}",
        game_defines_and_includes(config), *libc_includes, f"-idirafter {XDK_INCLUDE}",
    ])
    for source in game_sources(config):
        cflags = game_cflags
        if source.as_posix() == "source/main/main.c":
            cflags += " " + updater_defines(getattr(sln, "port_release", False))
        if source.as_posix() in VARIADIC_PROTOTYPE_FILES:
            cflags += f" -include {PORT_DIR}/include/halo_android_variadic_prototypes.h"
        objects.append(guest_object(source, cflags))
    for source in sorted(Path(config["game_sources"]).glob("*.c")):
        objects.append(guest_object(source, game_cflags))
    objects.append(guest_object(STB_VORBIS_SOURCE, game_cflags))

    # the platform layer shared with Linux, and the guest runtime
    platform_cflags = " ".join([
        guest_abi, guest_code, "-std=gnu11", "-D_GNU_SOURCE", "-DHALO_LINUX_PLATFORM_LAYER", "-w", profile_flags,
        f"-include {prefix_header}", f"-include {platform_semantics_header}",
        f"-I{LINUX_DIR}/src", f"-I{LINUX_DIR}/include", f"-I{PORT_DIR}/guest/runtime",
        f"-I{PORT_DIR}/include", f"-I{TOML_DIR}", f"-I{KCP_DIR}",
        f"-I{EXPAT_DIR}", f"-I{MONOCYPHER_DIR}", f"-I{ZLIB_DIR}", "-Isource -Isource/cseries",
        f"-I{SDL_DIR}/include", f"-I{gl_include}", *libc_includes, f"-idirafter {XDK_INCLUDE}",
    ])
    guest_host_only = {"memory_watch.c"}  # replaced by guest_memory_watch.c
    for source in sorted((LINUX_DIR / "src").glob("*.c")):
        if source.name.startswith("posix_") or source.name in guest_host_only:
            continue
        objects.append(guest_object(source, platform_cflags))
    for source in hud_assets_build(n, "linux_arm64", gen_dir / "hud_hires_assets.c"):
        objects.append(guest_object(source, platform_cflags))
    for name in EXPAT_SOURCES:
        objects.append(guest_object(EXPAT_DIR / name, platform_cflags))
    for source in opus_sources():
        objects.append(guest_object(source, " ".join([opus_cflags(guest_abi), *libc_includes])))
    for name in ("monocypher.c", "monocypher-ed25519.c"):
        objects.append(guest_object(MONOCYPHER_DIR / name, platform_cflags))
    for name in ZLIB_SOURCES:
        objects.append(guest_object(ZLIB_DIR / name, " ".join([platform_cflags, *ZLIB_DEFINES, "-U__ARM_FEATURE_CRC32"])))
    # the settings file's parser (port/third_party/tomlc17)
    objects.append(guest_object(TOML_DIR / "tomlc17.c", platform_cflags))
    # internet play's reliable streams (port/third_party/kcp; p2p.c)
    objects.append(guest_object(KCP_DIR / "ikcp.c", platform_cflags))
    # the game's sin, pow and the rest, the same on every port
    # (port/include/halo_math.h)
    musl_math_cflags = " ".join([
        guest_abi, "-std=gnu11", "-w", profile_flags, *libc_includes, f"-I{MUSL_MATH_DIR}/include",
        f"-include {MUSL_MATH_DIR}/include/libm.h",
    ])
    for source in musl_math_sources():
        objects.append(guest_object(source, musl_math_cflags))
    runtime_internal_cflags = " ".join([
        guest_abi, "-std=c99", "-ffreestanding", "-fno-common", "-D_XOPEN_SOURCE=700", "-D_GNU_SOURCE",
        f"-I{PORT_DIR}/guest/runtime", f"-I{PORT_DIR}/include",
        f"-I{arch}", f"-I{MUSL_DIR}/arch/generic", f"-I{libc_internal}",
        f"-I{PORT_DIR}/guest/libc/src_include", f"-I{MUSL_DIR}/src/include",
        f"-I{MUSL_DIR}/src/internal", f"-I{libc_include}", f"-I{MUSL_DIR}/include",
    ])
    runtime_cflags = " ".join([
        guest_abi, guest_code, "-std=gnu11", "-D_GNU_SOURCE",
        f"-I{PORT_DIR}/guest/runtime", f"-I{PORT_DIR}/include", f"-I{LINUX_DIR}/src",
        f"-I{SDL_DIR}/include", f"-I{gl_include}", *libc_includes,
    ])
    runtime_dir = PORT_DIR / "guest" / "runtime"
    for source in sorted(runtime_dir.glob("*.c")):
        if source.name in ("guest_thread.c", "guest_start.c"):
            objects.append(guest_object(source, runtime_internal_cflags))
        elif source.name == "guest_memory_watch.c":
            objects.append(guest_object(source, platform_cflags))
        else:
            objects.append(guest_object(source, runtime_cflags))
    objects.append(guest_object(guest_gl_c, runtime_cflags))
    objects.append(guest_object(guest_posix_c, runtime_cflags))
    imports_o = obj_dir / "gen" / "imports.o"
    n.build(outputs=imports_o, rule="linux_arm64_guest_as", inputs=imports_s)
    objects.append(imports_o)

    # ---------- the guest image

    linker_script = PORT_DIR / "guest" / "guest.ld"
    n.rule(
        name="linux_arm64_guest_link",
        command=(f"$linux_arm64_ld -m aarch64linux -static -nostdlib -T {linker_script} "
                 f"-Map $out.map -o $out @$out.rsp {libguestc} "
                 "$$($linux_arm64_host_cc -print-libgcc-file-name)"),
        description="LINUX ARM64 LINK $out",
        rspfile="$out.rsp",
        rspfile_content="$in_newline",
    )
    n.build(outputs=image, rule="linux_arm64_guest_link", inputs=objects, implicit=[libguestc, linker_script])

    # ---------- native SDL3 and host (no Android services)
    n.rule(name="linux_arm64_sdl3", command=(
        f"PKG_CONFIG_LIBDIR=/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig "
        f"cmake -S {SDL_DIR} -B {sdl_build} -G Ninja "
        f"-DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=aarch64 "
        f"-DCMAKE_C_COMPILER=$linux_arm64_cc -DCMAKE_BUILD_TYPE=Release "
        f"-DCMAKE_LIBRARY_ARCHITECTURE=aarch64-linux-gnu "
        f"-DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST_LIBRARY=OFF "
        f"-DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF "
        f"> {BUILD}/sdl3-configure.log && ninja -C {sdl_build} > {BUILD}/sdl3-build.log"),
        description="LINUX ARM64 SDL3", pool="console")
    n.build(outputs=libsdl, rule="linux_arm64_sdl3", implicit=[SDL_DIR / "CMakeLists.txt"])
    n.rule(name="linux_arm64_host_cc",
           command="$linux_arm64_cc -MMD -MF $out.d $cflags -c $in -o $out",
           description="LINUX ARM64 HOST CC $out", depfile="$out.d", deps="gcc")
    host_cflags = " ".join([
        "-O2 -g -Wall -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -DHALO_LINUX_ARM64_HOST=1 -DHALO_HOST_POSIX_FILES=1",
        f"-I{PORT_DIR}/include -I{PORT_DIR}/host -I{SDL_DIR}/include -I{LINUX_DIR}/src",
        f"-I{TOML_DIR} -I{NATIVE_DIR}/host"])
    host_sources = [NATIVE_DIR / ("host/" + name + ".c") for name in
                    ("host_main", "host_startup", "host_import", "host_xiso")] + [
        PORT_DIR / "host" / (name + ".c") for name in (
            "host_memory", "host_loader", "host_thread", "host_debug",
            "host_sdl", "host_gl", "host_syscall", "host_watch_hash", "host_touch")] + [
        LINUX_DIR / "src/posix_files.c", LINUX_DIR / "src/posix_net.c", LINUX_DIR / "src/xiso.c",
        TOML_DIR / "tomlc17.c", host_table_c]
    host_objects = []
    host_obj_dir = BUILD / "host/obj"
    for source in host_sources:
        obj = host_obj_dir / (source.name + ".o")
        n.build(outputs=obj, rule="linux_arm64_host_cc", inputs=source,
                variables={"cflags": host_cflags})
        host_objects.append(obj)
    upnp_flags = " ".join([host_cflags, f"-I{MINIUPNPC_DIR}/include",
                            f"-I{MINIUPNPC_DIR}/src", *MINIUPNPC_DEFINES])
    for source in [LINUX_DIR / "src/posix_upnp.c", *miniupnpc_sources()]:
        obj = host_obj_dir / ("upnp_" + source.name + ".o")
        n.build(outputs=obj, rule="linux_arm64_host_cc", inputs=source,
                variables={"cflags": upnp_flags})
        host_objects.append(obj)
    mbedtls_flags = " ".join([host_cflags, f"-I{MBEDTLS_DIR}/include", f"-I{MBEDTLS_DIR}/library"])
    for source in [LINUX_DIR / "src/posix_dtls.c", *sorted((MBEDTLS_DIR / "library").glob("*.c"))]:
        obj = host_obj_dir / ("dtls_" + source.name + ".o")
        n.build(outputs=obj, rule="linux_arm64_host_cc", inputs=source,
                variables={"cflags": mbedtls_flags})
        host_objects.append(obj)
    n.rule(name="linux_arm64_host_link", command=(
        f"$linux_arm64_cc -o $out $in -L{sdl_build} "
        "-Wl,-rpath,'$$ORIGIN/sdl3-build' -lSDL3 -lGLESv2 -lEGL -lm -ldl -lpthread "
        "-Wl,--no-undefined"), description="LINUX ARM64 HOST LINK $out")
    n.build(outputs=libmain, rule="linux_arm64_host_link", inputs=host_objects, implicit=[libsdl])
    n.build(outputs="linux_arm64_guest", rule="phony", inputs=image)
    n.build(outputs="linux_arm64_host", rule="phony", inputs=libmain)
    n.build(outputs="linux_arm64", rule="phony", inputs=[image, libmain])
    n.newline()
