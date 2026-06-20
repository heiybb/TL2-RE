# TL2 EditorGuts.dll Reverse-Engineering Record — MOD packing / reading data structures

> The goal, in one line: build a `.MOD` straight from `.DAT/.LAYOUT` sources **offline, with no editor running** — one
> that's **functionally equivalent to the native DLL's pack and actually takes effect in-game**.
>
> This is the design basis for the `mikuro_mod_packer/` package. It lays out the five formats TL2 packing touches —
> **MOD container / BINDAT / BINLAYOUT / RAW / MPP** — and, just as importantly, **how the native DLL writes each one and
> how it reads/validates them back**.
>
> How it was dug out: IDA (idalib MCP) disassembly of `E:\Torchlight 2\EditorGuts.dll` (32-bit, imagebase `0x10000000`),
> plus `Torchlight2.exe` for the read side, cross-checked on disk against `Ogre.log` / `modlauncher.sch`, and a byte-level
> diff of our output against shipped data and native packs. Every `sub_XXXXXXXX` below is an absolute address. The living
> companions are the in-code comments (each carries its addresses / byte layouts).
>
> A few constants thread through the whole thing, so they go up front: `ver` (container magic, `word_125EFF4C`) = 4;
> manifest version field (`word_125E3854`) = 2; `flags` = 0; the per-install `gamever` (1.25.9.5) = `0x0005000900190001`.

---

## 0. Overview: the five lines from source to .MOD

Before drowning in detail, here's the whole picture — five lines converging on one `.MOD`:

```
                       CreateMod (sub_103FA610: read MOD.DAT metadata)
  .DAT  ──compile──▶ BINDAT  ┐
  .LAYOUT ─compile─▶ BINLAYOUT├─▶  written into the .MOD (header + PAK data section + manifest tree)
  scan-derive   ─▶ 7×RAW    ┤        ▲ compiled output "rides" under the SOURCE name (FOO.DAT, not FOO.DAT.BINDAT)
  level raycast ─▶ .MPP     ┘        │   but takes the compiled form's type code
                                     └─ PAK data section, per block: [u32 uncompressed][u32 compressed][zlib]
```

There's one detail here that's easy to read right past: **the compiled output is stored under the source name, but with the
compiled form's type code.** The entry `FOO.DAT` (type 0 = BINDAT) actually carries the compiled BINDAT bytes; `FOO.LAYOUT`
(type 1) carries BINLAYOUT. GUTS does drop `.DAT.BINDAT` / `.LAYOUT.BINLAYOUT` onto disk, but it does **not** list those
separately in the manifest — only the source-named entry makes it in.

The game side is blunter about it: `Torchlight2.exe` mounts the `.MOD` as a PAK archive over the `MEDIA/` subtree
(`Ogre.log` shows `Added resource location 'MEDIA/UI/' of type 'PAK'`) and from then on looks everything up by path.

---

## 1. The `.MOD` container format

### 1.1 Three sections
The whole file is just three sections concatenated:
```
out = _w_header(h, off_data, off_man)        # mod-info header (variable length, depends on strings)
    + data                                   # PAK data section [off_data, off_man)
    + _w_manifest(h, dirs)                    # TOC file tree (starts at off_man)
```
`off_data` = header length; `off_man` = `off_data + len(data)`. The structure isn't the hard part — the hash fields further
down are.

### 1.2 Header (mod-info)
Writer `sub_103F5DA0`, reader `sub_103FA610`. Layout:
```
<HHQII> ver, modver, gamever, off_data, off_man
SS title; SS author; SS descr; SS website; SS download      # SS = ShortString: u16 char-count + UTF-16LE
<QIQ>   modid, flags, reqHash
<H> reqs_count;  per: SS(name) <QH> mod_id, version
<H> dels_count;  per: SS(path)
```
Which MOD.DAT field lands in which slot I pulled out of `sub_103FA610`/`sub_103F5DA0` one at a time: `NAME`→title(+40),
`AUTHOR`→+68, `DESCRIPTION`→+152, `WEBSITE`→+96, `DOWNLOAD_URL`→+124, `MOD_ID`→modid(+240), `VERSION`→modver(+256),
`REQUIRED_MODS`→reqs, `REMOVE_FILES`→dels. Watch out: `MOD_FILE_NAME` is the **output filename**, not a header slot at all.

