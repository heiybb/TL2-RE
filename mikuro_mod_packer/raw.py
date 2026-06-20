#!/usr/bin/env python3
"""RAW index file writers, ported from TL2Lib/rgio.raw.pas (Encode* functions).

A RAW file indexes a category of source .DAT files. WriteShortString = [u16
len][UTF-16-LE]. All ints little-endian. Encoders take already-scanned entry
dicts; build_*_from_media scans the source tree (Windows FindFirst order: a
name-sorted, case-insensitive DFS — files and subdirs interleaved by name).
"""
import os, re, struct

# Base-game install MEDIA. A mod unit's BASEFILE inheritance chain frequently
# points at a BASE template that ships only in the install (not copied into the
# mod), e.g. a custom 2H sword inheriting <STRING>UNITTYPE from the base
# greatsword template. The editor resolves BASEFILE against the FULL loaded game
# (mod overriding base), so UNITDATA.RAW's inherited fields (UNITTYPE/LEVEL/...)
# come through; resolving only within the mod drops them. Mirror that fallback.
_INSTALL_MEDIA = os.environ.get('TL2_MEDIA_DIR', r"E:\Torchlight 2\MEDIA")

# ── stream primitives ──

def _ss(s):
    """WriteShortString: u16 char count + UTF-16-LE."""
    return struct.pack('<H', len(s)) + s.encode('utf-16-le')

def _u32(v): return struct.pack('<I', v & 0xFFFFFFFF)
def _u16(v): return struct.pack('<H', v & 0xFFFF)
def _u8(v):  return struct.pack('<B', v & 0xFF)
def _q(v):   return struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF)


# ── source scan (FindFirst order) ──

def _scan(root, ext='.DAT'):
    """Yield <ext> paths under root in GUTS's scan order: per directory, this
    dir's files first (case-insensitive name sort), then recurse into subdirs
    (also name-sorted). Files-before-dirs, not interleaved."""
    ext = ext.upper()
    # os.scandir (not listdir + per-entry os.path.isdir): on Windows DirEntry
    # caches is_dir from the single directory read, so scanning a 15k-file tree
    # costs no per-entry stat (~3s -> ~0.3s on AFFIXES of a 68k-file mod).
    try:
        with os.scandir(root) as it:
            entries = list(it)
    except OSError:
        return
    files, dirs = [], []
    for e in entries:
        eu = e.name.upper()
        if e.is_dir():
            dirs.append((eu, e.path))
        elif eu.endswith(ext) and '.BIN' not in eu:
            files.append((eu, e.path))
    for _, full in sorted(files):
        yield full
    for _, full in sorted(dirs):
        yield from _scan(full, ext)


def _scan_dats(root):
    return _scan(root, '.DAT')


def _layout_names(text):
    """All <STRING>NAME: values inside the layout's [OBJECTS] block, in order."""
    m = re.search(r'\[OBJECTS\](.*?)\[/OBJECTS\]', text, re.DOTALL | re.IGNORECASE)
    body = m.group(1) if m else text
    return [s.strip() for s in re.findall(r'<STRING>NAME\s*:\s*([^\r\n]+)', body)]


def _read_dat(path):
    with open(path, 'r', encoding='utf-16-le') as f:
        return f.read()

def _field(text, name, default=None):
    m = re.search(rf'<[A-Z0-9 ]+>{name}\s*:\s*([^\r\n]*)', text)
    return m.group(1).strip() if m else default

def _media_path(dat_path, media_dir):
    # GUTS uppercases the whole stored path (ASCII); non-ASCII (e.g. CJK) is
    # left as-is by str.upper().
    rel = os.path.relpath(dat_path, media_dir).replace('\\', '/')
    return ('MEDIA/' + rel).upper()

