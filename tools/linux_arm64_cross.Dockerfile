# Isolated x86_64 -> AArch64 compiler and target graphics/audio development libs.
# Dependencies are container-only; this recipe never installs host packages.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN dpkg --add-architecture arm64 && \
    printf 'Types: deb\nArchitectures: amd64\nURIs: http://archive.ubuntu.com/ubuntu/\nSuites: noble noble-updates noble-security\nComponents: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\nTypes: deb\nArchitectures: arm64\nURIs: http://ports.ubuntu.com/ubuntu-ports/\nSuites: noble noble-updates noble-security\nComponents: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' > /etc/apt/sources.list.d/ubuntu.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git cmake ninja-build \
        clang lld llvm gcc file python3 python3-pytest pkg-config libc6-dev-i386 \
        libgles-dev libegl-dev && \
    apt-get install -y --no-install-recommends gcc-aarch64-linux-gnu libc6-dev-arm64-cross \
        libx11-dev:arm64 libxext-dev:arm64 libxrandr-dev:arm64 libxcursor-dev:arm64 \
        libxi-dev:arm64 libxfixes-dev:arm64 libxss-dev:arm64 libxtst-dev:arm64 libegl-dev:arm64 \
        libgles-dev:arm64 libasound2-dev:arm64 && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /repo