A few things that bite if you get them wrong:
- **modver = VERSION + 1**: the publish path runs `++*(this+256)`, so the version on disk is one higher than what you wrote.
- **reqHash** = recursive hash of REQUIRED_MODS (`sub_103F5500`); it's 0 when there are no deps — which is the only case we
  can cleanly reproduce offline, so deps are out of scope for now.
- **gamever** isn't hardcoded — `read_gamever()` actually reads `Torchlight2.exe`'s VS_FIXEDFILEINFO (`sub_103F8CD0`, word
  order (minorMS,majorMS,privLS,buildLS)). A per-install constant.

### 1.3 Manifest (TOC file tree)
Writer `sub_102A5860`. Layout:
```
<HI> version (= word_125E3854 = 2), mhash      # ← mhash is the "hashValue" field
SS root("MEDIA/")
<II> file_count(fc), dir_count
per dir: SS(dirname) <I> rec_count
         per rec: <IB> crc32, type   SS(name)   <IIQ> off, size, filetime
```
- **The dir tree is sorted, not authored**: files are keyed by parent dir into a `std::map<wstring,…>`, so dirs come out in
  **UTF-16 path order**; each dir also leaves a **type-7 placeholder** for each child subdir. `DIR[0]=('', [type-7 'MEDIA/'])`,
  root = `MEDIA/`.
- **The rec `off`** is **relative to the data-section start** — don't forget to add `off_data` for the absolute position in
  the file. It's easy to miss this when computing offsets.
- **`filetime`** = source mtime → Windows FILETIME. The game never looks at it; pure metadata.
- ⚠️ **Filenames must be UPPERCASE** — important enough to get its own section (1.6).

### 1.4 PAK data section
Writer `sub_102A7100`. Layout:
```
<II> maxCompressedBlockSize, rollingHash      # 8-byte header (rollingHash: see 1.5)
per file (manifest order): <II> uncompressed_size, compressed_size(0=stored) + byte stream
```
- **maxCompressedBlockSize** = the largest compressed block; it sizes the game's decompress read-buffer.
- **Store vs compress** = `byte_11E94CD8[type]` (pak writer `sub_102A7100`: `if (byte_11E94CD8[type] && size < 0x1900000)`
  → compress). The table is 1 for types 0..23, **0 only for type 24 (.JPG)**. So **everything is zlib-L6 except .JPG (stored)**;
  and any block ≥ `0x1900000` (26 MB) is stored too.
  > Our offline packer swaps the implementation here — it uses **isal** (`isal_zlib`, SIMD DEFLATE,
  > still zlib-format so the game inflates it just fine; its crc32 equals the standard value; falls back to plain zlib if it's
  > not installed). Not byte-exact, but functionally identical and ~3–5x faster.

### 1.5 The three hash/count fields (★ most critical — and I misjudged all three at first)

| Field | Location | Game validates? | Our handling |
|---|---|---|---|
| **PAK rollingHash** | 2nd u32 of the data header | **Yes, validated** | **must be correct** (`_pak_rolling_hash`) |
| manifest mhash ("hashValue") | manifest header | No (read, never checked) | 0 is fine |
| manifest fc (FileCount) | manifest header | No (capacity hint) | write the literal record count |

**rollingHash — this is the culprit behind "I ticked it in the launcher and nothing happened in-game."** The loader (see 1.9)
**recomputes it and compares**; write 0 and you get a silent `"Unable to load mod."`, the whole file table gets discarded, and
you end up with zero content and no error to point at. This one took us a long time to corner.

