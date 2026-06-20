# TL2-RE

Torchlight 2 二进制格式的**离线逆向与复现**工具集 — an offline, byte-exact
reimplementation of Torchlight 2's proprietary `.MOD` / `BINDAT` / `BINLAYOUT` /
`RAW` / `MPP` formats, recovered by reverse-engineering `EditorGuts.dll` and the
game loader, without the GUTS editor in the loop.

`mikuro_mod_packer` 直接从文本源(`.DAT` / `.LAYOUT`)序列化出与原生 DLL **逐字节一致**
的二进制,再组装成游戏可加载的 `.MOD` 容器(含 PAK rollingHash、大写文件名清单、
per-file string-hash 等已验证的关键细节)。

## What's inside

| 模块 | 作用 |
|---|---|
| `mikuro_mod_packer/packer.py` | `.MOD` 容器写入 + 全流程编排(Compile ‖ RAW ‖ MPP ‖ Pack) |
| `mikuro_mod_packer/bindat.py` | `.DAT` → `.BINDAT`(per-file string→id hash 表) |
| `mikuro_mod_packer/binlayout.py` | `.LAYOUT` → `.BINLAYOUT`(含 Logic Group / datagroup) |
| `mikuro_mod_packer/raw.py` | UNITDATA / AFFIXES / SKILLS / MISSILES / UI 等 `.RAW` 索引 |
| `mikuro_mod_packer/mpp/` | `.MPP` 寻路网格(numba 加速的离线近似 + EditorGuts.dll 字节精确双通道) |
| `mikuro_mod_packer/rghash.py` | `rg_hash`(GUTS 字符串哈希) |

逆向记录见 [`docs/`](docs/):
- [`EditorGuts逆向-MOD打包与读取-完整记录.md`](docs/EditorGuts逆向-MOD打包与读取-完整记录.md) — 完整中文逆向记录(MOD/BIN*/RAW/MPP 的写入与读取路径 + 函数地址附录)
- [`EditorGuts-RE-MOD-pack-and-read.md`](docs/EditorGuts-RE-MOD-pack-and-read.md) — English translation
- [`性能优化记录.md`](docs/性能优化记录.md) — 全量打包流水线 185.5→83s 的逐项优化(均字节一致)

## Requirements

- Python **>= 3.12**, [uv](https://docs.astral.sh/uv/)
- numpy(必需);numba + isal(可选加速,缺失时自动回退到纯 Python / zlib)
- **A real Torchlight 2 install** at `E:\Torchlight 2\MEDIA` — 该路径在多处是**硬编码常量**。
  打包真实内容、跑 `RAW` 构建器、以及大量「真机比对」测试都直接读取该目录。
  没有这个安装、或路径不同,相关代码/测试会失败或自跳过。

## Quickstart

```bash
uv sync                                   # 创建环境、装依赖

# 把一个 mod 目录(含 MEDIA/ 子树)打包成可加载的 .MOD(内存转换,不改动源 MEDIA)
uv run python -m mikuro_mod_packer <mod_directory>
#   --in-place / --temp-copy   写入策略
#   --mpp {dll,re,none}        .MPP 后端(dll=EditorGuts 字节精确,默认;re=离线近似)
#   --raw {auto,none}          RAW 索引生成

# 单独离线生成一个 .MPP
uv run python -m mikuro_mod_packer.mpp <LAYOUT> <OUT.mpp> [--snap 10]

# 测试(stdlib unittest,无 pytest;真机测试在缺少 TL2 安装时自跳过)
uv run python -m unittest discover -s tests -v
```

## Benchmark — vs the native GUTS editor

**口径** — 原生:forked headless `tl2_console_fork` 驱动真 `EditorGuts.dll`,
`InitEditor` 一次性 **5.14s**(下表已摊销),之后每 mod **warm** 计时(`CreateMod`
= 编译 + RAW + 打包,`EditorRegenPathingData` = byte-exact MPP)。我们:本仓
`tools/bench_all_mods.py`,**从零、内存内、不改动源 mod**,MPP 走离线 numba 后端。
同机(16 核)、同一批 mod、同一 TL2 安装。

| Mod | 原生 total (s) | **我们 total (s)** | 倍率 |
|---|--:|--:|--:|
| final_fantasy_weapons | 0.77 | **0.07** | 11.0× |
| arkhamsarmory | 1.46 | **0.22** | 6.6× |
| AdventurerTime (33.8 MB) | 6.31 | **0.52** | 12.1× |
| SYN_THROWING_WEAPONS | 1.41 | **0.18** | 7.8× |
| MIKURO_FUN | 1.15 | **0.94** | 1.2× |
| 挑战者大陆--佣兵系统 | 13.91 | **2.00** | 7.0× |
| MIKURO_VANILLA_OVERHAUL | 51.11 | **4.97** | 10.3× |
| 挑战者大陆--POE | 53.80 | **5.10** | 10.5× |
| **8-mod 合计** | **129.9** (另 +5.14 一次性 init) | **14.0** | **≈ 9.3×** |

- **MPP-heavy mod 差距最大**:VANILLA / POE 原生 51–54s,其中 byte-exact 寻路
  regen 就占 **29–31s**;我们 numba 离线 MPP ~3.5s。光看 MPP ≈ **8–9× 快**。
- **唯一接近的是 MIKURO_FUN**(关卡极少):离线 MPP 有 ~1s 的 numba 首次 JIT
  固定开销(类比原生那 5.14s init,只是小得多),单 tile 摊不开。
- **口径诚实**:原生 MPP 是 *byte-exact*,我们这条用的是 numba 离线**近似**
  (整语料 ~99.7% cell 命中)。若要 byte-exact MPP,用 `--mpp dll` 驱动同一个
  编辑器(MPP 段与原生同速),但编译 / RAW / 打包仍快 **3–90×**。
- 完整 **25-mod 语料**从零打包合计约 **82s**(Compile 24 / RAW 19 / MPP 24 /
  Pack 15;702 MB 输出)。逐项优化(185.5 → 83s)见
  [`docs/性能优化记录.md`](docs/性能优化记录.md)。

> 复现:`uv run python tools/bench_all_mods.py`(我们);
> `python tools/bench_native.py --default`(原生,需 `tl2_console_fork` 编译出的
> `TL2-Mikuro-Console.exe` 放进 TL2 安装目录)。

## Tooling (`tools/`)

逆向/校验/基准脚本:`mod_disasm.py`(`.MOD` 反汇编)、`cmp_mod.py` / `cmp_bindat.py`
(native-vs-ours 对比)、`verify_container_writer.py`(容器写入字节精确)、
`bench_all_mods.py` / `bench_native.py`(基准)、`build_*_*.py`(重建 `data/*.json`)、
`tl2_console_fork/`(C# 无头驱动 fork,字节精确 `.MPP` 用)。

> ⚠️ 这是对一款商业游戏私有格式的**研究性**复现。仅用于互操作 / 模组制作,不分发任何游戏资产。
