#!/usr/bin/env python3
"""
Mikuro MOD Packer — Complete TL2 MOD builder
=============================================
Pipeline (mirrors EditorGuts CreateMod): compile sources → binary, build RAW
indices, build .MPP pathing grids, pack into a .MOD container — entirely FROM
SCRATCH. No existing .MOD is needed or used as a structure reference: the header
is synthesized from MOD.DAT (build_header) and the manifest dir-tree from a MEDIA
scan (build_manifest_dirs), exactly as GUTS' CreateMod does. This builds mods that
ship with no / a 0-byte .MOD (e.g. 挑战者大陆--地图拓展, 44k files).
  1. read MOD.DAT metadata → header (build_header)
  2. DAT    → BINDAT      (bindat.py     — real from-scratch compiler)
  3. LAYOUT → BINLAYOUT   (binlayout.py  — real from-scratch compiler)
  4. 7 × RAW index files  (raw.py        — byte-verified vs GUTS)
  5. LAYOUT → .MPP        (mpp/          — offline pathing grids, optional)
  6. scan MEDIA → manifest tree (build_manifest_dirs) + pack into <name>.MOD
     (container writer, this file)

Dependency map — the modules this packer uses (all in this package):
    packer.py  (this file: .MOD container + orchestration)
    ├── bindat.py      → rghash.py   (+ data/bindat_string_dict.pkl corpus dict)
    ├── binlayout.py   (+ data/binlayout_schema.json, data/binlayout_datagroup_tags.json)
    ├── raw.py
    └── mpp/           (offline .MPP pathing-grid generator — APPROXIMATE; needs
                        numpy, so it is LAZY-IMPORTED only when --mpp is requested.
                        Optional byte-exact DLL backend via mpp/dll.py.)
  Superseded predecessors live in ../legacy/ (dat2bindat*.py, mod_packer.py) and
  are NOT used here. parse_layout.py (the Godot exporter) is unrelated to packing.

Usage: python -m mikuro_mod_packer [--mpp {re,dll,none}] [--raw {auto,none}] <mod_directory>
  RAW indexes are emitted ON-DEMAND (--raw auto, default): only for the content
  types this mod actually ships source for; --raw none skips them entirely.
"""
import os, sys, struct, re, zlib, time, shutil
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from .bindat import compile_dat  # real from-scratch DAT compiler (per-file hash ids)
from .binlayout import convert as layout_to_binlayout
from . import raw as rg_raw  # RAW writers ported from TL2Lib (byte-verified vs GUTS)

# Pack compression backend: prefer isal (SIMD DEFLATE) if installed — its output is
# zlib-format (the game inflates it) and its crc32 is the standard CRC-32 (identical
# values to zlib), so it's a drop-in. Measured ~3x faster than stdlib zlib at level
# 6's ratio (+~5% size on a texture-heavy mod). Falls back to stdlib zlib if absent.
# isal levels are 0-3 (3=best); zlib 0-9 (6=GUTS' level).
try:
    from isal import isal_zlib as _COMP
    _COMP_LEVEL = 3
except ImportError:
    import zlib as _COMP
    _COMP_LEVEL = 6

# The DAT→BINDAT compiler resolves STRING/TRANSLATE values to the game's global
# string-id dictionary. That dictionary is a corpus resource built once from the
# base-game install (cached to data/bindat_string_dict.pkl), NOT from the mod being
# packed — analogous to parse_layout.py parsing every base-game .material first.
TL2_MEDIA_DIR = os.environ.get('TL2_MEDIA_DIR', r"E:\Torchlight 2\MEDIA")

# LAYOUT→BINLAYOUT is CPU-heavy per file (~26ms) and needs no shared state, so
# it parallelizes well (~3.5x on 8 procs). DAT→BINDAT is too fine-grained
# (~6ms/file) — IPC + per-worker hash-DB pickling cancel the gain, so it stays
# serial. Only spin up a process pool when there are enough layout jobs to
# amortize spawn cost (Windows uses spawn).
_MP_MIN_LAYOUT_JOBS = 48


def _layout_job(job):
    """Process-pool worker: returns (bindat_path, bytes-or-None, error-or-None)."""
    lp, bp = job
    try:
        return bp, layout_to_binlayout(lp, bp), None
    except Exception as e:
        return bp, None, f'{lp}: {e}'


# MPP offline ('re') backend: per-worker install Context (loads LEVELSETS + mesh
# cache once per process, reused across that worker's layouts), then numpy-vectorized
# compile_mpp. Output is byte-identical to the serial path — parallelism is pure
# wall-clock. Below this many layouts, serial wins (avoids N×Context build cost).
_MP_MIN_MPP_JOBS = 16
# pack_mod compresses blocks with a thread pool (zlib drops the GIL); below this
# many compressible blocks the thread overhead isn't worth it -> serial.
_MP_MIN_PACK_BLOCKS = 64
# RAW: the 3 heavy builders (UNITDATA/AFFIXES/SKILLS) share one process pool when
# the mod carries at least this many UNITS/AFFIXES/SKILLS .DATs (else spawn cost
# isn't worth it -> serial). Output is byte-identical either way.
_MP_MIN_RAW_ITEMS = 3000
_MPP_CTX = None


def _mpp_init(base_install):
    global _MPP_CTX
    from .mpp.pipeline import Context
    _MPP_CTX = Context(base_install)


def _mpp_job(lp):
    """Process-pool worker: returns (layout_path, mpp-bytes-or-None)."""
    from .mpp import compile_mpp
    try:
        return lp, compile_mpp(lp, ctx=_MPP_CTX)
    except Exception:
        return lp, None


# DAT->BINDAT compile. Each file uses per-file HASH string-ids (compile_dat with
# no sdict — see bindat.HashStringDict): the game resolves a BINDAT's ids through
# THAT file's own table (model A, proven), so no global intern counter / corpus
# dict / shared state is needed. That makes compilation embarrassingly parallel
# AND deterministic (serial and pooled outputs are identical). Below this many
# DATs the pool spawn isn't worth it -> serial.
_MP_MIN_BINDAT_JOBS = 1500


def _bindat_compile_job(job):
    """Process-pool worker: compile a DAT with per-file hash ids (no shared
    state). Returns (bindat_path, bytes-or-None, error-or-None)."""
    dp, bp = job
    from .bindat import compile_dat
    try:
        return bp, compile_dat(dp), None
    except Exception as e:
        return bp, None, f'{dp}: {e}'


def _compile_bindat_serial(dat_jobs, media_dir, overrides, results):
    for dp, bp in dat_jobs:
        try:
            gen = compile_dat(dp)
            if gen is not None:
                _emit_converted(bp, gen, media_dir, overrides)
                results['bindat'] += 1
        except Exception as e:
            results['errors'].append(f'BINDAT {dp}: {e}')


def _compile_bindat_parallel(dat_jobs, media_dir, overrides, results):
    """Single-pass parallel DAT->BINDAT (byte-identical to the serial form, since
    each file's hash ids are self-contained)."""
    nproc = min(8, os.cpu_count() or 1)
    with ProcessPoolExecutor(max_workers=nproc) as ex:
        for bp, gen, err in ex.map(_bindat_compile_job, dat_jobs, chunksize=64):
            if err:
                results['errors'].append(f'BINDAT {err}')
            elif gen is not None:
                _emit_converted(bp, gen, media_dir, overrides)
                results['bindat'] += 1

# ── MOD.DAT reader ──