Once the algorithm was fully picked apart, it turned out the write (`sub_102A7100` tail) and validate (`sub_102A2690`) sides
are **symmetric and fully deterministic**:
- sampling stride `stride = N / rng(25,75)`, where `N` = data-section length;
- **the key bit**: that LCG (`sub_10285B30`: `state = state_hi + 695696193*state_lo`) gets **seeded with N** via `sub_10285A50`
  right before the call (`sub_10285450` saves the old state and restores it afterward). So the "random" divisor is really a
  **deterministic function of N**:
    ```
    divisor = 25 + (695696193 * N  mod 2^32) mod 51
    stride  = max(2, N // divisor)
    h = N;   for offsets 8, 8+stride, … < N:  h = (int8)byte + 33*h  (mod 2^32)
    h = (int8)data[N-1] + 33*h        # plus the last byte (the 8-byte header at 0..7 is NOT sampled)
    rollingHash = h
    ```
  - Verified **byte-exact** against 30 shipped / editor-published `.MOD` files. That match is what confirmed it.
- **mhash** derives from `sub_10286420(15,25)` (the debug string `"Rand Integer Between Seed VOLATILE"` gave it away);
  `sub_102A3320` reads it but **never compares** → it's genuinely random, so 0 is fine.
- **fc**: native's own fc (e.g. 862) doesn't even match its real record count (~618), yet it loads fine → the game walks
  DirCount + per-dir counts and **never uses fc** to bound iteration.

### 1.6 Filename case (★ the second in-game bug)
**GUTS uppercases every manifest filename** (collected in `sub_103F50D0`); the game's PAK lookup then uppercases the query
path and matches it against the stored name **as-is** (it assumes you're already uppercase).

The moment the two sides disagree on case, it fails silently. Here's the scene we actually hit: a lowercase-on-disk
`QLJX_F.dds`, stored verbatim, never matches the uppercased query `QLJX_F.DDS` → the texture silently goes missing. It
surfaces in a baffling way: `UNITS/PLAYERS/.../CLASS_QLJX_F.DAT` has `<STRING>ICON:QLJX_F_NORMAL` → (imageset) → `QLJX_F.dds`,
not found → **the class portrait renders as some other image** — while the class itself and its name show up fine (they don't go
through case-sensitive texture lookup), which made it all the more confusing.
- Fix: `_collect_media_files` stores the uppercased name (`str.upper()`: uppercases ASCII, leaves CJK untouched — matching GUTS).

### 1.7 Type codes (`sub_102A1EA0` + compile remap `sub_102A24F0`)
By UPPER extension (with dot): `.DAT/.TEMPLATE`→0, `.LAYOUT`→1, `.MESH`→2, `.SKELETON`→3, `.DDS`→4, `.PNG`→5,
`.WAV/.OGG`→6, dir→7, `.MATERIAL`→8, `.RAW`→9, `.UILAYOUT`→10, `.IMAGESET`→11, `.TTF/.TTC`→12, `.FONT`→13,
`.ANIMATION`→16, `.HIE`→17, unknown→18, `.SCHEME`→19, `.LOOKNFEEL`→20, `.MPP`→21, `.BIK`→23, `.JPG`→24.
And once more, that same trap: **compiled output keeps the source name but takes the compiled form's type** (`.DAT.BINDAT` is
classified by `.DAT` → 0).

### 1.8 Write path (CreateMod)
`CreateMod` (export `0x100DE830`) does three things: read MOD.DAT metadata (`sub_103FA610`) + `Pathing_RegenAll_worker` (MPP,
see §6) + pack the `.MOD` (header `sub_103F5DA0` / manifest `sub_102A5860` / PAK `sub_102A7100`). The PAK is written to
`PAKS/TMP.tmp` first, then renamed.