def _block_list(text, block, item):
    """Collect repeated <STRING>item: values inside [block]...[/block]."""
    m = re.search(rf'\[{block}\](.*?)\[/{block}\]', text, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    return re.findall(rf'<STRING>{item}\s*:\s*([^\r\n]+)', m.group(1))


# ── AFFIXES ──  EncodeAffixes (GUTS sub_103C4170):
#   u16 count (= scan count, every .DAT loads); per entry:
#     SS(FILE) SS(NAME upper)
#     u32(MIN_SPAWN_RANGE def 0) u32(MAX_SPAWN_RANGE def 999999)
#     u32(WEIGHT def 1) u32(DIFFICULTIES_ALLOWED def -1)
#     u8(nUNITTYPES)     SS(value)*   <- every <STRING>…: inside [UNITTYPES]
#     u8(nNOT_UNITTYPES) SS(value)*   <- every <STRING>…: inside [NOT_UNITTYPES]
#   Scan order is the name-interleaved DFS (sub_10292E10 / sub_1029BEA0 over
#   MEDIA/AFFIXES/ *.DAT). NAME missing -> "NA". The item tag inside the blocks
#   is inconsistent in the source DATs (UNITTYPE / UNITTYPES / NOT_UNITTYPES);
#   GUTS reads each item group's string value regardless of tag, so we collect
#   the value of every <STRING> line within the block.
#   Byte-verified: reproduces shipped MEDIA/AFFIXES.RAW exactly (4049 entries).

def _affix_unittypes(text, block):
    out = []
    for m in re.finditer(r'\[' + block + r'\](.*?)\[/' + block + r'\]',
                         text, re.DOTALL):
        out += [x.strip() for x in re.findall(
            r'<STRING>[A-Z0-9_ ]+\s*:\s*([^\r\n]+)', m.group(1))]
    return out


def _affix_entry(dp, media_dir):
    """One AFFIXES.RAW record (bytes) for affix .DAT `dp`. Shared by the serial
    and the process-pool builders so both produce byte-identical output."""
    t = _read_dat(dp)
    name = (_field(t, 'NAME', 'NA') or 'NA').upper()
    mn = _to_int(_field(t, 'MIN_SPAWN_RANGE'), 0)
    mx = _to_int(_field(t, 'MAX_SPAWN_RANGE'), 999999)
    w = _to_int(_field(t, 'WEIGHT'), 1)
    diff = _to_int(_field(t, 'DIFFICULTIES_ALLOWED'), -1)
    ut = _affix_unittypes(t, 'UNITTYPES')
    nut = _affix_unittypes(t, 'NOT_UNITTYPES')
    parts = [_ss(_media_path(dp, media_dir)), _ss(name),
             _u32(mn), _u32(mx), _u32(w), _u32(diff), _u8(len(ut))]
    parts += [_ss(x) for x in ut]
    parts.append(_u8(len(nut)))
    parts += [_ss(x) for x in nut]
    return b''.join(parts)


def build_affixes(media_dir):
    affixes = list(_scan_interleaved(os.path.join(media_dir, 'AFFIXES'), '.DAT'))
    if not affixes:
        return None
    return b''.join([_u16(len(affixes))] + [_affix_entry(dp, media_dir) for dp in affixes])


# ── SKILLS ──  EncodeSkills (GUTS sub_102ECFD0): u32 count (back-patched to the
#   number of *included* skills); per included skill: SS(NAME upper) SS(FILE)
#   QWord(UNIQUE_GUID def -1). A skill with an empty/missing NAME is skipped
#   (count counts only emitted entries). Scan order is the name-interleaved DFS
#   over MEDIA/SKILLS/ *.DAT — NOT files-before-dirs (verified against the shipped
#   RAW: the first entry is ALCHEMIST/…, root .DATs like EFFECT_BURN come later).
#   Byte-verified: reproduces shipped MEDIA/SKILLS.RAW exactly (1659 entries).

def _skill_entry(dp, media_dir):
    """One SKILLS.RAW record (bytes) for skill .DAT `dp`, or None when NAME is
    empty/missing (those are skipped and not counted). Shared by serial+pool."""
    t = _read_dat(dp)
    name = (_field(t, 'NAME', '') or '').upper()
    if name == '':
        return None
    guid = _to_int(_field(t, 'UNIQUE_GUID'), -1)
    return _ss(name) + _ss(_media_path(dp, media_dir)) + _q(guid)


def build_skills(media_dir):
    dats = list(_scan_interleaved(os.path.join(media_dir, 'SKILLS'), '.DAT'))
    if not dats:
        return None
    entries = [e for e in (_skill_entry(dp, media_dir) for dp in dats) if e is not None]
    return _u32(len(entries)) + b''.join(entries)


# ── TRIGGERABLES ──  EncodeTriggers: u16 count; per: SS(FILE) SS(NAME)

def build_triggerables(media_dir):
    dats = list(_scan_dats(os.path.join(media_dir, 'TRIGGERABLES')))
    if not dats:
        return None
    out = [_u16(len(dats))]
    for dp in dats:
        t = _read_dat(dp)
        out.append(_ss(_media_path(dp, media_dir)))
        out.append(_ss(_field(t, 'NAME', os.path.splitext(os.path.basename(dp))[0])))
    return b''.join(out)


# ── MISSILES ──  EncodeMissiles (GUTS sub_102FB490): u16 count (back-patched to
#   the number of loadable .LAYOUTs — every layout that loads emits an entry,
#   even with zero missile names); per entry:
#     SS(FILE) u8(nMissileNames) SS(MISSILE NAME upper)*
#   For each [OBJECTS] object whose <STRING>DESCRIPTOR is exactly "Missile",
#   GUTS emits that object's MISSILE NAME (uppercased; missing -> "NA"). FILE is a
#   .LAYOUT (NOT .DAT). Scan order is the name-interleaved DFS over
#   MEDIA/MISSILES/ *.LAYOUT (root layouts first, then MONSTERS/ etc.).
#   Byte-verified: reproduces shipped MEDIA/MISSILES.RAW exactly (407 entries).

def build_missiles(media_dir):
    lays = list(_scan_interleaved(os.path.join(media_dir, 'MISSILES'), '.LAYOUT'))
    if not lays:
        return None
    body = []
    count = 0
    for lp in lays:
        t = _read_dat(lp)
        count += 1
        m = re.search(r'\[OBJECTS\](.*?)\[/OBJECTS\]', t, re.DOTALL | re.IGNORECASE)
        objs = m.group(1) if m else t
        names = []
        for pb in re.split(r'(?=\[PROPERTIES\])', objs):
            if re.search(r'<STRING>DESCRIPTOR\s*:\s*Missile\s*$', pb, re.MULTILINE):
                mn = re.search(r'<STRING>MISSILE NAME\s*:\s*([^\r\n]*)', pb)
                names.append((mn.group(1).strip() if mn else 'NA').upper())
        body.append(_ss(_media_path(lp, media_dir)))
        body.append(_u8(len(names)))
        body += [_ss(n) for n in names]
    return _u16(count) + b''.join(body)


# ── UI ──  EncodeUI (GUTS sub_103178E0):
#   u32 count; per included menu:
#     SS(MENU NAME) SS(FILE) u32(TYPE idx) u32(GAME STATE idx)
#     u8(ALWAYS VISIBLE || CREATE ON LOAD) u8(MULTIPLAYER ONLY)
#     u8(SINGLEPLAYER ONLY) SS(KEY BINDING)
#
#   Scan: every .LAYOUT under MEDIA/UI/ in _scan (FindFirst) order. Only layouts
#   whose [OBJECTS] contains an object with <STRING>DESCRIPTOR:Menu Definition
#   are candidates; the menu's props are read off THAT object (not the layout as
#   a whole). Inclusion rule (sub_103178E0): skip if MENU NAME is empty OR the
#   DO NOT CREATE bool is true; the count is the number of *included* entries
#   (NOT the layout count — 109 of 171 layouts ship).
#
#   FILE = the layout's stored path from "MEDIA" onward (on-disk casing == upper,
#   matching _media_path). TYPE / GAME STATE are case-insensitive indices into
#   the editor enum tables below (default 0 / not-found). The first flag byte is
#   ALWAYS VISIBLE OR CREATE ON LOAD (both checked, OR'd) — not CREATE ON LOAD
#   alone. Byte-verified: reproduces shipped MEDIA/UI.RAW exactly (109 entries).
_UI_TYPES = [None, 'TEST MENU', 'HUD MENU', 'CHAT MENU', 'PLAYER STATS MENU',
             'MERCHANT MENU', 'SKILL MENU', 'QUEST DIALOG MENU', 'QUEST MENU',
             'MESSAGE BOX MENU', 'MAIN MENU', 'SERVER MENU', 'CONSOLE MENU',
             'RESURRECTION MENU', 'TOWNPORTAL MENU', 'HOTBAR CONTEXT MENU',
             'STANDALONE SERVER MENU', 'LOGIN MENU', 'UPSELL MENU', 'CLIENT OPTIONS']
_UI_STATES = [None, 'Testing', 'All', 'In Game', 'Server Only', 'Loading', 'Main Menu Mod']


def _idx(arr, val):
    for j, x in enumerate(arr):
        if x is not None and val is not None and x.upper() == val.upper():
            return j
    return 0


def _menu_definition_props(text):
    """Return the property-block text of the [OBJECTS] object whose
    <STRING>DESCRIPTOR is exactly 'Menu Definition' (first match), or None.
    GUTS reads MENU NAME / TYPE / flags off this object specifically."""
    m = re.search(r'\[OBJECTS\](.*?)\[/OBJECTS\]', text, re.DOTALL | re.IGNORECASE)
    body = m.group(1) if m else text
    for pb in re.split(r'(?=\[PROPERTIES\])', body):
        if re.search(r'<STRING>DESCRIPTOR\s*:\s*Menu Definition\s*$',
                     pb, re.MULTILINE | re.IGNORECASE):
            return pb
    return None


def _menu_str(block, name):
    m = re.search(rf'<STRING>{re.escape(name)}\s*:([^\r\n]*)', block)
    return m.group(1).strip() if m else ''


def _menu_bool(block, name):
    m = re.search(rf'<BOOL>{re.escape(name)}\s*:([^\r\n]*)', block)
    return bool(m) and m.group(1).strip().upper() in ('TRUE', '1', 'YES')


def build_ui(media_dir):
    lays = list(_scan(os.path.join(media_dir, 'UI'), '.LAYOUT'))
    if not lays:
        return None
    out = []
    count = 0
    for lp in lays:
        blk = _menu_definition_props(_read_dat(lp))
        if blk is None:
            continue
        menu_name = _menu_str(blk, 'MENU NAME')
        # Inclusion rule: empty MENU NAME or DO NOT CREATE -> not indexed.
        if menu_name == '' or _menu_bool(blk, 'DO NOT CREATE'):
            continue
        count += 1
        f0 = 1 if (_menu_bool(blk, 'ALWAYS VISIBLE')
                   or _menu_bool(blk, 'CREATE ON LOAD')) else 0
        out.append(_ss(menu_name))
        out.append(_ss(_media_path(lp, media_dir)))
        out.append(_u32(_idx(_UI_TYPES, _menu_str(blk, 'TYPE') or None)))
        out.append(_u32(_idx(_UI_STATES, _menu_str(blk, 'GAME STATE') or None)))
        out.append(_u8(f0))
        out.append(_u8(1 if _menu_bool(blk, 'MULTIPLAYER ONLY') else 0))
        out.append(_u8(1 if _menu_bool(blk, 'SINGLEPLAYER ONLY') else 0))
        out.append(_ss(_menu_str(blk, 'KEY BINDING')))
    return _u32(count) + b''.join(out)


# ── UNITDATA ──  EncodeUnits (GUTS sub_1026CC50 / reader sub_1026F2B0):
#   4 fixed categories in order ITEMS, MONSTERS, PLAYERS, PROPS (the MEDIA/UNITS
#   subdirs). Per category: u32 count; then per unit:
#     i64(UNIT_GUID) SS(NAME) SS(FILE) u8(flags)
#     i32(LEVEL) i32(MINLEVEL) i32(MAXLEVEL) i32(RARITY) i32(RARITY_HARDCORE)
#     SS(UNITTYPE)
#   flags: bit0 = CREATEAS==EQUIPMENT, bit1 = SET present.
#   Units whose OWN .DAT has <BOOL>DONTCREATE:true are skipped (abstract bases).
#   Every other field is resolved through the BASEFILE inheritance chain
#   (child first, then parents). Integer fields use GUTS's getter-loop: scan the
#   chain and take the first value that differs from the field's default
#   (LEVEL/RARITY default 1; MINLEVEL/MAXLEVEL default 0; RARITY_HARDCORE default
#   = the resolved RARITY). For a DONTCREATE-skip nothing is emitted, but note
#   GUTS still re-derives RARITY/RARITY_HARDCORE as 0 only when DONTCREATE is set
#   *and* the unit is kept — which never happens, so kept units always carry the
#   chain-resolved rarity.
#   Scan order is a fully name-interleaved DFS (files and subdirs sorted together
#   by name, case-insensitive; recurse on dirs in place) — NOT the files-before-
#   dirs order of _scan used by the other RAWs.

_UNIT_CATEGORIES = ('ITEMS', 'MONSTERS', 'PLAYERS', 'PROPS')


def _scan_interleaved(root, ext='.DAT'):
    """GUTS unit scan order: per directory, sort files and subdirs *together*
    by name (case-insensitive); yield a file or recurse into a subdir in that
    merged order. (_scan, by contrast, does all files then all subdirs.)"""
    ext = ext.upper()
    # os.scandir: is_dir cached from the one directory read, no per-entry stat.
    try:
        with os.scandir(root) as it:
            entries = list(it)
    except OSError:
        return
    items = []  # (UPPER_name, full, is_dir)
    for e in entries:
        eu = e.name.upper()
        if e.is_dir():
            items.append((eu, e.path, True))
        elif eu.endswith(ext) and '.BIN' not in eu:
            items.append((eu, e.path, False))
    for _, full, is_dir in sorted(items):
        if is_dir:
            yield from _scan_interleaved(full, ext)
        else:
            yield full


def _unit_attrs(text):
    """Top-level [UNIT] attributes only: NAME->value, first occurrence. Nested
    sub-blocks ([WARDROBE], [REQ_CLASS], [AFFIXES], ...) are skipped — only
    lines directly inside the outermost block (depth 1) count."""
    attrs = {}
    depth = 0
    for line in text.splitlines():
        s = line.strip().lstrip('﻿')
        if not s:
            continue
        if s.startswith('[/'):
            depth -= 1
            continue
        if s.startswith('['):
            depth += 1
            continue
        if depth != 1:
            continue
        m = re.match(r'<[A-Z0-9 ]+>([A-Z0-9_ ]+)\s*:(.*)$', s)
        if m:
            k = m.group(1).strip().upper()
            if k not in attrs:
                attrs[k] = m.group(2).strip()
    return attrs


def _basefile_path(basefile, media_dir):
    rel = basefile.replace('\\', '/').strip()
    if rel.upper().startswith('MEDIA/'):
        rel = rel[6:]
    return os.path.join(media_dir, rel.replace('/', os.sep))


def _resolve_basefile(basefile, media_dir):
    """Resolve a BASEFILE against the mod first (mod overrides base), then fall
    back to the base-game install — matching how the editor chains inheritance
    across the full loaded game."""
    p = _basefile_path(basefile, media_dir)
    if os.path.isfile(p):
        return p
    if os.path.normcase(media_dir) != os.path.normcase(_INSTALL_MEDIA):
        pi = _basefile_path(basefile, _INSTALL_MEDIA)
        if os.path.isfile(pi):
            return pi
    return p


def _unit_attrs_for(path, cache):
    """Read+parse a unit DAT's attrs (None if missing), memoized by absolute path.
    A base template inherited by hundreds/thousands of mod units is read+decoded+
    regex-parsed ONCE, not once per inheriting unit — the dominant cost of
    UNITDATA on unit-heavy mods (worsened by the base-install fallback chain)."""
    key = os.path.normcase(os.path.abspath(path))
    if cache is not None and key in cache:
        return cache[key]
    attrs = _unit_attrs(_read_dat(path)) if os.path.isfile(path) else None
    if cache is not None:
        cache[key] = attrs
    return attrs


def _unit_chain(path, media_dir, depth=0, seen=None, cache=None):
    """Inheritance chain as a list of attr-dicts, child first then BASEFILE
    ancestors (cycle- and depth-guarded). `cache` memoizes the per-DAT read+parse
    across the whole build (see _unit_attrs_for)."""
    if seen is None:
        seen = set()
    key = os.path.normcase(os.path.abspath(path))
    if depth > 30 or key in seen:
        return []
    seen.add(key)
    own = _unit_attrs_for(path, cache)
    if own is None:
        return []
    out = [own]
    bf = own.get('BASEFILE')
    if bf:
        out += _unit_chain(_resolve_basefile(bf, media_dir), media_dir, depth + 1, seen, cache)
    return out


def _chain_str(chain, name, default=''):
    for a in chain:
        v = a.get(name)
        if v is not None and v != default:
            return v
    return default


def _to_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _chain_int(chain, name, default):
    """GUTS integer getter loop: walk child->base, return the first value that
    differs from `default`; otherwise `default`."""
    for a in chain:
        v = a.get(name)
        if v is None or v == '':
            continue
        iv = _to_int(v, default)
        if iv != default:
            return iv
    return default


def _unit_entry(dp, media_dir, cache):
    """One UNITDATA.RAW record (bytes) for unit .DAT `dp`, or None for an abstract
    base template (DONTCREATE) which is excluded from the index. `cache` memoizes
    the per-DAT attr read across the unit's BASEFILE chain. Shared by serial+pool
    (the cache is pure memoization, so output is identical whether it is shared
    across the whole build or rebuilt per worker)."""
    own = _unit_attrs_for(dp, cache)
    if own.get('DONTCREATE', '').upper() == 'TRUE':
        return None
    chain = _unit_chain(dp, media_dir, cache=cache)
    guid = _to_int(_chain_str(chain, 'UNIT_GUID', ''), -1)
    name = _chain_str(chain, 'NAME', '').upper()
    createas = _chain_str(chain, 'CREATEAS', '')
    setv = _chain_str(chain, 'SET', '')
    flags = 1 if createas.upper() == 'EQUIPMENT' else 0
    if setv != '':
        flags |= 2
    level = _chain_int(chain, 'LEVEL', 1)
    minlevel = _chain_int(chain, 'MINLEVEL', 0)
    maxlevel = _chain_int(chain, 'MAXLEVEL', 0)
    rarity = _chain_int(chain, 'RARITY', 1)
    rarity_hc = _chain_int(chain, 'RARITY_HARDCORE', rarity)
    unittype = _chain_str(chain, 'UNITTYPE', '').upper()
    return b''.join([
        _q(guid), _ss(name), _ss(_media_path(dp, media_dir)),
        _u8(flags),
        _u32(level), _u32(minlevel), _u32(maxlevel),
        _u32(rarity), _u32(rarity_hc),
        _ss(unittype),
    ])


def build_unitdata(media_dir):
    units_root = os.path.join(media_dir, 'UNITS')
    if not os.path.isdir(units_root):
        return None
    out = []
    emitted = 0
    cache = {}   # shared path -> attrs cache across every unit's inheritance chain
    for cat in _UNIT_CATEGORIES:
        cat_root = os.path.join(units_root, cat)
        entries = [e for e in (_unit_entry(dp, media_dir, cache)
                               for dp in _scan_interleaved(cat_root, '.DAT'))
                   if e is not None]
        out.append(_u32(len(entries)))
        out += entries
        emitted += len(entries)
    if not emitted:
        return None
    return b''.join(out)


# ── ROOMPIECES ──  EncodeRoomPieces: u32 count; per: SS(FILE); then per: u32(GUIDS count) QWord(GUID)*

def build_roompieces(media_dir):
    dats = list(_scan_dats(os.path.join(media_dir, 'LEVELSETS')))
    if not dats:
        return None
    guids = []
    for dp in dats:
        t = _read_dat(dp)
        blk = re.findall(r'\[PIECE\](.*?)\[/PIECE\]', t, re.DOTALL | re.IGNORECASE)
        gs = []
        for b in blk:
            m = re.search(r'<INTEGER64>GUID\s*:\s*(-?\d+)', b)
            if m:
                gs.append(int(m.group(1)))
        guids.append(gs)
    out = [_u32(len(dats))]
    out += [_ss(_media_path(dp, media_dir)) for dp in dats]
    for gs in guids:
        out.append(_u32(len(gs)))
        out += [_q(g) for g in gs]
    return b''.join(out)


# ── parallel builders ──
# The three heavy RAW indexes (UNITDATA/AFFIXES/SKILLS) are an order-preserving
# per-DAT map. Their cost is dominated by READING thousands of tiny UTF-16 DATs
# (I/O), so the caller hands in a THREAD pool, not a process pool: file I/O drops
# the GIL (so reads parallelize), results stay in memory (no pickling/IPC overhead
# per tiny item, which crushed the process-pool version), and the UNITDATA
# BASEFILE-chain attr cache can be SHARED across threads (a plain dict is GIL-safe;
# the worst race is a duplicate parse with an identical result, never corruption).
# Order-preserving `executor.map` -> output byte-identical to the serial builders.
def build_unitdata_parallel(media_dir, executor, chunksize=64):
    units_root = os.path.join(media_dir, 'UNITS')
    if not os.path.isdir(units_root):
        return None
    cache = {}   # shared across threads (UNITDATA BASEFILE-chain attr memo)
    out = []
    emitted = 0
    for cat in _UNIT_CATEGORIES:
        paths = list(_scan_interleaved(os.path.join(units_root, cat), '.DAT'))
        entries = [e for e in executor.map(lambda p: _unit_entry(p, media_dir, cache),
                                           paths, chunksize=chunksize)
                   if e is not None] if paths else []
        out.append(_u32(len(entries)))
        out += entries
        emitted += len(entries)
    if not emitted:
        return None
    return b''.join(out)


def build_affixes_parallel(media_dir, executor, chunksize=64):
    affixes = list(_scan_interleaved(os.path.join(media_dir, 'AFFIXES'), '.DAT'))
    if not affixes:
        return None
    entries = list(executor.map(lambda p: _affix_entry(p, media_dir),
                                affixes, chunksize=chunksize))
    return b''.join([_u16(len(affixes))] + entries)


def build_skills_parallel(media_dir, executor, chunksize=64):
    dats = list(_scan_interleaved(os.path.join(media_dir, 'SKILLS'), '.DAT'))
    if not dats:
        return None
    entries = [e for e in executor.map(lambda p: _skill_entry(p, media_dir),
                                       dats, chunksize=chunksize)
               if e is not None]
    return _u32(len(entries)) + b''.join(entries)


BUILDERS = {
    'AFFIXES.RAW': build_affixes, 'SKILLS.RAW': build_skills,
    'TRIGGERABLES.RAW': build_triggerables, 'MISSILES.RAW': build_missiles,
    'UI.RAW': build_ui, 'ROOMPIECES.RAW': build_roompieces,
    'UNITDATA.RAW': build_unitdata,
}


if __name__ == '__main__':
    import sys
    media = sys.argv[1]
    data = build_affixes(media)
    sys.stdout.buffer.write(data or b'')