def read_mod_metadata(mod_dir):
    """Read MOD.DAT to get mod name and metadata."""
    mod_dat = os.path.join(mod_dir, 'MOD.DAT')
    if not os.path.exists(mod_dat):
        return {'name': os.path.basename(mod_dir), 'title': os.path.basename(mod_dir)}
    
    with open(mod_dat, 'r', encoding='utf-16-le') as f:
        text = f.read()
    
    meta = {}
    for key in ['MOD_FILE_NAME', 'DISPLAYNAME', 'MOD_TITLE', 'AUTHOR']:
        m = re.search(rf'<STRING>{key}:([^\r\n]+)', text)
        if m:
            meta[key.lower()] = m.group(1).strip()
    
    meta['name'] = meta.get('mod_file_name', os.path.basename(mod_dir))
    meta['title'] = meta.get('displayname', meta.get('mod_title', meta['name']))
    return meta


# ── Converter runner ──

def _emit_converted(path, data, media_dir, overrides):
    """Persist a converted file: write to disk, or — when `overrides` is a dict —
    stash the bytes in memory keyed by UPPER rel path (so the caller can pack
    straight from memory without copying MEDIA to a scratch dir)."""
    if overrides is not None:
        rel = os.path.relpath(path, media_dir).replace('\\', '/').upper()
        overrides[rel] = data
    else:
        with open(path, 'wb') as fh:
            fh.write(data)


def convert_all(media_dir, overrides=None, mpp='re', raw='auto'):
    """Run all conversions on MEDIA directory.

    If `overrides` is a dict, converted bytes are collected there (keyed by
    UPPER rel path) instead of written to media_dir, leaving the source MEDIA
    untouched and letting pack_mod build the .MOD from memory — no temp copy.

    `mpp` selects the .MPP pathing-grid backend run after the RAW step:
      're'           offline generator (mpp/; needs numpy; ~91-99% of cells match) — DEFAULT.
                     Robust: pure offline, no editor dependency, never crashes. Cell
                     accuracy (~91-99%) is plenty for walkability — the player can move;
                     only byte-fidelity vs the game is sacrificed, which doesn't matter
                     for gameplay. This is the safe default for personal modding.
      'dll'          BYTE-EXACT via the real EditorGuts.dll (mpp/dll.py). The only
                     backend matching the game byte-for-byte, BUT it drives the real
                     editor which renders to compute pathing → can hit the D3D9/NVIDIA
                     crash mid-run and (because its 2-pass --twice leaves pass-1 STUB
                     .mpp behind) silently emit empty 50x50 all-blocked stubs → maps
                     become unwalkable. Use only when byte-fidelity is required and the
                     editor env is known-good.
      None / 'skip'  do not generate any .MPP (keep the source's existing .MPP).

    `raw` controls the 7 RAW index files (AFFIXES/SKILLS/MISSILES/TRIGGERABLES/
    UNITDATA/UI/ROOMPIECES), step 3:
      'auto'         ON-DEMAND (default): each builder indexes the mod's own
                     MEDIA/<TYPE>/ source and returns None when that subdir is
                     absent, so a RAW is emitted only for the content types this
                     mod actually carries. A mod that touches none of them emits 0
                     RAW (RAW is a FULL index — a mod that does not ship the type's
                     source should not overwrite the base game's RAW).
      None/'none'/'skip'  skip the RAW step entirely."""
    results = {'bindat': 0, 'binlayout': 0, 'raw': 0, 'mpp': 0, 'errors': []}

    # Single directory walk: collect DAT/LAYOUT jobs that have an existing
    # template, and detect whether any BINDAT exists (gates the hash DB build).
    dat_jobs = []      # (dat_path, bindat_path)
    layout_jobs = []   # (layout_path, binlayout_path)
    for root, dirs, files in os.walk(media_dir):
        # Case-insensitive: GUTS source files may be .dat/.layout in any case,
        # and templates are matched on a case-folded set (Windows FS is
        # case-insensitive, so open() with either case works).
        upper = {f.upper() for f in files}
        for f in files:
            fu = f.upper()
            if fu.endswith('.DAT') and '.BIN' not in fu:
                # Real compiler: a sibling .BINDAT template is NOT required — the
                # binary is serialized from scratch from the .DAT text.
                dat_jobs.append((os.path.join(root, f), os.path.join(root, f + '.BINDAT')))
            elif fu.endswith('.LAYOUT'):
                if fu + '.BINLAYOUT' in upper:
                    layout_jobs.append((os.path.join(root, f), os.path.join(root, f + '.BINLAYOUT')))

    # 1. DAT → BINDAT (compiled from scratch; reads no existing .BINDAT). Big mods
    #    use the two-pass parallel compiler (byte-identical, collision-free); small
    #    ones stay serial. On any pool failure -> serial fallback (idempotent).
    print("  Converting DAT→BINDAT...")
    if len(dat_jobs) >= _MP_MIN_BINDAT_JOBS:
        try:
            _compile_bindat_parallel(dat_jobs, media_dir, overrides, results)
        except Exception:
            results['bindat'] = 0
            _compile_bindat_serial(dat_jobs, media_dir, overrides, results)
    elif dat_jobs:
        _compile_bindat_serial(dat_jobs, media_dir, overrides, results)

    # 2. LAYOUT → BINLAYOUT (parallel when there are enough jobs)
    print("  Converting LAYOUT→BINLAYOUT...")
    layout_out = None
    if len(layout_jobs) >= _MP_MIN_LAYOUT_JOBS:
        try:
            with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as ex:
                layout_out = list(ex.map(_layout_job, layout_jobs, chunksize=4))
        except Exception:
            layout_out = None  # any pool failure → fall back to serial below
    if layout_out is None:
        layout_out = [_layout_job(j) for j in layout_jobs]
    for bp, gen, err in layout_out:
        if err is not None:
            results['errors'].append(f'BINLAYOUT {err}')
        elif gen is not None:
            _emit_converted(bp, gen, media_dir, overrides)
            results['binlayout'] += 1

    # 3. RAW file generation (ON-DEMAND: generate_raw_files' builders each skip a
    # type whose source subdir is absent, so only the content types this mod
    # carries emit a RAW; raw='none' skips the whole step).
    if raw not in (None, 'none', 'skip'):
        print("  Generating RAW files (on-demand per content type)...")
        results['raw'] = generate_raw_files(media_dir, overrides)
    else:
        print("  Skipping RAW generation (raw=none).")

    # 4. MPP pathing-grid generation (optional; lazy-imports the mpp subpackage)
    if mpp not in (None, 'skip', 'none'):
        print(f"  Generating MPP files (backend={mpp})...")
        try:
            results['mpp'] = generate_mpp_files(media_dir, overrides, backend=mpp)
        except RuntimeError as e:
            # DLL backend unavailable (no editor/console) or build failed: fall back
            # to the offline approximate generator so packing still succeeds — with a
            # clear warning that the .mpp is then APPROXIMATE, not native-byte-exact.
            if mpp == 'dll':
                print(f"  WARNING: byte-exact DLL MPP backend unavailable ({e});\n"
                      f"           falling back to APPROXIMATE offline MPP — output "
                      f"will NOT match the game byte-for-byte.")
                try:
                    results['mpp'] = generate_mpp_files(media_dir, overrides, backend='re')
                except Exception as e2:
                    results['errors'].append(f'MPP: {e2}')
            else:
                results['errors'].append(f'MPP: {e}')
        except Exception as e:
            results['errors'].append(f'MPP: {e}')

    return results


# ── RAW generator ──