### 1.9 Read / validation path (game loader)
This chain is how we finally understood the "no effect" culprit, so walk it through: `sub_103FB240` (logs
`"Unable to load mod.\nFailed because :"`) → `sub_103F8BC0` (logs `"Unable to load mod: <name>"`, returns 1 on success) →
**`sub_103F83C0` (the real load/validate)**:
1. `if (*(this+312)) return 1;` (already loaded); `if (!*(this+200) || !*(this+276)) return 0;` (null file table / offMan → silent fail).
2. Top loop: resolve REQUIRED_MODS deps (`sub_103F8FF0` lookup + recursive `sub_103F83C0`); missing/wrong-version logs `"Unable to activate mod : … with guid:"` / `"… is not installed"`.
3. Reopen file; `sub_103F7E60` checks required-mods versions (no-op when there are no deps).
4. **reqHash compare**: `sub_103F5500(this,0)` recompute ?= stored reqHash (0==0 with no deps).
5. **`sub_102A3320`**: read manifest version (reject if `> word_125E3854(=2)`), read hashValue (not checked), then
   **`sub_102A2690` recomputes and compares rollingHash** — **this is the rollingHash validation point**; a mismatch →
   `goto LABEL_27` (`fclose; return 0`, silent).

> So you can end up in this confusing state: the container structure is right, the file list is right, every content byte is
> right — and one wrong rollingHash field silently rejects the entire mod. That single step is the whole mechanism behind
> "checkable in the launcher but no in-game effect."

### 1.10 Activation (MODGUID)
`<save>/modlauncher.sch`: `[MODS] <INTEGER64>MODGUID:<modid> [/MODS]`. The game loads the `.MOD` whose header modid matches.
So ticking a mod activates it by **MOD_ID** — nothing to do with the filename or any hash.

---

## 2. BINDAT (`.DAT` → binary)

Serializer chain `sub_10289A40` (with string collector `sub_10289950`, interner `sub_1023E9F0`, node writer `sub_10289860`);
`sub_1028ED40` = WriteShortString.

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
- Encoding has to use **surrogatepass**: the editor reads/writes the wchar stream verbatim with no UTF-16 surrogate-pair
  validation. `TAGS.DAT` splices a float-colour blob straight into a `<STRING>:` value (which gets reinterpreted as lone
  surrogates), and nothing short of surrogatepass will byte-round-trip that — it's the kind of garbage you only find by
  stepping on it, not by reasoning about it.

### 2.2 String-id resolution model — ★ PER-FILE (model A, PROVEN)
This is one of the more important pieces of BINDAT reasoning:
- In the **shipped** format, ids look like a **global session counter** (`sub_1023E9F0`, `counter++`). The obvious guess is
  a single global table.
- **But the game resolves per-file** (model A): each BINDAT carries its own table, and body ids resolve through **that file's table**.
  - **Hard proof**: the shipped base game ships with **565 cross-file id collisions** (the same id meaning different strings in
    different files — e.g. id 1398 = `'SET STAT ON LEVEL'` here, something else there) and the game runs perfectly fine → a
    single global merged table would have broken long ago.
  - The table is **sorted by id**, so the game binary-searches each file's table → any id resolves, however sparse.
- **The corollary**: the actual id values don't matter at all, as long as they're **unique within the file**.
  So our offline packer **throws out the corpus dictionary and uses per-file hash ids** (`HashStringDict`: `rg_hash(s)` plus an
  intra-file linear probe for uniqueness) → no shared state, embarrassingly parallel, deterministic. Already **validated in-game**
  (class, skills, icon all correct).
  - The corpus dict (rebuilt by scanning every shipped BINDAT into an id↔string map, `data/bindat_string_dict.pkl`) is kept
    around only for the "compiler byte-exact" test.

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

Dispatcher `sub_1029BFA0`; `SS` = ShortString below. Each RAW indexes one class of source `.DAT/.LAYOUT`; scan order is per row.

