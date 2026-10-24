# OpenCE — 实验性 Linux ARM64 移植

[English](README.md) · [上游原始说明](docs/README.upstream.md)

基于上游 **build-268**（`5e27f3a2`），采用 AArch64 ILP32 游戏 guest + Linux AArch64 LP64 host，保留游戏的 32 位指针 ABI，通过 SDL3、EGL/GLES 运行。这不是模拟器，也不是上游官方 ARM64 发行版。

## 下载与启动

从 [Releases](https://github.com/NagaseKouichi/OpenCE-linux-arm64/releases) 下载运行包，解压到可写目录：

```sh
chmod +x Halo halo-host
./Halo --preflight
./Halo
```

运行条件：Linux AArch64、**4KB 内存页**、glibc **≥ 2.38**、EGL/OpenGL ES 3.x，以及可用的 SDL 桌面后端。当前构建支持 X11/XWayland。不要替换系统 libc 或显卡驱动。

游戏不含地图，请提供自己拥有的初代 Xbox《Halo: Combat Evolved》镜像或提取数据。首次无地图时，提示选择 ISO/XISO 并显示提取进度；文件选择器取决于桌面 portal/zenity 环境。命令行后备方式：

```sh
./Halo --import-iso '/镜像路径/Halo.iso' --print-paths
```

也可以直接将 `maps/` 放在程序旁边。保留独立的数据及存档目录时，在**程序旁边**的 `config.toml` 中设置：

```toml
[paths]
data = '/绝对路径/data' # 里面包含 maps/
saves = '/绝对路径/saves'
```

已有 `[paths]` 时修改原区段，不要重复添加。然后直接 `./Halo` 即可。默认存档位于 `$XDG_DATA_HOME/halo-linux` 或 `~/.local/share/halo-linux`；仍支持 `HALO_DATA_ROOT` / `HALO_SAVE_ROOT` 环境变量覆盖。旧 ARM64 版本使用过其他默认目录，不会自动迁移，请先备份存档并显式指定旧目录。升级必须同时替换 host 和 guest。

## 验证范围

此前 BSP 修复包已经用户确认：Adreno 830 ARM64 掌机可以显示主菜单、播放菜单音乐。**本次 build-268 仍需实机复测**；战役、实体手柄、检查点、联网及长期稳定性尚未完整验收。QEMU 离屏／假音频验证不等于实机可玩。片头 Bink 视频当前跳过。

- ARM64／启动／打包／Linux 回归：50 通过、4 跳过。
- 上游专项测试：82 通过、3 跳过。
- 引擎测试：842 通过、1 项电梯预测精确浮点断言失败；纯上游同版源码也能复现。

详见 [ARM64 技术说明](port/linux_arm64/README.md) 和 [验证记录](port/linux_arm64/VALIDATION.md)。

## 在 x86_64 Linux 上交叉编译

需要 Python 3 和 Docker，不向掌机安装开发环境：

```sh
python3 tools/build_linux_arm64.py --jobs 4
python3 tools/package_linux_arm64.py
```

参数为 `--linux-arm64 --pgo=off --lto=off`。

## 许可

上游为 **AGPL-3.0-or-later**，参见 [LICENSE](LICENSE)、[CC0](LICENSES/CC0-1.0.txt) 及第三方许可。发行时同时提供匹配源码；不发布 ISO、地图、缓存或存档。上游 README 保存在 `docs/README.upstream.md`。