def generate_raw_files(media_dir, overrides=None):
    """Generate RAW index files via the rg_raw builders (ported from TL2Lib).

    Byte-verified vs GUTS: AFFIXES, SKILLS, TRIGGERABLES, MISSILES, UNITDATA, UI.
    UNITDATA reproduces shipped MEDIA/UNITDATA.RAW byte-for-byte (full BASEFILE
    inheritance + interleaved scan order); UI reproduces shipped MEDIA/UI.RAW
    byte-for-byte — GUTS's writer (EditorGuts sub_103178E0) only indexes layouts
    whose [OBJECTS] contain a `DESCRIPTOR: Menu Definition` object (109 of 171
    .LAYOUTs), keyed off that object's MENU NAME / DO NOT CREATE props.
    ROOMPIECES follows the reference (no LEVELSETS test mod available to verify).

    If `overrides` is a dict, bytes are stored there (keyed by UPPER name)
    instead of written to media_dir.

    The three heavy builders (UNITDATA/AFFIXES/SKILLS — UNITDATA's BASEFILE-chain
    resolution dominates RAW time on unit-heavy mods) share ONE process pool when
    the mod is large enough (>= _MP_MIN_RAW_ITEMS source .DATs); each is an
    order-preserving per-DAT map, so the pooled output is byte-identical to the
    serial path. On any pool failure it falls back to serial (idempotent)."""
    if _raw_heavy_count(media_dir, _MP_MIN_RAW_ITEMS) >= _MP_MIN_RAW_ITEMS:
        try:
            # THREADS, not processes: the heavy builders are read-bound (tiny
            # UTF-16 DATs), so GIL-dropping I/O parallelizes with zero IPC and a
            # shared UNITDATA attr cache. See rg_raw build_*_parallel.
            with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 1)) as ex:
                return _run_raw_builders(media_dir, overrides, ex)
        except Exception:
            pass   # pool unavailable -> serial fallback (re-emits are idempotent)
    return _run_raw_builders(media_dir, overrides, None)


def _emit_raw(raw_name, data, media_dir, overrides):
    """Write one RAW (to `overrides` dict or disk); return 1 if emitted, else 0."""
    if not data:
        return 0
    if overrides is not None:
        overrides[raw_name.upper()] = data
    else:
        with open(os.path.join(media_dir, raw_name), 'wb') as f:
            f.write(data)
    return 1


def _run_raw_builders(media_dir, overrides, ex):
    """Run every RAW builder (the 3 heavy ones pooled via `ex` when non-None) and
    emit each. Builder ORDER mirrors the original serial sequence."""
    skills = rg_raw.build_skills_parallel(media_dir, ex) if ex else rg_raw.build_skills(media_dir)
    affixes = rg_raw.build_affixes_parallel(media_dir, ex) if ex else rg_raw.build_affixes(media_dir)
    unitdata = rg_raw.build_unitdata_parallel(media_dir, ex) if ex else rg_raw.build_unitdata(media_dir)
    count = 0
    count += _emit_raw('ROOMPIECES.RAW', rg_raw.build_roompieces(media_dir), media_dir, overrides)
    count += _emit_raw('SKILLS.RAW', skills, media_dir, overrides)
    count += _emit_raw('MISSILES.RAW', rg_raw.build_missiles(media_dir), media_dir, overrides)
    count += _emit_raw('AFFIXES.RAW', affixes, media_dir, overrides)
    count += _emit_raw('TRIGGERABLES.RAW', rg_raw.build_triggerables(media_dir), media_dir, overrides)
    count += _emit_raw('UNITDATA.RAW', unitdata, media_dir, overrides)
    count += _emit_raw('UI.RAW', rg_raw.build_ui(media_dir), media_dir, overrides)
    return count


def _raw_heavy_count(media_dir, cap):
    """Count source .DATs under UNITS/AFFIXES/SKILLS, stopping early at `cap`
    (the gate only needs to know whether the pool is worth spawning)."""
    n = 0
    for sub in ('UNITS', 'AFFIXES', 'SKILLS'):
        root = os.path.join(media_dir, sub)
        if not os.path.isdir(root):
            continue
        for _r, _d, files in os.walk(root):
            for f in files:
                fu = f.upper()
                if fu.endswith('.DAT') and '.BIN' not in fu:
                    n += 1
                    if n >= cap:
                        return n
    return n


# ── MPP generator ──

def generate_mpp_files(media_dir, overrides=None, backend='re', install_dir=None):
    """Generate .MPP pathing grids for the mod's layouts.

    backend='re'  : OFFLINE approximate generator — walk MEDIA/LAYOUTS/**/*.LAYOUT,
                    compile each to its sibling <layout>.mpp via mpp.compile_mpp,
                    emit through _emit_converted (respects `overrides`). Returns the
                    count of .mpp files emitted. Room-piece collision geometry comes
                    from the BASE install, so compile_mpp's Context points at the
                    install (install_dir or TL2_MEDIA_DIR), not at this mod's MEDIA.
    backend='dll' : BYTE-EXACT — drive the real EditorGuts.dll. `media_dir` here is
                    the mod's MEDIA; its parent is the mod dir handed to the DLL
                    driver. Returns whatever regen_mpp_via_dll returns (dict|int).
    backend in (None,'skip','none') : no-op, returns 0.

    The mpp subpackage (and its numpy dependency) is LAZY-IMPORTED inside this
    function so the BINDAT/BINLAYOUT/RAW core never requires numpy unless MPP is
    actually requested."""
    if backend in (None, 'skip', 'none'):
        return 0

    if backend == 'dll':
        from .mpp.dll import regen_mpp_via_dll
        # the DLL driver operates on the mod dir (containing MOD.DAT + MEDIA/)
        mod_dir = os.path.dirname(os.path.normpath(media_dir))
        if overrides is None:
            # in-place / temp-copy flow: the editor writes .mpp onto disk where
            # pack_mod reads them directly.
            res = regen_mpp_via_dll(mod_dir, install_dir=install_dir)
            if not isinstance(res, dict):
                raise RuntimeError(f"DLL MPP build failed (console exit {res})")
            return res.get('mpp_copied_back', res.get('mpp_count', 0))
        # non-mutating overrides flow: regen on a throwaway copy of the mod and
        # harvest the editor's BYTE-EXACT .mpp into `overrides` (so the source mod
        # is never written). Keyed like _emit_converted: rel-to-MEDIA, '/', UPPER.
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(),
                           f"mikuro_mpp_dll_{os.path.basename(os.path.normpath(mod_dir))}")
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        shutil.copytree(mod_dir, tmp)
        try:
            res = regen_mpp_via_dll(tmp, install_dir=install_dir)
            if not isinstance(res, dict):
                raise RuntimeError(f"DLL MPP build failed (console exit {res})")
            tmp_media = os.path.join(tmp, 'MEDIA')
            n = 0
            for r, _d, fs in os.walk(tmp_media):
                for f in fs:
                    if f.upper().endswith('.MPP'):
                        p = os.path.join(r, f)
                        rel = os.path.relpath(p, tmp_media).replace('\\', '/').upper()
                        overrides[rel] = open(p, 'rb').read()
                        n += 1
            return n
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if backend != 're':
        raise ValueError(f"unknown mpp backend: {backend!r}")

    from .mpp.pipeline import Context
    base_install = install_dir or TL2_MEDIA_DIR
    layouts_dir = os.path.join(media_dir, 'LAYOUTS')
    jobs = [os.path.join(root, f)
            for root, _dirs, files in os.walk(layouts_dir)
            for f in files if f.upper().endswith('.LAYOUT')]
    if not jobs:
        return 0   # no level layouts -> nothing to path; skip the install Context build

    out = None
    if len(jobs) >= _MP_MIN_MPP_JOBS:
        try:
            with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1),
                                     initializer=_mpp_init,
                                     initargs=(base_install,)) as ex:
                out = list(ex.map(_mpp_job, jobs, chunksize=4))
        except Exception:
            out = None  # any pool failure → serial fallback below
    if out is None:
        from .mpp import compile_mpp
        ctx = Context(base_install)   # build once (loads install LEVELSETS), reuse
        out = []
        for lp in jobs:
            try:
                out.append((lp, compile_mpp(lp, ctx=ctx)))
            except Exception:
                out.append((lp, None))

    count = 0
    for lp, data in out:
        if not data:
            continue
        mpp_path = lp[: -len('.LAYOUT')] + '.mpp' if lp.upper().endswith('.LAYOUT') \
            else lp + '.mpp'
        _emit_converted(mpp_path, data, media_dir, overrides)
        count += 1
    return count