| RAW | Writer | Structure |
|---|---|---|
| **AFFIXES** | `sub_103C4170` | `<H>count`; per: SS(FILE) SS(NAME↑) `<IIII>`MIN_SPAWN(0)/MAX_SPAWN(999999)/WEIGHT(1)/DIFF(-1) `<B>`n + SS×(UNITTYPES) `<B>`n + SS×(NOT_UNITTYPES) |
| **SKILLS** | `sub_102ECFD0` | `<I>`count (only entries with non-empty NAME); per: SS(NAME↑) SS(FILE) `<q>`UNIQUE_GUID(-1) |
| **MISSILES** | `sub_102FB490` | `<H>`count; per: SS(FILE=.LAYOUT) `<B>`n + SS×(the MISSILE NAME↑ of each DESCRIPTOR:Missile object) |
| **TRIGGERABLES** | — | `<H>`count; per: SS(FILE) SS(NAME) |
| **UI** | `sub_103178E0` | `<I>`count (only Menu Definition with non-empty MENU NAME, not DO NOT CREATE); per: SS(MENU NAME) SS(FILE) `<II>`TYPE/GAME STATE enum idx `<BBB>`(ALWAYS VISIBLE‖CREATE ON LOAD)/MP only/SP only SS(KEY BINDING) |
| **UNITDATA** | `sub_1026CC50` / reader `sub_1026F2B0` | 4 categories (ITEMS/MONSTERS/PLAYERS/PROPS) each: `<I>`count; per: `<q>`UNIT_GUID SS(NAME↑) SS(FILE) `<B>`flags(bit0=CREATEAS==EQUIPMENT, bit1=SET) `<iiiii>`LEVEL/MIN/MAX/RARITY/RARITY_HC SS(UNITTYPE↑). **Fields resolve through the full BASEFILE inheritance chain** (child→parent, first value != default); DONTCREATE abstract bases skipped |
| **ROOMPIECES** | — | `<I>`count; per SS(FILE); then per `<I>`GUIDs + `<q>`GUID× |

A handful of things that'll burn you if they aren't spelled out:
- **Scan order isn't uniform**: AFFIXES/SKILLS/UNITDATA/MISSILES use a **name-interleaved DFS** (files and subdirs merged by
  name and recursed in place); TRIGGERABLES/UI/ROOMPIECES are files-before-dirs. `_media_path`: `MEDIA/` + relative path,
  **uppercased** (non-ASCII left as-is). Mixing those two orders up is an easy mistake.
- **GUID type gotcha**: the same value is `<INTEGER64>GUID:` in `.DAT` but `<STRING>GUID:` in `.LAYOUT`. Match both.
- Byte-verified: AFFIXES/SKILLS/MISSILES/UI/UNITDATA all reproduce the shipped RAW byte-for-byte.

---

## 5. MPP pathing files (`.mpp`)

### 5.1 Format
One `.mpp` sitting next to each `.layout`, same base name:
```
24B header: <iiffff> gw, gh, worldW, worldD, originW, originD
then gw*gh bytes: 1 byte per cell of walkability (0/1/255)
```
- cell = **0.4 units**; region snap = `floor((min-0.2)/10)*10 / ceil((max+0.2)/10)*10`.
- **PATH NODE OCCUPATION is runtime-only**, never baked into the .mpp (which only ever holds 0/1/255).

### 5.2 Generate / write path (`EditorRegenPathingData`)
Export `0x100DDDE0` → `Pathing_RegenAll_worker` (`sub_10018750`): scan `*.layout` → a **single-threaded** do/while over each
file via `Pathing_RegenSingleFile_worker` (`sub_10015FA0`), with an Ogre resource-unload sweep every 20 files. Per file:
`CLevel_ctor` (`sub_101FD170`, 1160B object) → set flags → `CLevel_SetMppOutputPath` (`sub_1000B980`) →
**`CLevel_LoadLevelData` (`sub_1020AB90`, parse the layout + load every collision mesh via Ogre + assemble the collision
world)** → raycast each cell → write .mpp → destroy. The dominant cost is **Ogre mesh loading + the CLevel lifecycle**, not the
raycast — which is exactly why skipping Ogre offline buys so much.

