# TL2 EditorGuts.dll Reverse-Engineering Record — MOD packing / reading data structures

> Goal: **offline, editor-free** generation — from `.DAT/.LAYOUT` sources — of `.MOD` files that are
> **functionally equivalent to the native DLL pack and take effect in-game**.
> This is the design basis of the `mikuro_mod_packer/` package, covering the five formats
> **MOD container / BINDAT / BINLAYOUT / RAW / MPP**, and **how the native DLL writes and reads/validates** each.
>
> **Method**: IDA (idalib MCP) disassembly of `E:\Torchlight 2\EditorGuts.dll` (32-bit, imagebase `0x10000000`)
> + `Torchlight2.exe` (read side) + on-disk validation via `Ogre.log`/`modlauncher.sch` + byte-level diff of our
> output against shipped data / native packs. All `sub_XXXXXXXX` are absolute addresses.
> Living companions: the memory files (see end), `AGENTS.md`, and in-code comments (with addresses / byte layouts).
>
> **Key constants**: `ver` (container magic, `word_125EFF4C`) = 4; manifest version field (`word_125E3854`) = 2;
> `flags` = 0. Per-install `gamever` (1.25.9.5) = `0x0005000900190001`.

---

## 0. Overview: the five lines from source to .MOD

```
                       CreateMod (sub_103FA610: read MOD.DAT metadata)
  .DAT  ──compile──▶ BINDAT  ┐
  .LAYOUT ─compile─▶ BINLAYOUT├─▶  written into the .MOD (header + PAK data section + manifest tree)
  scan-derive   ─▶ 7×RAW    ┤        ▲ compiled output "rides" under the SOURCE name (FOO.DAT, not FOO.DAT.BINDAT)
  level raycast ─▶ .MPP     ┘        │   but takes the compiled form's type code
                                     └─ PAK data section, per block: [u32 uncompressed][u32 compressed][zlib]
```

- **Compiled output stored under the source name, with the compiled type**: entry `FOO.DAT` (type 0 = BINDAT)
  carries the compiled BINDAT bytes; `FOO.LAYOUT` (type 1) carries BINLAYOUT. GUTS writes `.DAT.BINDAT` /
  `.LAYOUT.BINLAYOUT` to disk but does **not** list them separately in the manifest.
- Game side: `Torchlight2.exe` mounts the `.MOD` as a PAK archive over the `MEDIA/` subtree
  (`Ogre.log` shows `Added resource location 'MEDIA/UI/' of type 'PAK'`), and looks files up by path.

---

## 1. The `.MOD` container format

### 1.1 Three sections
```
out = _w_header(h, off_data, off_man)        # mod-info header (variable length, depends on strings)
    + data                                   # PAK data section [off_data, off_man)
    + _w_manifest(h, dirs)                    # TOC file tree (starts at off_man)
```
`off_data` = header length; `off_man` = `off_data + len(data)`.