# ── MOD packer ──

def find_zlib_offsets(data):
    """Find all zlib magic markers in data."""
    markers = [b'\x78\x9c', b'\x78\xda', b'\x78\x01']
    offsets = []
    pos = 0
    while pos < len(data):
        found = False
        for m in markers:
            idx = data.find(m, pos)
            if idx >= 0:
                offsets.append(idx)
                pos = idx + 1
                found = True
                break
        if not found:
            break
    return offsets


# ── MOD container writer (ported from TL2Lib rgmod/rgman; byte-verified) ──
# Everything below is synthesized FROM SCRATCH — no reference .MOD is consulted.
# The header comes from MOD.DAT (build_header), the manifest tree from a MEDIA
# scan (build_manifest_dirs); pack_mod assembles the PAK + TOC with the byte-exact
# writers _w_header / _w_manifest. All format facts are RE'd from EditorGuts.dll
# (function anchors cited inline); see 开发日志/MOD容器格式逆向-完成报告.md.

# Header constants (EditorGuts sub_103F5DA0 "Compiling Mod").
_MOD_MAGIC = 4                  # word_125EFF4C — container magic / format ver, const.
_MOD_FLAGS = 0                  # this+268 — internal flags; 0 in every shipped .MOD.
# gameVersion (4×u16 from Torchlight2.exe VS_FIXEDFILEINFO via sub_103F8CD0); a
# per-install constant. We read it live from Torchlight2.exe (read_gamever) so it
# tracks the install; this default is the value the 1.25.9.5 install stamps
# (0x0001,0x0019,0x0009,0x0005), used when the exe can't be read. Overridable via
# the TL2_MOD_GAMEVER env var.
_DEFAULT_GAMEVER = 0x0005000900190001


def read_gamever(install_dir=None):
    """gameVersion u64 read from Torchlight2.exe's VS_FIXEDFILEINFO, matching
    EditorGuts sub_103F8CD0 exactly: it takes the 4 version words in the order
    (minor_ms, major_ms, private_ls, build_ls) — i.e. for 1.25.9.5 the bytes are
    0001 0019 0009 0005 → u64 0x0005000900190001. Returns _DEFAULT_GAMEVER if the
    exe / its version resource can't be read (non-Windows, missing file, …)."""
    if install_dir is None:
        # MEDIA dir's parent is the install root; both are siblings of the exe.
        install_dir = os.path.dirname(os.path.normpath(TL2_MEDIA_DIR))
    exe = os.path.join(install_dir, 'Torchlight2.exe')
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return _DEFAULT_GAMEVER
    if not os.path.isfile(exe):
        return _DEFAULT_GAMEVER
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(exe, None)
        if not size:
            return _DEFAULT_GAMEVER
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(exe, 0, size, buf):
            return _DEFAULT_GAMEVER
        # VS_FIXEDFILEINFO via VerQueryValueW("\\"): dwSignature(0xFEEF04BD),
        # dwStrucVersion, dwFileVersionMS, dwFileVersionLS, ...
        lp = ctypes.c_void_p()
        ln = wintypes.UINT()
        if not ver.VerQueryValueW(buf, '\\', ctypes.byref(lp), ctypes.byref(ln)):
            return _DEFAULT_GAMEVER
        ffi = ctypes.cast(lp, ctypes.POINTER(ctypes.c_uint32))
        if ffi[0] != 0xFEEF04BD:               # dwSignature sanity check
            return _DEFAULT_GAMEVER
        ms, ls = ffi[2], ffi[3]                # dwFileVersionMS, dwFileVersionLS
        # VS_FIXEDFILEINFO as u16: w4=ms&0xFFFF, w5=ms>>16, w6=ls&0xFFFF, w7=ls>>16.
        # sub_103F8CD0 emits (a1,a2,a3,a4)=(w5,w4,w7,w6) as 4 consecutive u16, so
        # the u64 (little-endian) is a1 | a2<<16 | a3<<32 | a4<<48. For 1.25.9.5
        # (ms=0x00010019, ls=0x00090005) this yields 0x0005000900190001.
        w4, w5 = ms & 0xFFFF, (ms >> 16) & 0xFFFF
        w6, w7 = ls & 0xFFFF, (ls >> 16) & 0xFFFF
        return w5 | (w4 << 16) | (w7 << 32) | (w6 << 48)
    except Exception:
        return _DEFAULT_GAMEVER

# Extension → manifest TYPE code (EditorGuts sub_102A1EA0 + the compile remap in
# sub_102A24F0). Keys are UPPER extensions WITH the dot. Source files that GUTS
# compiles are stored under their SOURCE name but get the COMPILED file's type:
#   .DAT/.TEMPLATE → BINDAT(0), .LAYOUT → BINLAYOUT(1),
#   .ANIMATION → 16, .HIE → 17  (all four are *.BINDAT/*.BINLAYOUT on disk).
_EXT_TYPE = {
    '.DAT': 0, '.TEMPLATE': 0, '.BINDAT': 0,        # → 0 (BINDAT)
    '.LAYOUT': 1, '.BINLAYOUT': 1,                  # → 1 (BINLAYOUT)
    '.MESH': 2, '.SKELETON': 3, '.DDS': 4, '.PNG': 5,
    '.WAV': 6, '.OGG': 6, '.MATERIAL': 8, '.RAW': 9,
    '.UILAYOUT': 10, '.IMAGESET': 11, '.TTF': 12, '.TTC': 12,
    '.FONT': 13, '.ANIMATION': 16, '.HIE': 17,
    '.SCHEME': 19, '.LOOKNFEEL': 20, '.MPP': 21, '.BIK': 23, '.JPG': 24,
}
_TYPE_DIR = 7        # directory placeholder
_TYPE_UNKNOWN = 18   # sub_102A1EA0 default (extension not matched / too short)

# Store-vs-compress per type = byte_11E94CD8[type] (used in pak writer sub_102A7100:
# `if (byte_11E94CD8[type] && size < 0x1900000)` → compress, else store). The table
# (RE'd by get_bytes @ 0x11E94CD8) is 1 for every type 0..23 and 0 for 24 (.JPG).
# i.e. EVERYTHING is zlib-compressed except .JPG, which is stored uncompressed.
# (Verified empirically: final_fantasy_weapons stores only its 5 .JPGs; a 12k-file
# material mod compresses all PNG/WAV/MPP/ANIMATION/unknown blocks.)
_STORE_TYPES = frozenset({24})


def _ext_type(name_upper):
    """Manifest type code for a file name (UPPER). .BINDAT/.BINLAYOUT names are
    classified by the SOURCE extension they wrap (GUTS stores them under the
    source name), so e.g. FOO.DAT.BINDAT → look up .DAT → 0."""
    # Strip a compiled-binary suffix so FOO.DAT.BINDAT classifies as its .DAT.
    base = name_upper
    for suf in ('.BINDAT', '.BINLAYOUT'):
        if base.endswith(suf):
            base = base[:-len(suf)]
            break
    dot = base.rfind('.')
    if dot < 0:
        return _TYPE_UNKNOWN
    return _EXT_TYPE.get(base[dot:], _TYPE_UNKNOWN)