### 5.3 Offline / headless generation
- Offline numba backend (`mpp/native_nb.py`): `@njit(fastmath=False)` mirrors the scalar kernels, bit-identical IEEE754; ~99.7%
  of cells match native (the rest = cliff/overhang float tie-breaks + nocollide cave walls, which aren't reproducible).
- **Headless byte-exact**: when you truly need 100%, drive the real DLL (fork `TL2-Mikuro-Console.exe`) `InitEditor` +
  `EditorSetWorkingMod` + `CreateMod` (double pass: pass 1 writes .BINLAYOUT + a stub .mpp, pass 2 writes the real .mpp).
  InitEditor is ~6.24s once (Ogre/PAK/room-piece data ~3s + FMOD+D3D9 device ~2s + shaders).

---

## 6. Editor lifecycle

- **InitEditor** (`0x10001DD0`): a thin wrapper → `sub_10017120` (848B editor-object ctor, holding D3D9/FMOD/Ogre) +
  `sub_10019A00`. Here's the counter-intuitive finding: the MPP raycast is **pure CPU geometry, no GPU needed**, but
  `CLevel_LoadLevelData` loads meshes through Ogre's resource manager (which by default builds hardware buffers via the
  RenderSystem) → **the D3D9 device is load-bearing for mesh loading** and can't just be skipped; FMOD, on the other hand, can.
  That single fact decides what "headless" can and can't drop.
- **CreateMod** (`0x100DE830`) = metadata + MPP + .MOD pack; and it only accepts projects under `<install>/mods/`.
- **Crash attribution**: an AccessViolation in the game/editor's render tick is the RTX 3070 + legacy D3D9 driver bug (fix:
  Threaded Optimization off / cap FPS / DXVK), **not** the packing pipeline. It's easy to misattribute this to the packer; it isn't.

---

## 7. rg_hash (GUTS 32-bit string hash)

Used for BINDAT **node names / key names** (and, in our per-file BINDAT, the string ids). Implementation in
`mikuro_mod_packer/rghash.py` (cracked, verified against known (string→hash) pairs). One thing not to mix up: BINDAT **string
values** do NOT use the hash — those go through the id table; rg_hash only hashes keys and names.

---

## 8. Cross-cutting notes & a few earlier conclusions I had to walk back

- ✅ **Offline pack == native, functionally** (proven field-by-field for MIKURO_CLASS_QLJX_EN): identical file list, BINDAT
  semantics, mesh/texture/skeleton/material, RAW sets, header. The only differences left are the (proven-harmless) random
  mhash/rollingHash values, benign SKILLS.RAW order, benign BINDAT id numbering, and one LAYOUT whose **source is itself
  malformed** (`CHILDREN]` missing its `[`).
- ❌ **Corrected**: my early call that "rollingHash is random / the game ignores it" was **flat wrong** — it IS validated (its
  stride RNG is seeded with N → deterministic) and has to be computed correctly. This was the project's worst misjudgment.
- ❌ **Corrected**: the early work missed that **manifest filenames must be uppercased**, which made lowercase `.dds` and friends fail to resolve.
- **Manifest record order** differs from native (native = the raw NTFS FindFirstFile order at editor-pack time), but is
  **harmless** — the game looks up by path, not by order.

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
- **Tools**: `tools/mod_disasm.py` (.MOD disassembler), `cmp_mod.py`/`cmp_bindat.py` (native-vs-ours diff), `verify_container_writer.py` (container writer byte-exact), `bench_all_mods.py`/`bench_native.py` (benchmarks), `tools/tl2_console_fork/` (headless driver fork).
- **Performance**: see [`性能优化记录.md`](性能优化记录.md) (full-corpus pack 185.5→82s).
