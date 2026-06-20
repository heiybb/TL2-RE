# TL2-RE

[English](README.md) | **简体中文**

把 Torchlight 2 那几种私有二进制格式 —— `.MOD` / `BINDAT` / `BINLAYOUT` / `RAW` / `MPP`
—— 从 `EditorGuts.dll` 和游戏加载器里逆向出来,然后**离线、不开 GUTS 编辑器**地重新实现一遍。

核心是 `mikuro_mod_packer`:喂它文本源(`.DAT` / `.LAYOUT`),它直接序列化出跟原生 DLL **逐字节对得上**
的二进制,再拼成一个游戏能加载、能生效的 `.MOD`。中间几个容易出错的关键细节 —— PAK rollingHash、
清单文件名必须全大写、BINDAT 的 per-file string-hash —— 都已经验证过了。

## 包含什么

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
- [`EditorGuts-RE-MOD-pack-and-read.md`](docs/EditorGuts-RE-MOD-pack-and-read.md) — 同一份记录的英文版
- [`性能优化记录.md`](docs/性能优化记录.md) — 全量打包流水线 185.5→82s 的逐项优化(均字节一致)

## 环境要求

- Python **>= 3.12**、[uv](https://docs.astral.sh/uv/)
- numpy(必需);numba + isal(可选加速,缺失时自动回退到纯 Python / zlib)
- **一份真实的 Torchlight 2 安装**,在 `E:\Torchlight 2\MEDIA` —— 该路径在多处是**硬编码常量**。
  打包真实内容、跑 `RAW` 构建器、以及大量「真机比对」测试都直接读取该目录。
  没有这个安装、或路径不同,相关代码/测试会失败或自跳过。

## 快速上手

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

## 基准 —— 对比原生 GUTS 编辑器(全 25-mod 语料)

**全语料从零打包:原生 GUTS 编辑器 ~23 分钟,本 packer ~82 秒 —— 端到端 16.6×。**

**口径** —— 原生:forked headless `tl2_console_fork` 驱动真 `EditorGuts.dll`
(`InitEditor` 一次性 **3.85s**,已摊销),每 mod **warm** 计时 `CreateMod`(编译 +
RAW + 打包)+ `EditorRegenPathingData`(byte-exact MPP);`COMMANDMENTS` 作冷启动
warm-up 丢弃,其余 **24 个全部 `ok`**。我们:`tools/bench_all_mods.py`,**从零、
内存内、不改动源 mod**,MPP 走离线 numba 后端。同机(16 核)、同一 TL2 安装。

| 阶段 | 原生 (s) | 我们 (s) | 倍率 |
|---|--:|--:|--:|
| Build(编译 + RAW + 打包,**byte-exact 可比**) | 1053.8 | 58.0 | **18.2×** |
| MPP(寻路栅格) | 301.1 | 23.5 | **12.8×** |
| **合计**(另 +原生一次性 3.85s init) | **1354.9** | **81.6** | **16.6×** |

<details><summary><b>完整 24-mod 逐项(按原生耗时降序;点开)</b></summary>

| Mod | 文件 | 原生 build | 原生 MPP | 原生 total | **我们 total** | 倍率 |
|---|--:|--:|--:|--:|--:|--:|
| 挑战者大陆--通用素材01 | 12712 | 164.05 | 208.77 | 372.82 | **14.95** | 24.9× |
| 挑战者大陆--职业技能 | 68217 | 268.42 | 0.00 | 268.42 | **12.17** | 22.1× |
| 挑战者大陆--地图拓展 | 44060 | 234.02 | 8.96 | 242.98 | **13.99** | 17.4× |
| 挑战者大陆--群魔堕落 | 52438 | 169.36 | 0.51 | 169.87 | **9.27** | 18.3× |
| 挑战者大陆--暗黑传奇 | 32020 | 97.86 | 6.02 | 103.88 | **7.91** | 13.1× |
| 挑战者大陆--POE | 1978 | 24.65 | 28.07 | 52.72 | **5.10** | 10.3× |
| MIKURO_VANILLA_OVERHAUL | 1708 | 20.18 | 30.35 | 50.53 | **4.97** | 10.2× |
| 挑战者大陆--暗黑世界(临时) | 354 | 9.68 | 17.26 | 26.94 | **3.64** | 7.4× |
| 挑战者大陆--佣兵系统 | 2956 | 14.16 | 0.86 | 15.02 | **2.00** | 7.5× |
| 挑战者大陆--至尊适配 | 1818 | 11.14 | 0.00 | 11.14 | **0.91** | 12.2× |
| 挑战者大陆--实验内容 | 470 | 8.31 | 0.00 | 8.31 | **1.22** | 6.8× |
| AdventurerTime | 523 | 6.27 | 0.00 | 6.27 | **0.52** | 12.1× |
| VCO_paladin | 1554 | 4.80 | 0.00 | 4.80 | **0.81** | 5.9× |
| 挑战者大陆--护身符 | 1348 | 4.29 | 0.00 | 4.29 | **0.49** | 8.8× |
| MIKURO_CLASS_QLJX_EN | 955 | 3.32 | 0.00 | 3.32 | **0.73** | 4.5× |
| MIKURO_CLASS_QLJX | 955 | 3.25 | 0.00 | 3.25 | **0.77** | 4.2× |
| Loading_Screens_Maps+Creat | 32 | 2.79 | 0.00 | 2.79 | **0.18** | 15.5× |
| 挑战者大陆--宠物系统 | 431 | 1.96 | 0.17 | 2.13 | **0.45** | 4.7× |
| arkhamsarmory | 276 | 1.46 | 0.00 | 1.46 | **0.22** | 6.6× |
| SYN_THROWING_WEAPONS | 367 | 1.34 | 0.00 | 1.34 | **0.18** | 7.4× |
| MIKURO_FUN | 238 | 1.05 | 0.15 | 1.20 | **0.94** | 1.3× |
| final_fantasy_weapons | 63 | 0.78 | 0.00 | 0.78 | **0.07** | 11.1× |
| LurkerHUD_(Non-Conflict) | 24 | 0.46 | 0.00 | 0.46 | **0.05** | 9.2× |
| EFFECTS_LIST_OVERHAUL | 3 | 0.21 | 0.00 | 0.21 | **0.02** | 10.5× |

*(COMMANDMENTS 作 warm-up 已丢弃。)*

</details>

- **大 mod 是分水岭**:`职业技能`(68k 文件)原生 **268s** vs 我们 **12s**;
  `通用素材01`(277 MB)原生 **373s** vs 我们 **15s**。原生编辑器逐文件串行
  compile/pack,文件越多越塌;我们多进程 / 多线程并行,几乎线性。
- **Build-only 已 18×**:不含 MPP 的编译 + RAW + 打包(可与原生**逐字节对齐**的
  部分)原生 1053.8s vs 我们 58.0s —— 这块**没有任何近似**。
- **口径诚实**:原生 MPP 是 *byte-exact*,我们这条是 numba 离线**近似**(整语料
  ~99.7% cell 命中)。要 byte-exact 就用 `--mpp dll` 驱动同一编辑器(MPP 段与原生
  同速),build 仍 **18×**。
- 逐项优化(185.5 → 82s)见 [`docs/性能优化记录.md`](docs/性能优化记录.md)。

> 复现:`uv run python tools/bench_all_mods.py`(我们,~82s);
> `python tools/bench_native.py <mod>...`(原生,~23 min,需 `tl2_console_fork`
> 编出的 `TL2-Mikuro-Console.exe` 放进 TL2 安装目录)。

## 工具(`tools/`)

逆向/校验/基准脚本:`mod_disasm.py`(`.MOD` 反汇编)、`cmp_mod.py` / `cmp_bindat.py`
(native-vs-ours 对比)、`verify_container_writer.py`(容器写入字节精确)、
`bench_all_mods.py` / `bench_native.py`(基准)、`build_*_*.py`(重建 `data/*.json`)、
`tl2_console_fork/`(C# 无头驱动 fork,字节精确 `.MPP` 用)。

> ⚠️ 这是对一款商业游戏私有格式的**研究性**复现。仅用于互操作 / 模组制作,不分发任何游戏资产。