def _filetime_from_mtime(path):
    """Windows FILETIME (100ns ticks since 1601-01-01 UTC) from a file's mtime,
    matching DateTimeToFileTime in the manifest writer. 0 if the file is gone."""
    try:
        # st_mtime is POSIX seconds (UTC); FILETIME epoch is 1601-01-01.
        secs = os.path.getmtime(path)
    except OSError:
        return 0
    return int(secs * 10_000_000) + 116444736000000000


def _w_ss(s):
    return struct.pack('<H', len(s)) + s.encode('utf-16-le')


def _pak_rolling_hash(data):
    """PAK data-section rolling hash (the 2nd u32 of the 8-byte data header). The
    GAME VALIDATES this at mod-load time — a mismatch makes it silently reject the
    whole mod ("Unable to load mod"), so it MUST be correct, not 0.

    RE'd from the writer (EditorGuts sub_102A7100) and the validating reader
    (sub_102A2690 / sub_103F83C0). The sampling stride is `N / rng(25,75)` where
    rng is the LCG sub_10285B30 — but it is first SEEDED WITH N (the data-section
    length) via sub_10285A50, so the "random" divisor is a deterministic function
    of N and the reader reproduces it exactly:
        divisor = 25 + (695696193*N mod 2^32) mod 51
    Bytes are sampled from offset 8 (skipping the [maxBlock][rollingHash] header)
    at `stride`, folded as h = (signed)byte + 33*h with h seeded to N, plus the
    final byte. Verified byte-exact against 30 shipped / editor-published .MODs."""
    n = len(data)
    if n <= 8:
        return 0
    divisor = 25 + (695696193 * n & 0xFFFFFFFF) % 51    # rng(25,75) seeded by N
    stride = n // divisor
    if stride <= 1:
        stride = 2
    h = n & 0xFFFFFFFF
    k = 8
    while k < n:
        b = data[k]
        h = ((b - 256 if b >= 128 else b) + 33 * h) & 0xFFFFFFFF
        k += stride
    b = data[n - 1]
    return ((b - 256 if b >= 128 else b) + 33 * h) & 0xFFFFFFFF


def _disasm_mod(tdata):
    """Parse a .MOD: returns (header_dict, dirs) where dirs is
    [(dirname, [(crc, type, name, off, size, ftime), ...]), ...]."""
    p = [0]
    def rw(): v = struct.unpack_from('<H', tdata, p[0])[0]; p[0] += 2; return v
    def rd(): v = struct.unpack_from('<I', tdata, p[0])[0]; p[0] += 4; return v
    def rb(): v = tdata[p[0]]; p[0] += 1; return v
    def rq(): v = struct.unpack_from('<Q', tdata, p[0])[0]; p[0] += 8; return v
    def rss(): n = rw(); s = tdata[p[0]:p[0]+n*2].decode('utf-16-le'); p[0] += n*2; return s
    h = dict(ver=rw(), modver=rw(), gamever=rq(), offData=rd(), offMan=rd(),
             title=rss(), author=rss(), descr=rss(), website=rss(), download=rss(),
             modid=rq(), flags=rd(), reqHash=rq())
    h['reqs'] = [(rss(), rq(), rw()) for _ in range(rw())]
    h['dels'] = [rss() for _ in range(rw())]
    p[0] = h['offMan']
    mver = rw(); h['mhash'] = rd() if mver >= 2 else 0; h['root'] = rss()
    h['fc'] = rd(); dc = rd()
    dirs = []
    for _ in range(dc):
        dname = rss(); cnt = rd()
        dirs.append((dname, [(rd(), rb(), rss(), rd(), rd(), rq()) for _ in range(cnt)]))
    return h, dirs


def _w_header(h, off_data, off_man):
    out = struct.pack('<HHQII', h['ver'], h['modver'], h['gamever'], off_data, off_man)
    out += (_w_ss(h['title']) + _w_ss(h['author']) + _w_ss(h['descr'])
            + _w_ss(h['website']) + _w_ss(h['download']))
    out += struct.pack('<QIQ', h['modid'], h['flags'], h['reqHash'])
    out += struct.pack('<H', len(h['reqs']))
    for (n, i, v) in h['reqs']:
        out += _w_ss(n) + struct.pack('<QH', i, v)
    out += struct.pack('<H', len(h['dels']))
    for d in h['dels']:
        out += _w_ss(d)
    return out


def _w_manifest(h, dirs):
    # Accumulate into a LIST + b''.join, NOT `out += ...` on bytes: `bytes` is
    # immutable so `+=` copies the whole buffer each iteration -> O(n^2). On a 44k-
    # record manifest that was ~16.5s; the list form is O(n) (~0.1s).
    parts = [struct.pack('<HI', 2, h['mhash']), _w_ss(h['root']),
             struct.pack('<II', h['fc'], len(dirs))]
    for (dname, recs) in dirs:
        parts.append(_w_ss(dname))
        parts.append(struct.pack('<I', len(recs)))
        for (crc, typ, name, off, size, ft) in recs:
            parts.append(struct.pack('<IB', crc, typ) + _w_ss(name)
                         + struct.pack('<IIQ', off, size, ft))
    return b''.join(parts)


def _parse_mod_dat(mod_dir):
    """Parse MOD.DAT into a flat dict of UPPER field → value plus the structured
    REQUIRED_MODS / REMOVE_FILES lists. UTF-16-LE; <TYPE>KEY:VALUE lines, with
    [block]...[/block] nesting (REQUIRED_MODS holds child mod blocks)."""
    path = os.path.join(mod_dir, 'MOD.DAT')
    fields, reqs, dels = {}, [], []
    if not os.path.exists(path):
        return fields, reqs, dels
    with open(path, 'rb') as fh:
        raw = fh.read()
    # MOD.DAT is UTF-16-LE (BOM optional); fall back to utf-8 if it isn't.
    try:
        text = raw.decode('utf-16-le')
    except UnicodeDecodeError:
        text = raw.decode('utf-8', 'replace')
    text = text.lstrip('﻿')

    # Top-level scalar fields (first occurrence wins; case-insensitive key).
    for m in re.finditer(r'<[^>]+>([A-Za-z0-9_]+)\s*:([^\r\n]*)', text):
        key, val = m.group(1).upper(), m.group(2).strip()
        fields.setdefault(key, val)

    # REQUIRED_MODS: a block whose children each carry NAME/MOD_ID/VERSION.
    rm = re.search(r'\[REQUIRED_MODS\](.*?)\[/REQUIRED_MODS\]', text,
                   re.IGNORECASE | re.DOTALL)
    if rm:
        body = rm.group(1)
        for blk in re.split(r'(?=\[[A-Za-z0-9_]+\])', body):
            nm = re.search(r'<[^>]+>NAME\s*:([^\r\n]*)', blk, re.IGNORECASE)
            gid = re.search(r'<[^>]+>(?:MOD_ID|GUID|ID)\s*:\s*(-?\d+)', blk, re.IGNORECASE)
            ver = re.search(r'<[^>]+>VERSION\s*:\s*(-?\d+)', blk, re.IGNORECASE)
            if gid:
                reqs.append((nm.group(1).strip() if nm else '',
                             int(gid.group(1)) & 0xFFFFFFFFFFFFFFFF,
                             (int(ver.group(1)) if ver else 0) & 0xFFFF))

    # REMOVE_FILES: a block of <STRING>...:path entries (the path is the value).
    rf = re.search(r'\[REMOVE_FILES\](.*?)\[/REMOVE_FILES\]', text,
                   re.IGNORECASE | re.DOTALL)
    if rf:
        for m in re.finditer(r'<STRING>[^:]*:([^\r\n]*)', rf.group(1)):
            v = m.group(1).strip()
            if v:
                dels.append(v)
    return fields, reqs, dels