### 1.2 Header (mod-info)
Writer `sub_103F5DA0`, reader `sub_103FA610`. Layout:
```
<HHQII> ver, modver, gamever, off_data, off_man
SS title; SS author; SS descr; SS website; SS download      # SS = ShortString: u16 char-count + UTF-16LE
<QIQ>   modid, flags, reqHash
<H> reqs_count;  per: SS(name) <QH> mod_id, version
<H> dels_count;  per: SS(path)
```
- **Field→slot** (RE'd from `sub_103FA610`/`sub_103F5DA0`): `NAME`→title(+40), `AUTHOR`→+68, `DESCRIPTION`→+152,
  `WEBSITE`→+96, `DOWNLOAD_URL`→+124, `MOD_ID`→modid(+240), `VERSION`→modver(+256), `REQUIRED_MODS`→reqs,
  `REMOVE_FILES`→dels. `MOD_FILE_NAME` is the **output filename**, not a header slot.
- **modver = VERSION + 1**: the publish path runs `++*(this+256)`.
- **reqHash** = recursive hash of REQUIRED_MODS (`sub_103F5500`); 0 when there are no deps (the common, offline-reproducible case).
- **gamever** = `read_gamever()` reads `Torchlight2.exe`'s VS_FIXEDFILEINFO (`sub_103F8CD0`, word order (minorMS,majorMS,privLS,buildLS)). Per-install constant.

### 1.3 Manifest (TOC file tree)
Writer `sub_102A5860`. Layout:
```
<HI> version (= word_125E3854 = 2), mhash      # ← mhash is the "hashValue" field
SS root("MEDIA/")
<II> file_count(fc), dir_count
per dir: SS(dirname) <I> rec_count
         per rec: <IB> crc32, type   SS(name)   <IIQ> off, size, filetime
```
- **Dir tree**: files are keyed by parent dir into a `std::map<wstring,…>` → dirs emitted in **UTF-16 path order**;
  each dir gets a **type-7 placeholder** for each child subdir. `DIR[0]=('', [type-7 'MEDIA/'])`, root = `MEDIA/`.
- **rec `off`** is **relative to the data-section start** (`off_data + off` = absolute position in the file).
- **`filetime`** = source mtime → Windows FILETIME. The game does not validate it; pure metadata.
- ⚠️ **Filenames must be UPPERCASE** (see 1.6).

### 1.4 PAK data section
Writer `sub_102A7100`. Layout:
```
<II> maxCompressedBlockSize, rollingHash      # 8-byte header (rollingHash: see 1.5)
per file (manifest order): <II> uncompressed_size, compressed_size(0=stored) + byte stream
```
- **maxCompressedBlockSize** = the largest compressed block, feeds the game's decompress read-buffer sizing.
- **Store vs compress** = `byte_11E94CD8[type]` (pak writer `sub_102A7100`: `if (byte_11E94CD8[type] && size < 0x1900000)` → compress). The table is 1 for types 0..23, **0 only for type 24 (.JPG)**. I.e. **everything is zlib-L6 except .JPG (stored)**; any block ≥ `0x1900000` (26 MB) is also stored.
  > Note: our offline packer uses **isal** (`isal_zlib`, SIMD DEFLATE, still zlib-format so the game inflates it; its crc32 equals the standard value; falls back to zlib if absent) — not byte-exact but functionally equivalent and ~3–5x faster.

### 1.5 The three hash/count fields (★ most critical, all three were misjudged at first)

| Field | Location | Game validates? | Our handling |
|---|---|---|---|
| **PAK rollingHash** | 2nd u32 of the data header | **Yes, validated** | **must be correct** (`_pak_rolling_hash`) |
| manifest mhash ("hashValue") | manifest header | No (read, never checked) | 0 is fine |
| manifest fc (FileCount) | manifest header | No (capacity hint) | write the literal record count |

**rollingHash — this is the root cause of "checkable in launcher but no in-game effect."** The loader (see 1.9)
**recomputes and compares** it; writing 0 → silent `"Unable to load mod."` → the whole file table is discarded → no content.
- Write (`sub_102A7100` tail) / validate (`sub_102A2690`) algorithm is **symmetric and deterministic**:
  - sampling stride `stride = N / rng(25,75)`, where `N` = data-section length;
  - **key**: the LCG (`sub_10285B30`: `state = state_hi + 695696193*state_lo`) is **seeded with N** via `sub_10285A50`
    (`sub_10285450` saves the old state, restored after) before the call → so the "random" divisor is a **deterministic
    function of N**:
    ```
    divisor = 25 + (695696193 * N  mod 2^32) mod 51
    stride  = max(2, N // divisor)
    h = N;   for offsets 8, 8+stride, … < N:  h = (int8)byte + 33*h  (mod 2^32)
    h = (int8)data[N-1] + 33*h        # plus the last byte (the 8-byte header at 0..7 is NOT sampled)
    rollingHash = h
    ```
  - Verified **byte-exact** against 30 shipped / editor-published `.MOD` files.
- **mhash** derives from `sub_10286420(15,25)` (debug string `"Rand Integer Between Seed VOLATILE"`); `sub_102A3320`
  reads it but **never compares** → truly random, 0 is fine.
- **fc**: native's own fc (e.g. 862) ≠ its actual record count (~618) yet it still loads → the game walks
  DirCount + per-dir counts, it does **not** use fc to bound iteration.

### 1.6 Filename case (★ the second in-game bug)
**GUTS uppercases every manifest filename** (collected in `sub_103F50D0`); the game's PAK lookup uppercases the query
path and matches it against the stored name **as-is** (assuming it is already uppercase).
- Consequence: a lowercase-on-disk `QLJX_F.dds` stored verbatim never matches the uppercased query `QLJX_F.DDS` → that
  resource silently fails to resolve. Concretely: `UNITS/PLAYERS/.../CLASS_QLJX_F.DAT` has `<STRING>ICON:QLJX_F_NORMAL`
  → (imageset) → `QLJX_F.dds` not found → **the class portrait shows a different image** (the class itself and its name
  render fine because they don't go through case-sensitive texture lookup).
- Fix: `_collect_media_files` stores the uppercased name (`str.upper()`: uppercases ASCII, leaves CJK unchanged — matching GUTS).

### 1.7 Type codes (`sub_102A1EA0` + compile remap `sub_102A24F0`)
By UPPER extension (with dot): `.DAT/.TEMPLATE`→0, `.LAYOUT`→1, `.MESH`→2, `.SKELETON`→3, `.DDS`→4, `.PNG`→5,
`.WAV/.OGG`→6, dir→7, `.MATERIAL`→8, `.RAW`→9, `.UILAYOUT`→10, `.IMAGESET`→11, `.TTF/.TTC`→12, `.FONT`→13,
`.ANIMATION`→16, `.HIE`→17, unknown→18, `.SCHEME`→19, `.LOOKNFEEL`→20, `.MPP`→21, `.BIK`→23, `.JPG`→24.
**Compiled output keeps the source name but takes the compiled form's type** (`.DAT.BINDAT` → classify by `.DAT` → 0).

### 1.8 Write path (CreateMod)
`CreateMod` (export `0x100DE830`) = read MOD.DAT metadata (`sub_103FA610`) + `Pathing_RegenAll_worker` (MPP, see §6)
+ `.MOD` pack (header `sub_103F5DA0` / manifest `sub_102A5860` / PAK `sub_102A7100`). The PAK is first written to
`PAKS/TMP.tmp`, then renamed.

### 1.9 Read / validation path (game loader)
Chain: `sub_103FB240` (logs `"Unable to load mod.\nFailed because :"`) → `sub_103F8BC0` (logs
`"Unable to load mod: <name>"`, returns 1 on success) → **`sub_103F83C0` (the real load/validate)**:
1. `if (*(this+312)) return 1;` (already loaded); `if (!*(this+200) || !*(this+276)) return 0;` (null file table / offMan → silent fail).
2. Top loop: resolve REQUIRED_MODS deps (`sub_103F8FF0` lookup + recursive `sub_103F83C0`); missing/wrong-version logs `"Unable to activate mod : … with guid:"` / `"… is not installed"`.
3. Reopen file; `sub_103F7E60` checks required-mods versions (no-op when there are no deps).
4. **reqHash compare**: `sub_103F5500(this,0)` recompute ?= stored reqHash (0==0 with no deps).
5. **`sub_102A3320`**: read manifest version (reject if `> word_125E3854(=2)`), read hashValue (not checked), then
   **`sub_102A2690` recomputes and compares rollingHash** — **this is the rollingHash validation point**; mismatch →
   `goto LABEL_27` (`fclose; return 0`, silent).

> I.e. the container structure, file list, and every content byte can be correct, yet a wrong rollingHash silently
> rejects the whole mod. That is the mechanism behind "launcher-checkable but no in-game effect."

### 1.10 Activation (MODGUID)
`<save>/modlauncher.sch`: `[MODS] <INTEGER64>MODGUID:<modid> [/MODS]`. The game loads the `.MOD` whose header modid
matches. So checking a mod activates it by **MOD_ID**, independent of filename/hash.

---

## 2. BINDAT (`.DAT` → binary)

Serializer chain `sub_10289A40` (+ string collector `sub_10289950`, interner `sub_1023E9F0`, node writer
`sub_10289860`); `sub_1028ED40` = WriteShortString.

### 2.1 Format
```
Header 12B: <III> version(=2), string_count, first_id
String table (ascending by id, GUTS iterates a std::map):
   entry0 = <H>len + wchar[]           # first entry has no id prefix (its id is first_id in the header)
   entryN = <I>id <H>len + wchar[]
Body = one recursive node:
   <II> name_hash(node name rg_hash), prop_count
   per prop: <II> key_hash(rg_hash), type   + value(8B if type∈{3,7}, else 4B)
   <I> child_count   + children...           # source order
```
- Types: `INTEGER`→1, `FLOAT`→2, `UNSIGNED INT`→4, `STRING`→5, `BOOL`→6, `INTEGER64`→7, `TRANSLATE`→8. Keys hashed with **rg_hash** (§7, uppercase).
- **STRING/TRANSLATE values store a string-table id**; the empty string uses the `0xFFFFFFFF` sentinel inline (not in the table).
- Encoding uses **surrogatepass**: the editor reads/writes the wchar stream verbatim with no UTF-16 surrogate-pair
  validation; `TAGS.DAT` splices a float-colour blob into a `<STRING>:` value (reinterpreted as lone surrogates), which
  requires surrogatepass for a byte round-trip.

### 2.2 String-id resolution model — ★ PER-FILE (model A, PROVEN)
- In the **shipped** format, ids come from a **global session counter** (`sub_1023E9F0`, `counter++`).
- **But the game resolves per-file** (model A): each BINDAT carries its own table; body ids resolve through **that
  file's table**.
  - **Hard proof**: the shipped base game has **565 cross-file id collisions** (the same id meaning different strings in
    different files, e.g. id 1398 = `'SET STAT ON LEVEL'` vs another string) yet the game loads/runs fine → a global
    merged table would have broken long ago.
  - The table is **sorted by id** → the game binary-searches each file's table → any (incl. sparse) id resolves.
- **Corollary**: the actual id values are irrelevant as long as they are **unique within the file**. So our offline
  packer **drops the corpus dictionary and uses per-file hash ids** (`HashStringDict`: `rg_hash(s)` + intra-file linear
  probe for uniqueness) → no shared state, embarrassingly parallel, deterministic; **validated in-game** (class/skills/icon all correct).
  - The corpus dict (rebuilt by scanning all shipped BINDATs into an id↔string map, `data/bindat_string_dict.pkl`) is now
    kept only for the "compiler byte-exact" test.

---

## 3. BINLAYOUT (`.LAYOUT` → binary)

Schema-driven per-descriptor encoders (`data/binlayout_schema.json`); writer chain
`sub_101169B0→sub_10116780→sub_10116650→sub_10116420→sub_10115320`, datagroup `sub_101150F0`.

### 3.1 Format
```
Header: <B>0x0B <B>flag(=4) <I>dg_off <H>obj_count(top-level)
Object (recursive):
   <I> block_size  <B> descriptor  <q> id
   str NAME(only when != the descriptor's default name)
   <B> prop_count   per prop: <H>mem <B>code + value
   <I> adprop_region   <H> child_count   + children...
```
### 3.2 Logic Group graph (in the ADPROP region)
`<B>count` + per logic object `{<B>ID <q>OBJECTID <f>X <f>Y <I>end_offset <B>link_count}` + links
`{<B>LINKINGTO str OUTPUTNAME str INPUTNAME}` (names inline, not resolved ids).

### 3.3 Datagroup (= `CLayoutBinaryGroup` tree, mirroring every `Group` object desc=1, synthetic root id=-1)
Node: `<q>id <B>CHOICE@16 <I>RANDOMIZATION@20 <B>NUMBER@24 <I>@28 <I>TAG@92 <B>@25(NO TAG FOUND)/@26(LEVEL UNIQUE)/@27(GAME MODE)
<I>+<q>[]ACTIVE THEMES <I>+<q>[]DEACTIVE THEMES <H>child_count`. `@28` = that Group object's block stream offset;
`TAG@92` = the runtime tag-registry id (`sub_10253630`, learned offline into `data/binlayout_datagroup_tags.json`).

---

## 4. The 7 RAW index files

Dispatcher `sub_1029BFA0`; `SS` = ShortString. Each indexes one class of source `.DAT/.LAYOUT`; scan order per row.

| RAW | Writer | Structure |
|---|---|---|
| **AFFIXES** | `sub_103C4170` | `<H>count`; per: SS(FILE) SS(NAME↑) `<IIII>`MIN_SPAWN(0)/MAX_SPAWN(999999)/WEIGHT(1)/DIFF(-1) `<B>`n + SS×(UNITTYPES) `<B>`n + SS×(NOT_UNITTYPES) |
| **SKILLS** | `sub_102ECFD0` | `<I>`count (only entries with non-empty NAME); per: SS(NAME↑) SS(FILE) `<q>`UNIQUE_GUID(-1) |
| **MISSILES** | `sub_102FB490` | `<H>`count; per: SS(FILE=.LAYOUT) `<B>`n + SS×(the MISSILE NAME↑ of each DESCRIPTOR:Missile object) |
| **TRIGGERABLES** | — | `<H>`count; per: SS(FILE) SS(NAME) |
| **UI** | `sub_103178E0` | `<I>`count (only Menu Definition with non-empty MENU NAME, not DO NOT CREATE); per: SS(MENU NAME) SS(FILE) `<II>`TYPE/GAME STATE enum idx `<BBB>`(ALWAYS VISIBLE‖CREATE ON LOAD)/MP only/SP only SS(KEY BINDING) |
| **UNITDATA** | `sub_1026CC50` / reader `sub_1026F2B0` | 4 categories (ITEMS/MONSTERS/PLAYERS/PROPS) each: `<I>`count; per: `<q>`UNIT_GUID SS(NAME↑) SS(FILE) `<B>`flags(bit0=CREATEAS==EQUIPMENT, bit1=SET) `<iiiii>`LEVEL/MIN/MAX/RARITY/RARITY_HC SS(UNITTYPE↑). **Fields resolve through the full BASEFILE inheritance chain** (child→parent, first value != default); DONTCREATE abstract bases skipped |
| **ROOMPIECES** | — | `<I>`count; per SS(FILE); then per `<I>`GUIDs + `<q>`GUID× |

- **Scan order**: AFFIXES/SKILLS/UNITDATA/MISSILES = **name-interleaved DFS** (files and subdirs merged by name,
  recursed in place); TRIGGERABLES/UI/ROOMPIECES = files-before-dirs. `_media_path`: `MEDIA/` + relative path, **uppercased** (non-ASCII left as-is).
- **GUID type gotcha**: in `.DAT` it is `<INTEGER64>GUID:`, in `.LAYOUT` it is `<STRING>GUID:` — same value, different type.
- Byte-verified: AFFIXES/SKILLS/MISSILES/UI/UNITDATA all reproduce the shipped RAW byte-for-byte.

---

## 5. MPP pathing files (`.mpp`)

### 5.1 Format
One `.mpp` next to each `.layout`, same base name:
```
24B header: <iiffff> gw, gh, worldW, worldD, originW, originD
then gw*gh bytes: 1 byte per cell of walkability (0/1/255)
```
- cell = **0.4 units**; region snap = `floor((min-0.2)/10)*10 / ceil((max+0.2)/10)*10`.
- **PATH NODE OCCUPATION is runtime-only**, not baked into the .mpp (only 3 byte values 0/1/255).

### 5.2 Generate / write path (`EditorRegenPathingData`)
Export `0x100DDDE0` → `Pathing_RegenAll_worker` (`sub_10018750`): scan `*.layout` → **single-threaded** do/while over each
file via `Pathing_RegenSingleFile_worker` (`sub_10015FA0`), with an Ogre resource-unload sweep every 20 files. Per file:
`CLevel_ctor` (`sub_101FD170`, 1160B object) → set flags → `CLevel_SetMppOutputPath` (`sub_1000B980`) →
**`CLevel_LoadLevelData` (`sub_1020AB90`, parse the layout + load every collision mesh via Ogre + assemble the collision
world)** → raycast each cell → write .mpp → destroy. The dominant cost is **Ogre mesh loading + the CLevel lifecycle**, not the raycast.

### 5.3 Offline / headless generation
- Offline numba backend (`mpp/native_nb.py`): `@njit(fastmath=False)` mirrors the scalar kernels, bit-identical IEEE754;
  ~99.7% of cells match native (the rest = cliff/overhang float tie-breaks + nocollide cave walls, not reproducible).
- **Headless byte-exact**: drive the real DLL (fork `TL2-Mikuro-Console.exe`) `InitEditor` + `EditorSetWorkingMod` +
  `CreateMod` (double pass: pass 1 writes .BINLAYOUT + stub .mpp, pass 2 writes the real .mpp). InitEditor is ~6.24s once
  (Ogre/PAK/room-piece data ~3s + FMOD+D3D9 device ~2s + shaders).

---

## 6. Editor lifecycle

- **InitEditor** (`0x10001DD0`): thin wrapper → `sub_10017120` (848B editor-object ctor, contains D3D9/FMOD/Ogre) +
  `sub_10019A00`. The MPP raycast is **pure CPU geometry, no GPU needed**, but `CLevel_LoadLevelData` loads meshes via
  Ogre's resource manager (by default creating hardware buffers through the RenderSystem) → **the D3D9 device is
  load-bearing for mesh loading**, can't be trivially skipped; FMOD can.
- **CreateMod** (`0x100DE830`) = metadata + MPP + .MOD pack; only accepts projects under `<install>/mods/`.
- **Crash attribution**: an AccessViolation in the game/editor's render tick = RTX 3070 + legacy D3D9 driver bug
  (fix: Threaded Optimization off / cap FPS / DXVK), **not** the packing pipeline.

---

## 7. rg_hash (GUTS 32-bit string hash)

Used for BINDAT **node names / key names** (and, in our per-file BINDAT, the string ids). Implementation in
`mikuro_mod_packer/rghash.py` (cracked, verified against known (string→hash) pairs). Note: BINDAT **string values** do
NOT use the hash — they use the id table; rg_hash only hashes keys/names.

---

## 8. Cross-cutting notes & corrected earlier conclusions

- ✅ **Offline pack == native, functionally** (proven field-by-field for MIKURO_CLASS_QLJX_EN): identical file list,
  BINDAT semantics, mesh/texture/skeleton/material, RAW sets, header; the only differences are the (proven-harmless)
  random mhash/rollingHash values, benign SKILLS.RAW order, benign BINDAT id numbering, and one LAYOUT whose **source is
  malformed** (`CHILDREN]` missing its `[`).
- ❌ **Corrected**: the early conclusion "rollingHash is random / ignored by the game" was **wrong** — it IS validated
  (its stride RNG is seeded with N → deterministic), and must be computed correctly.
- ❌ **Corrected**: the early work missed that **manifest filenames must be uppercased**, causing lowercase `.dds` etc. to fail to resolve.
- **Manifest record order** differs from native (native = the raw NTFS FindFirstFile order at editor-pack time), but is
  **harmless** (the game uses path lookups, not order).

---

## Appendix A: key function addresses (EditorGuts.dll, imagebase 0x10000000)

| Function | Address |
|---|---|
| InitEditor / CreateMod / EditorSetWorkingMod / EditorRegenPathingData | `0x10001DD0` / `0x100DE830` / `0x100E3B50` / `0x100DDDE0` |
| MOD header write / read | `sub_103F5DA0` / `sub_103FA610` |
| Manifest write | `sub_102A5860` |
| PAK data write (+ rollingHash compute) | `sub_102A7100` |
| Type classify / compile remap / store table | `sub_102A1EA0` / `sub_102A24F0` / `byte_11E94CD8` |
| Load report / "Unable to load mod" / **load validate** | `sub_103FB240` / `sub_103F8BC0` / `sub_103F83C0` |
| required-mods check / reqHash / gamever read | `sub_103F7E60` / `sub_103F5500` / `sub_103F8CD0` |
| manifest+PAK validate / **rollingHash validate** | `sub_102A3320` / `sub_102A2690` |
| rollingHash seed RNG: "rand between" / LCG / set seed / save state | `sub_10286420` / `sub_10285B30` / `sub_10285A50` / `sub_10285450` |
| BINDAT: serialize / collect strings / interner / node write / WriteShortString | `sub_10289A40` / `sub_10289950` / `sub_1023E9F0` / `sub_10289860` / `sub_1028ED40` |
| BINLAYOUT: writer chain / datagroup / tag registry | `sub_101169B0…sub_10115320` / `sub_101150F0` / `sub_10253630` |
| RAW: dispatch / AFFIXES / SKILLS / MISSILES / UI / UNITDATA (write/read) | `sub_1029BFA0` / `sub_103C4170` / `sub_102ECFD0` / `sub_102FB490` / `sub_103178E0` / `sub_1026CC50`·`sub_1026F2B0` |
| MPP: RegenAll / RegenSingleFile / CLevel ctor·LoadLevelData·SetMppOutputPath | `sub_10018750` / `sub_10015FA0` / `sub_101FD170`·`sub_1020AB90`·`sub_1000B980` |

## Appendix B: companion resources

- **Code**: `mikuro_mod_packer/` (`packer.py` container+orchestration, `bindat.py`, `binlayout.py`, `raw.py`, `rghash.py`, `mpp/`); CLI `python -m mikuro_mod_packer`.
- **Memory**: `mod-container-hash-count-fields-and-activation` (rollingHash/mhash/fc/activation), `mod-manifest-uppercase-filenames` (case), `bindat-binlayout-template-echo` (BIN*/RAW/container + per-file hash), `mpp-*` (.mpp format / headless regen / corpus accuracy, etc.).
- **Tools**: `tools/mod_disasm.py` (.MOD disassembler), `cmp_mod.py`/`cmp_bindat.py` (native-vs-ours diff), `verify_container_writer.py` (container writer byte-exact), `bench_all_mods.py`/`bench_native.py` (benchmarks), `tools/tl2_console_fork/` (headless driver fork).
- **Performance**: see `开发日志/性能优化记录.md` #6 (full-corpus pack 185.5→83s).
