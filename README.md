# TL2-RE

**English** | [简体中文](README.zh-CN.md)

An offline, byte-exact reimplementation of Torchlight 2's proprietary `.MOD` / `BINDAT` / `BINLAYOUT` / `RAW` / `MPP`
formats — reverse-engineered out of `EditorGuts.dll` and the game loader, and rebuilt **offline, with no GUTS editor in the loop**.

At the core is `mikuro_mod_packer`: feed it the text sources (`.DAT` / `.LAYOUT`) and it serializes binary that's
**byte-for-byte aligned with the native DLL**, then assembles a `.MOD` the game can load and actually run. The handful of
easy-to-get-wrong details in between — the PAK rollingHash, the mandatory uppercase manifest filenames, BINDAT's per-file
string-hash — are all verified.

## What's inside

| Module | Role |
|---|---|
| `mikuro_mod_packer/packer.py` | `.MOD` container writer + full-pipeline orchestration (Compile ‖ RAW ‖ MPP ‖ Pack) |
| `mikuro_mod_packer/bindat.py` | `.DAT` → `.BINDAT` (per-file string→id hash table) |
| `mikuro_mod_packer/binlayout.py` | `.LAYOUT` → `.BINLAYOUT` (incl. Logic Group / datagroup) |
| `mikuro_mod_packer/raw.py` | `.RAW` indexes: UNITDATA / AFFIXES / SKILLS / MISSILES / UI, etc. |
| `mikuro_mod_packer/mpp/` | `.MPP` pathing grids (numba-accelerated offline approximation + byte-exact EditorGuts.dll backend) |
| `mikuro_mod_packer/rghash.py` | `rg_hash` (GUTS string hash) |

Reverse-engineering write-ups in [`docs/`](docs/):
- [`EditorGuts-RE-MOD-pack-and-read.md`](docs/EditorGuts-RE-MOD-pack-and-read.md) — the full RE record (write/read paths for MOD/BIN*/RAW/MPP + a function-address appendix)
- [`EditorGuts逆向-MOD打包与读取-完整记录.md`](docs/EditorGuts逆向-MOD打包与读取-完整记录.md) — the same record, in Chinese
- [`性能优化记录.md`](docs/性能优化记录.md) — the step-by-step optimization log that took the full-corpus pack from 185.5 → 82s (Chinese; every step byte-identical)

## Requirements

- Python **>= 3.12**, [uv](https://docs.astral.sh/uv/)
- numpy (required); numba + isal (optional accelerators — the code falls back to pure Python / zlib without them)
- **A real Torchlight 2 install** at `E:\Torchlight 2\MEDIA` — this path is a **hardcoded constant** in several places.
  Packing real content, the `RAW` builders, and the many "compare-against-the-real-install" tests all read it directly.
  Without that install (or at a different path), the relevant code/tests will fail or self-skip.

## Quickstart

```bash
uv sync                                   # create the env, install deps

# Pack a mod directory (containing a MEDIA/ subtree) into a loadable .MOD
# (converted in memory; the source MEDIA is not modified)
uv run python -m mikuro_mod_packer <mod_directory>
#   --in-place / --temp-copy   write strategy
#   --mpp {dll,re,none}        .MPP backend (dll = byte-exact via EditorGuts, default; re = offline approximation)
#   --raw {auto,none}          RAW index generation

# Generate a single .MPP offline
uv run python -m mikuro_mod_packer.mpp <LAYOUT> <OUT.mpp> [--snap 10]

# Tests (stdlib unittest, no pytest; real-install tests self-skip when TL2 is absent)
uv run python -m unittest discover -s tests -v
```

## Benchmark — vs the native GUTS editor (full 25-mod corpus)

**Packing the whole corpus from scratch: the native GUTS editor takes ~23 minutes; this packer takes ~82 seconds — 16.6× end-to-end.**

**Setup** — Native: a forked headless `tl2_console_fork` drives the real `EditorGuts.dll` (`InitEditor` paid once, **3.85s**,
amortized), timing each mod **warm**: `CreateMod` (compile + RAW + pack) + `EditorRegenPathingData` (byte-exact MPP);
`COMMANDMENTS` is the discarded cold-load warm-up, the other **24 all `ok`**. Ours: `tools/bench_all_mods.py`, **from scratch,
in memory, source mod untouched**, MPP on the offline numba backend. Same machine (16 cores), same TL2 install.

| Stage | Native (s) | Ours (s) | Speedup |
|---|--:|--:|--:|
| Build (compile + RAW + pack, **byte-exact-comparable**) | 1053.8 | 58.0 | **18.2×** |
| MPP (pathing grids) | 301.1 | 23.5 | **12.8×** |
| **Total** (+ native's one-time 3.85s init) | **1354.9** | **81.6** | **16.6×** |

<details><summary><b>Full per-mod table (24 mods, by native time desc; click to expand)</b></summary>

| Mod | Files | Native build | Native MPP | Native total | **Ours total** | Speedup |
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

*(COMMANDMENTS used as the warm-up, discarded.)*

</details>

- **The big mods are the divider**: `职业技能` (68k files) is **268s** native vs **12s** ours; `通用素材01` (277 MB) is
  **373s** native vs **15s** ours. The native editor compiles/packs file-by-file and collapses as the file count grows;
  ours parallelizes across processes/threads and scales near-linearly.
- **Build alone is already 18×**: the non-MPP compile + RAW + pack — the part that's **byte-for-byte alignable** with native —
  is 1053.8s native vs 58.0s ours, **with no approximation involved**.
- **Honest caveat**: native MPP is *byte-exact*; our path here is the numba offline **approximation** (~99.7% cell-accurate
  over the corpus). For byte-exact MPP, `--mpp dll` drives the same editor (MPP at native speed), and build is still **18×**.
- The step-by-step optimization (185.5 → 82s) is in [`docs/性能优化记录.md`](docs/性能优化记录.md).

> Reproduce: `uv run python tools/bench_all_mods.py` (ours, ~82s);
> `python tools/bench_native.py <mod>...` (native, ~23 min; needs the `TL2-Mikuro-Console.exe` built from
> `tl2_console_fork`, placed in the TL2 install dir).

## Tooling (`tools/`)

RE / verification / benchmark scripts: `mod_disasm.py` (`.MOD` disassembler), `cmp_mod.py` / `cmp_bindat.py`
(native-vs-ours diff), `verify_container_writer.py` (container-writer byte-exact), `bench_all_mods.py` / `bench_native.py`
(benchmarks), `build_*_*.py` (rebuild the `data/*.json`), `tl2_console_fork/` (C# headless driver fork, used for byte-exact `.MPP`).

> ⚠️ This is a **research** reimplementation of a commercial game's proprietary formats. For interoperability / modding only;
> it ships no game assets.