def build_header(mod_dir, gamever=None):
    """Synthesize the .MOD mod-info header dict (keys consumed by _w_header) from
    MOD.DAT — no reference .MOD needed. Field→slot mapping RE'd from the MOD.DAT
    reader (sub_103FA610) and the header writer (sub_103F5DA0):

        NAME → title (this+40)      AUTHOR → author (this+68)
        DESCRIPTION → descr (+152)  WEBSITE → website (+96)
        DOWNLOAD_URL → download (+124)
        MOD_ID → modid (+240)       VERSION → modver (+256)
        REQUIRED_MODS → reqs        REMOVE_FILES → dels
    (MOD_FILE_NAME is the output filename, NOT a header field.)

    modver = VERSION + 1: sub_103F5DA0 does `++*(this+256)` on the publish path,
    so a published .MOD's modver is one past its MOD.DAT VERSION (COMMANDMENTS
    VERSION:10 → modver 11; MIKURO VERSION:6 → modver 7).

    reqHash = recursive hash of REQUIRED_MODS (sub_103F5500); 0 when there are no
    required mods — the common case, and all we can reproduce offline. gamever is
    a per-install constant (sub_103F8CD0 reads Torchlight2.exe); use the passed /
    env value, else _DEFAULT_GAMEVER. ver(magic) and flags are constants."""
    fields, reqs, dels = _parse_mod_dat(mod_dir)

    def _i(key, default=0):
        v = fields.get(key)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    if gamever is None:
        env = os.environ.get('TL2_MOD_GAMEVER')
        gamever = int(env, 0) if env else read_gamever()

    return dict(
        ver=_MOD_MAGIC,
        modver=(_i('VERSION', 0) + 1) & 0xFFFF,
        gamever=gamever,
        title=fields.get('NAME', os.path.basename(mod_dir)),
        author=fields.get('AUTHOR', ''),
        descr=fields.get('DESCRIPTION', ''),
        website=fields.get('WEBSITE', ''),
        download=fields.get('DOWNLOAD_URL', ''),
        modid=_i('MOD_ID', 0) & 0xFFFFFFFFFFFFFFFF,
        flags=_MOD_FLAGS,
        # reqHash = recursive hash of REQUIRED_MODS (sub_103F5500); 0 when there
        # are no reqs (the common case). We don't reproduce the non-empty hash
        # offline, so reqs!=[] would leave it 0 too — acceptable (it gates a
        # dependency-staleness warning, not loading), but documented as a gap.
        reqHash=0,
        reqs=reqs,
        dels=dels,
        # Manifest fields: hash is an unvalidatable random-stride fingerprint
        # (sub_102A5860 → sub_10286420(15,25)); 0 is accepted by the game. root
        # and fc are filled by build_manifest_dirs / pack_mod.
        mhash=0,
        root='MEDIA/',
        fc=0,
    )


def _collect_media_files(media_dir, overrides=None):
    """Recursive MEDIA scan → list of (rel_path_with_MEDIA_prefix, manifest_name,
    type_code, ftime), in FindFirstFileW name-interleaved DFS order (the order
    GUTS' sub_103F50D0 collects). Applies the PNG→DDS dedup (drop a .PNG when a
    sibling .DDS exists). `overrides` (UPPER rel→bytes, e.g. RAW/BINDAT built in
    memory) is unioned in so generated files appear even if not on disk.

    The .BINDAT/.BINLAYOUT compiled outputs are NOT listed separately: GUTS stores
    them under the SOURCE name (FOO.DAT, FOO.LAYOUT). So a source .DAT/.LAYOUT/
    .TEMPLATE/.ANIMATION/.HIE yields ONE entry, named for the source, typed for
    the compiled form (handled by _ext_type)."""
    files = []        # (rel_upper_with_media, manifest_name, type, ftime)
    seen = set()      # rel_upper keys already emitted

    def _walk(disk_dir, rel_prefix):
        # FindFirstFileW returns entries sorted by name, files and subdirs
        # interleaved; replicate with a single sorted listing. os.scandir (not
        # listdir + per-file os.path.isdir/getmtime/exists) returns is_dir + stat
        # cached from the ONE directory read — on Windows those DirEntry methods
        # cost no extra syscall, so this is the difference between ~15s and ~1s of
        # manifest build on a 68k-file mod (tens of thousands of stat() calls).
        try:
            with os.scandir(disk_dir) as it:
                entries = sorted(it, key=lambda e: e.name.upper())
        except OSError:
            return
        names_u = {e.name.upper() for e in entries}   # for PNG→DDS dedup, no stat
        for e in entries:
            nm = e.name
            rel = rel_prefix + nm
            relu = rel.upper()
            if e.is_dir():
                _walk(e.path, rel + '/')
                continue
            nmu = nm.upper()
            # Skip compiled outputs — they ride under the source name.
            if nmu.endswith('.BINDAT') or nmu.endswith('.BINLAYOUT'):
                continue
            # PNG→DDS dedup: drop the PNG if a sibling DDS exists (same dir OR in
            # overrides) — GUTS prefers the DDS.
            if nmu.endswith('.PNG'):
                dds_ov = relu[6:-4] + '.DDS'        # override key (no MEDIA/ prefix)
                if (nmu[:-4] + '.DDS') in names_u or (overrides and dds_ov in overrides):
                    continue
            seen.add(relu)
            try:
                ft = int(e.stat().st_mtime * 10_000_000) + 116444736000000000
            except OSError:
                ft = 0
            # Store the UPPERCASED name: GUTS uppercases every manifest filename
            # (sub_103F50D0), and the game's PAK lookup uppercases the query key
            # and matches it against the stored name AS-IS. A lowercase-on-disk
            # name (e.g. QLJX_F.dds) stored verbatim never matches the uppercased
            # query "QLJX_F.DDS" -> the resource (here a class-icon texture
            # referenced by an .imageset) silently fails to resolve. str.upper()
            # matches GUTS: ASCII upper, CJK/non-ASCII unchanged.
            files.append((relu, nmu, _ext_type(nmu), ft))

    media_norm = os.path.normpath(media_dir)
    _walk(media_norm, 'MEDIA/')

    # Generated-in-memory files (RAW / BINDAT / BINLAYOUT) that aren't on disk:
    # overrides is keyed by UPPER rel path WITHOUT the MEDIA/ prefix. RAW indices
    # (FOO.RAW) live at MEDIA root; compiled BINDAT/BINLAYOUT ride under their
    # source name (already on disk), so only add files we haven't already seen.
    if overrides:
        for key in overrides:
            ku = key.upper()
            # Map override key → the manifest source name. A '<src>.BINDAT' /
            # '.BINLAYOUT' override is the compiled form of an on-disk source,
            # already listed; skip. Bare names (e.g. *.RAW) are new root files.
            if ku.endswith('.BINDAT') or ku.endswith('.BINLAYOUT'):
                continue
            relu = 'MEDIA/' + ku
            if relu in seen:
                continue
            seen.add(relu)
            name = ku.rsplit('/', 1)[-1]
            files.append((relu, name, _ext_type(ku), 0))

    return files


def build_manifest_dirs(media_dir, overrides=None):
    """Synthesize the manifest dir-tree `dirs` (the structure _w_manifest writes)
    from a MEDIA scan — no reference .MOD needed. Returns
        (dirs, file_count)
    where dirs = [(dirname, [(crc, type, name, off, size, ftime), ...]), ...].
    crc/off/size are 0 here (filled during data assembly in pack_mod); type and
    ftime are final.

    Grouping mirrors the manifest writer (sub_102A5860), which keys each file by
    its parent dir into a std::map<wstring, files> (so dirs come out sorted by
    UTF-16 path) and inserts a type-7 placeholder for every directory under its
    parent. Layout:
      DIR[0]  name=''        → one type-7 child 'MEDIA/'   (the unnamed root)
      DIR[1]  name='MEDIA/'  → root-level files + type-7 children for subdirs
      …       name='MEDIA/SUB/…/' (sorted) → that dir's files + child subdir
                                              placeholders
    file_count = the literal total record count (files + dir placeholders). GUTS'
    own FileCount field is an inflated capacity hint (it counts the pre-tree
    collection incl. on-disk .BINDAT/.BINLAYOUT siblings); the loader (TL2Lib
    rgman.pas Parse) iterates DirCount + per-dir counts and never uses FileCount
    to bound iteration, so the literal count loads identically."""
    files = _collect_media_files(media_dir, overrides)

    # dir path → list of file records (crc/off/size filled later).
    dir_files = {}        # 'MEDIA/SUB/' → [(crc,type,name,off,size,ft), ...]
    # dir path → ordered set of immediate child SUBDIR leaf names (with '/').
    dir_subdirs = {}      # 'MEDIA/' → ['SUB1/', 'SUB2/', ...]
    all_dirs = set()      # every dir path that must exist as a node

    def _ensure_dir(dpath):
        if dpath in all_dirs:
            return
        all_dirs.add(dpath)
        dir_files.setdefault(dpath, [])
        dir_subdirs.setdefault(dpath, [])
        # register this dir as a child placeholder under its parent, and recurse
        # so every ancestor exists. Root 'MEDIA/' is registered under '' below.
        if dpath == 'MEDIA/':
            return
        parent = dpath[:-1].rsplit('/', 1)[0] + '/'   # 'MEDIA/A/B/' → 'MEDIA/A/'
        _ensure_dir(parent)
        leaf = dpath[len(parent):]                    # 'B/'
        if leaf not in dir_subdirs[parent]:
            dir_subdirs[parent].append(leaf)

    _ensure_dir('MEDIA/')
    for relu, name, typ, ft in files:
        dpath = relu.rsplit('/', 1)[0] + '/'          # parent dir incl trailing '/'
        _ensure_dir(dpath)
        dir_files[dpath].append((0, typ, name, 0, 0, ft))

    # Emit dirs sorted by UTF-16/codepoint path order (the rb-tree iteration in
    # sub_102A5860). Each dir's records = its files (scan order) followed by its
    # immediate child-subdir placeholders (type 7). GUTS appends the subdir
    # placeholders after the files (the LABEL_36 ancestor loop); keep child
    # placeholders sorted for determinism.
    dirs = [('', [(0, _TYPE_DIR, 'MEDIA/', 0, 0, 0)])]
    file_count = 1                                    # the 'MEDIA/' placeholder
    for dpath in sorted(all_dirs):
        recs = list(dir_files[dpath])
        for leaf in sorted(dir_subdirs[dpath]):
            recs.append((0, _TYPE_DIR, leaf, 0, 0, 0))
        dirs.append((dpath, recs))
        file_count += len(recs)

    return dirs, file_count


def _content_for(rel_upper, media_dir, overrides):
    """Bytes packed for a manifest entry whose path (UPPER, no MEDIA/ prefix) is
    `rel_upper`. Prefers the compiled form for compilable sources (BINDAT for
    .DAT/.TEMPLATE/.ANIMATION/.HIE, BINLAYOUT for .LAYOUT), from `overrides` first
    then disk; otherwise the raw file. None if nothing is found."""
    cands = []
    if rel_upper.endswith(('.DAT', '.TEMPLATE', '.ANIMATION', '.HIE')):
        cands.append(rel_upper + '.BINDAT')
    elif rel_upper.endswith('.LAYOUT'):
        cands.append(rel_upper + '.BINLAYOUT')
    cands.append(rel_upper)
    if overrides:
        for c in cands:
            if c in overrides:
                return overrides[c]
    for c in cands:
        disk = os.path.join(media_dir, c.replace('/', os.sep))
        if os.path.isfile(disk):
            with open(disk, 'rb') as fh:
                return fh.read()
    return None


def pack_mod(media_dir, output_path, mod_name, original_mod_dir=None, overrides=None):
    """Build a .MOD entirely FROM SCRATCH — no reference .MOD is used.

    Synthesizes the mod-info header from MOD.DAT (build_header) and the manifest
    dir-tree from a MEDIA scan (build_manifest_dirs), then assembles the PAK data
    section (per file: [decomp:u32][csz:u32][stream]; csz=0 = stored) and writes
    header + data + manifest via the byte-verified writers. Container format,
    type codes and the store/compress rule are RE'd from EditorGuts (sub_103F5DA0
    / sub_102A7100 / sub_102A5860 / sub_102A1EA0 / byte_11E94CD8).

    `original_mod_dir` is the mod dir (containing MOD.DAT); it is used only to
    read MOD.DAT for the header — it no longer needs to contain a .MOD. If omitted
    it defaults to the parent of media_dir. `overrides` (UPPER rel→bytes) supplies
    in-memory conversions (RAW/BINDAT/BINLAYOUT); when absent, content is read
    from disk. The PAK rolling-hash IS validated by the game and is computed over
    the assembled data section (_pak_rolling_hash) — emitting 0 makes the game
    silently reject the mod. The manifest TOC hashValue (mhash) is NOT validated
    (the reader reads but never checks it), so it stays 0 (see build_header)."""
    mod_dir = original_mod_dir or os.path.dirname(os.path.normpath(media_dir))

    h = build_header(mod_dir)
    dirs, file_count = build_manifest_dirs(media_dir, overrides)
    h['fc'] = file_count

    # Data section: 8-byte PAK header placeholder + one block per non-dir file,
    # in manifest (dir-sorted) order. Records carry their content's crc/off/size.
    #
    # The per-block zlib.compress + crc32 is the heavy step; zlib RELEASES the GIL,
    # so we parallelize it with a THREAD pool (no pickling — threads share the big
    # `overrides`/content in memory). Pass A resolves content in order, Pass B
    # compresses concurrently, Pass C assembles `data` strictly in manifest order
    # (offsets depend on cumulative position). Output is byte-identical to the old
    # serial loop (same order, deterministic compress/crc).

    # Pass A: resolve every record to a placeholder or a content block, in order.
    plan = []        # [(dname, [item, ...])]; item = placeholder rec OR a block dict
    blocks = []      # flat list of block dicts needing compress/crc (refs into plan)
    for dname, recs in dirs:
        items = []
        for (crc, typ, name, off, size, ft) in recs:
            if typ == _TYPE_DIR:
                items.append((0, typ, name, 0, 0, ft))
                continue
            full_upper = (dname + name).upper()
            rel_upper = full_upper[6:] if full_upper.startswith('MEDIA/') else full_upper
            content = _content_for(rel_upper, media_dir, overrides)
            if content is None:
                # Missing source (shouldn't happen for scanned files); keep a
                # zero-length, zero-offset entry so the manifest still parses.
                items.append((0, typ, name, 0, 0, ft))
                continue
            # Store vs compress per byte_11E94CD8[type]: store only .JPG (24), and
            # only-store also when too big for GUTS' compress buffer (>= 0x1900000).
            blk = {"typ": typ, "name": name, "ft": ft, "content": content,
                   "size": len(content),
                   "store": typ in _STORE_TYPES or len(content) >= 0x1900000}
            items.append(blk)
            blocks.append(blk)
        plan.append((dname, items))

    # Pass B: compress + crc concurrently (zlib drops the GIL; level 6 == GUTS).
    def _compress_block(blk):
        content = blk["content"]
        if blk["store"]:
            blk["comp"], blk["csz"] = content, 0
        else:
            comp = _COMP.compress(content, _COMP_LEVEL)
            blk["comp"], blk["csz"] = comp, len(comp)
        blk["crc"] = _COMP.crc32(content) & 0xffffffff
        blk["content"] = None        # free the raw bytes once compressed
    if len(blocks) >= _MP_MIN_PACK_BLOCKS:
        # zlib releases the GIL, so use ALL cores — Pack is the last stage (no
        # other pool runs concurrently). Measured ~1.43x vs the old cap of 8 on a
        # 16-core box, with byte-identical output.
        with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 1)) as ex:
            list(ex.map(_compress_block, blocks, chunksize=8))
    else:
        for blk in blocks:
            _compress_block(blk)

    # Pass C: assemble `data` strictly in manifest order; build the records.
    data = bytearray(8)              # [maxCompressedBlockSize][rollingHash], patched
    max_csz = 0
    new_dirs = []
    for dname, items in plan:
        nr = []
        for it in items:
            if isinstance(it, tuple):       # placeholder (dir / missing)
                nr.append(it)
                continue
            off = len(data)
            data += struct.pack('<II', it["size"], it["csz"]) + it["comp"]
            if it["csz"] > max_csz:
                max_csz = it["csz"]
            nr.append((it["crc"], it["typ"], it["name"], off, it["size"], it["ft"]))
        new_dirs.append((dname, nr))

    # maxCompressedBlockSize feeds the game's decompress read-buffer sizing, so
    # set it to the largest compressed block. rollingHash is sampled from offset 8
    # onward (it ignores these first 8 bytes), and the GAME VALIDATES it at load
    # time — so compute it over the assembled data section, else the mod is
    # silently rejected ("Unable to load mod"). See _pak_rolling_hash.
    struct.pack_into('<I', data, 0, max_csz)
    struct.pack_into('<I', data, 4, _pak_rolling_hash(data))

    off_data = len(_w_header(h, 0, 0))               # header is fixed-length given h
    off_man = off_data + len(data)
    out = _w_header(h, off_data, off_man) + bytes(data) + _w_manifest(h, new_dirs)
    with open(output_path, 'wb') as fo:
        fo.write(out)
    return len(out)


# ── Main ──

def _parse_mpp_flag(argv):
    """Extract --mpp {re,dll,none} from argv, returning (backend, remaining_argv).
    Supports both `--mpp re` and `--mpp=re`; default 're' (our own offline generator —
    robust, no editor; ~91-99% cell-accurate, plenty for walkability). Use --mpp dll
    for byte-exact via the real EditorGuts.dll (needs the editor env; can crash mid-run
    → may emit empty stub .mpp), or --mpp none to keep the source's existing .mpp."""
    backend = 're'
    out = []
    it = iter(argv)
    for a in it:
        if a == '--mpp':
            backend = next(it, 're')
        elif a.startswith('--mpp='):
            backend = a.split('=', 1)[1]
        else:
            out.append(a)
    if backend not in ('re', 'dll', 'none'):
        print(f"Error: --mpp must be one of re|dll|none (got {backend!r})")
        sys.exit(1)
    return backend, out


def _parse_raw_flag(argv):
    """Extract --raw {auto,none} from argv, returning (mode, remaining_argv).
    'auto' (default) = ON-DEMAND: emit a RAW only for content types this mod
    carries source for; 'none' = skip all RAW. Supports `--raw none`/`--raw=none`."""
    mode = 'auto'
    out = []
    it = iter(argv)
    for a in it:
        if a == '--raw':
            mode = next(it, 'auto')
        elif a.startswith('--raw='):
            mode = a.split('=', 1)[1]
        else:
            out.append(a)
    if mode not in ('auto', 'none'):
        print(f"Error: --raw must be one of auto|none (got {mode!r})")
        sys.exit(1)
    return mode, out


def main():
    in_place = '--in-place' in sys.argv
    temp_copy = '--temp-copy' in sys.argv
    rest = [a for a in sys.argv[1:] if a not in ('--in-place', '--temp-copy')]
    mpp_backend, args = _parse_mpp_flag(rest)
    raw_mode, args = _parse_raw_flag(args)

    if len(args) < 1:
        print("Usage: python -m mikuro_mod_packer [--in-place|--temp-copy] "
              "[--mpp {re,dll,none}] [--raw {auto,none}] <mod_directory>")
        print("  (default)    Convert in memory, pack without copying MEDIA (fastest, non-mutating)")
        print("  --in-place   Write converted files into MEDIA, then pack")
        print("  --temp-copy  Copy MEDIA to a temp dir, convert there, then pack")
        print("  --mpp re     Offline .MPP generator (DEFAULT; robust, no editor, ~91-99% accurate)")
        print("  --mpp dll    Byte-exact .MPP via the real EditorGuts.dll (needs editor env;")
        print("               can crash mid-run and emit empty stub .mpp)")
        print("  --mpp none   Skip generation, keep the source's existing .MPP")
        print("  --raw auto   Emit RAW indexes on-demand per content type (DEFAULT)")
        print("  --raw none   Skip RAW generation entirely")
        sys.exit(1)

    mod_dir = os.path.abspath(args[0])
    media_dir = os.path.join(mod_dir, 'MEDIA')

    if not os.path.isdir(media_dir):
        print(f"Error: no MEDIA directory in {mod_dir}")
        sys.exit(1)

    # Read metadata
    meta = read_mod_metadata(mod_dir)
    print(f"MOD: {meta['name']}")
    print(f"Title: {meta.get('title', 'N/A')}")

    overrides = None
    work_media = media_dir
    if in_place:
        print("[1/3] Converting files in-place...")
        results = convert_all(media_dir, mpp=mpp_backend, raw=raw_mode)
    elif temp_copy:
        import tempfile
        tmp_media = os.path.join(tempfile.gettempdir(), f'mikuro_mod_{os.path.basename(mod_dir)}')
        if os.path.exists(tmp_media):
            shutil.rmtree(tmp_media)
        print("[1/3] Copying MEDIA to temp + converting...")
        shutil.copytree(media_dir, tmp_media)
        results = convert_all(tmp_media, mpp=mpp_backend, raw=raw_mode)
        work_media = tmp_media
    else:
        print("[1/3] Converting in memory (no copy)...")
        overrides = {}
        results = convert_all(media_dir, overrides=overrides, mpp=mpp_backend, raw=raw_mode)

    print(f"\n  Results:")
    print(f"    DAT→BINDAT:   {results['bindat']} files")
    print(f"    LAYOUT→BINLAYOUT: {results['binlayout']} files")
    print(f"    RAW generated: {results['raw']} files")
    print(f"    MPP generated: {results['mpp']} files (backend={mpp_backend})")
    if results['errors']:
        print(f"    Errors: {len(results['errors'])}")
        for e in results['errors'][:5]:
            print(f"      {e}")

    # Pack
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_name = f"{meta['name']}_{ts}.MOD"
    output_path = os.path.join(mod_dir, output_name)

    print("\n[2/3] Packing MOD...")
    mod_size = pack_mod(work_media, output_path, meta['name'],
                        original_mod_dir=mod_dir, overrides=overrides)

    if temp_copy:
        shutil.rmtree(work_media)
    print(f"\n[3/3] Done!")
    print(f"  Output: {output_path}")
    print(f"  Size:   {mod_size:,} bytes")


if __name__ == '__main__':
    main()
