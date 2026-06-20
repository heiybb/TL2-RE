#!/usr/bin/env python3
"""Real Torchlight 2 .DAT -> .BINDAT compiler.

This is a *from-scratch* serializer: it parses the .DAT text into a node tree
and emits the BINDAT bytes byte-for-byte as GUTS (EditorGuts.dll) does. It does
NOT read the sibling shipped .BINDAT (unlike the old `legacy/dat2bindat_final.py`
template-echoer) -- the only binary input is a corpus-wide *string dictionary*
resource, exactly analogous to how `parse_layout.py` parses every `.material`
into a global texture table before converting one layout.

================================================================================
BINDAT FORMAT  (reverse-engineered from EditorGuts.dll, confirmed byte-exact)
================================================================================
Serializer entry: CBinaryStyle::write  = sub_10289A40
  string collector = sub_10289950  (gathers STRING/TRANSLATE values, sorted map)
  string interner  = sub_1023E9F0  (allocates a *global* monotonic id per string)
  node writer      = sub_10289860  -> props via sub_102896D0
  stream writers   = sub_1028EC60 (raw), sub_1028ED40 (WriteShortString)

Layout (all little-endian):

  Header (12 bytes):
    u32  version       == 2   (constant)
    u32  string_count  == number of entries in the string table
    u32  first_id      == the global dictionary id of the FIRST string-table entry

  String table (string_count entries, ASCENDING by id):
    entry[0]:                  u16 len; wchar[len]          (id == header.first_id)
    entry[1..]:  u32 id;       u16 len; wchar[len]
    -> i.e. the first entry's id lives in the header (no per-entry id prefix),
       every subsequent entry is prefixed with its own id.
    -> `len` counts UTF-16 code units; bytes = 2*len.
    -> The table holds every distinct STRING(5)/TRANSLATE(8) *value* used in the
       file (deduplicated, one entry per distinct value), and ONLY those -- keys
       are stored as hashes, not strings.

  Body = exactly one root node, recursively:
    NODE:
      u32  key_hash      == RGHash(section-name)
      u32  prop_count    == number of scalar properties directly in this node
      prop_count * PROP
      u32  child_count   == number of direct sub-section nodes
      child_count * NODE
    PROP:
      u32  key_hash      == RGHash(property-key-name)
      u32  type_code     (see below)
      value:  8 bytes if type_code in {3,7} else 4 bytes

  Type codes (from the <TAG> in the DAT text):
      INTEGER       -> 1   i32
      FLOAT         -> 2   f32 (IEEE-754, bit-exact)
      UNSIGNED INT  -> 4   u32
      STRING        -> 5   u32 = global dictionary id of the value
      BOOL          -> 6   u32 (1/0)
      INTEGER64     -> 7   u64 (8 bytes)
      TRANSLATE     -> 8   u32 = global dictionary id of the value
      (type 3 is an 8-byte runtime-only type, never emitted from text)

Hash = RGHash (Runic Games string hash), see rghash.py. Property/section key
names in DATs are uppercase, so RGHash == RGHashUp for them; we hash the raw key.

================================================================================
THE STRING DICTIONARY
================================================================================
The `id` stored for a STRING/TRANSLATE value is NOT a content hash -- it is a
*global, session-persistent* integer that GUTS allocates the first time it ever
sees a given string (sub_1023E9F0: `id = counter++`). The same string therefore
gets the same id in every BINDAT it appears in (verified across the corpus:
MONSTER==0x7fd, PASSIVE==0xe0e, ALWAYS==0xeaf everywhere). Because the id depends
on the global processing order at the original ship-time compile, it cannot be
re-derived from a single file in isolation -- but every shipped BINDAT redundantly
embeds the (id, string) pairs it uses, so the *entire* dictionary can be
reconstructed once by scanning the corpus' string tables. That reconstructed
dictionary is this compiler's resource; given it, compilation is a pure
text->bytes transform.

For a brand-new string with no existing id anywhere in the corpus, GUTS would
allocate `max_id+1`; we do the same (deterministic given the dictionary).
"""
import os
import re
import struct
import pickle
import glob

from .rghash import rg_hash

# ---------------------------------------------------------------------------
# Type tags
# ---------------------------------------------------------------------------
# Normalized (spaces stripped, uppercased) tag -> type code.
TYPE_MAP = {
    'INTEGER': 1, 'INT': 1,
    'FLOAT': 2,
    'UNSIGNEDINT': 4, 'UINT': 4,
    'STRING': 5,
    'BOOL': 6, 'BOOLEAN': 6,
    'INTEGER64': 7, 'INT64': 7,
    'TRANSLATE': 8,
}
# Types whose value occupies 8 bytes rather than 4.
WIDE_TYPES = (3, 7)
# Types whose value is a string-table id.
STRING_TYPES = (5, 8)


def _norm_tag(tag):
    return tag.upper().replace(' ', '')


def _decode_dat_bytes(data):
    """Decode a .DAT byte blob (UTF-16, BOM-aware).

    Some shipped .DAT files (e.g. the global TAGS.DAT) have raw binary blobs
    (float colour data) spliced into a <STRING>: value, which reinterpret as
    lone UTF-16 surrogates and are illegal under strict/replace decoding. The
    editor's compiler reads the wchar stream verbatim and passes those code
    units straight into the .BINDAT, so we MUST decode with surrogatepass (and
    re-encode the same way in WriteShortString) to reproduce the bytes exactly.
    errors='replace' would clobber the blob with U+FFFD and lose 5 strings."""
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        enc = 'utf-16'
    else:
        enc = 'utf-16-le'
    return data.decode(enc, errors='surrogatepass')


# ---------------------------------------------------------------------------
# Node tree
# ---------------------------------------------------------------------------
class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name):
        self.name = name
        self.props = []        # list of (type_tag, key, raw_value)
        self.children = []     # list of Node


# ---------------------------------------------------------------------------
# DAT text parser
# ---------------------------------------------------------------------------
# A property line: <TYPE>KEY:VALUE   (VALUE may be empty, may contain ':' and '<>')
# KEY may be EMPTY: TAGS.DAT (and other flat tables) store `<STRING>:tagname` /
# `<INTEGER>:hash` pairs with no key — the datum is the VALUE. `[^:]*?` (vs `+?`)
# lets those parse; non-empty keys still match (the `:` anchor forces the full key).
_PROP_RE = re.compile(r'^<([A-Za-z0-9_ ]+)>\s*([^:]*?)\s*:(.*)$')


def parse_dat_text(text):
    """Parse .DAT text into a list of top-level Node trees.

    Sections are `[NAME] ... [/NAME]` and nest. Property lines are
    `<TYPE>KEY:VALUE`. Returns the list of root nodes (DATs have exactly one).
    """
    text = text.lstrip('﻿')
    lines = text.splitlines()
    roots = []
    stack = []  # stack of open Nodes
    for raw in lines:
        # Strip only leading indentation and any trailing CR; trailing spaces in
        # a property VALUE are significant (GUTS keeps them), so do NOT rstrip
        # the whole line.
        line = raw.lstrip(' \t').rstrip('\r')
        if not line:
            continue
        if line[0] == '[':
            close = line.find(']')
            if close == -1:
                continue
            name = line[1:close].strip()
            if name.startswith('/'):
                # closing tag
                if stack:
                    stack.pop()
                continue
            node = Node(name)
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
            continue
        m = _PROP_RE.match(line)
        if m and stack:
            type_tag = m.group(1).strip()
            key = m.group(2).strip()
            value = m.group(3)
            stack[-1].props.append((type_tag, key, value))
    return roots


# ---------------------------------------------------------------------------
# Value encoding
# ---------------------------------------------------------------------------
def _encode_int(raw):
    try:
        return int(raw.strip())
    except ValueError:
        try:
            return int(float(raw.strip()))
        except ValueError:
            return 0


def _encode_float_bits(raw):
    try:
        f = float(raw.strip())
    except ValueError:
        f = 0.0
    return struct.unpack('<I', struct.pack('<f', f))[0]


def _encode_bool(raw):
    return 1 if raw.strip().upper() in ('TRUE', '1', 'YES') else 0


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------
class StringDict:
    """Global string id dictionary used by the BINDAT compiler.

    Maps each string *value* to the stable global integer id GUTS assigned it.
    Built once by scanning the shipped corpus' BINDAT string tables; cached to a
    pickle next to this module. New strings get `max_id+1` deterministically.
    """

    # The empty string is interned as id 0xFFFFFFFF (the -1 sentinel returned by
    # EditorGuts sub_1023E9F0 for empty strings) and is NOT written into the
    # string table -- a prop with an empty STRING/TRANSLATE value just stores
    # this id inline.
    EMPTY_ID = 0xFFFFFFFF

    def __init__(self, s2id=None, max_id=0):
        self.s2id = s2id or {}
        # Real maximum allocated id, ignoring the empty-string sentinel.
        self.max_id = max_id if max_id != self.EMPTY_ID else 0
        for i in self.s2id.values():
            if i != self.EMPTY_ID and i > self.max_id:
                self.max_id = i
        self._next = self.max_id + 1

    def get(self, s):
        """Return the id for `s`, allocating a fresh one if unknown."""
        if s == '':
            return self.EMPTY_ID
        i = self.s2id.get(s)
        if i is not None:
            return i
        i = self._next
        self._next += 1
        self.s2id[s] = i
        return i

    def has(self, s):
        return s in self.s2id


class HashStringDict:
    """Per-FILE string->id via hash, with intra-file linear probing for
    uniqueness. Replaces the global-counter StringDict for compilation: because
    the game resolves a BINDAT's string ids through THAT file's own table (model
    A — PROVEN: the shipped base game has 565 cross-file id collisions and loads
    fine, and a hash-id-packed class mod renders correctly in-game), the actual id
    VALUES are irrelevant as long as they are unique WITHIN the file. So we drop
    the global intern counter entirely — no corpus dictionary, no shared state ->
    compilation is embarrassingly parallel and deterministic.

    Determinism: ids depend only on the file's string SET (iterated sorted), so
    the probe order is fixed regardless of parse/scheduling order. Uniqueness:
    the BINDAT string table is keyed by id ({id: string}) so two strings sharing
    an id would silently drop one -> we linear-probe on collision. EMPTY string
    keeps the 0xFFFFFFFF sentinel."""
    EMPTY_ID = 0xFFFFFFFF

    def __init__(self, strings):
        self.s2id = {}
        used = set()
        for s in sorted(strings):
            i = rg_hash(s) & 0xFFFFFFFF
            while i == self.EMPTY_ID or i in used:
                i = (i + 1) & 0xFFFFFFFF
            used.add(i)
            self.s2id[s] = i

    def get(self, s):
        return self.EMPTY_ID if s == '' else self.s2id[s]

    def has(self, s):
        return s in self.s2id


_DEFAULT_PKL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'data', 'bindat_string_dict.pkl')


def _read_bindat_string_table(data):
    """Yield (id, string) pairs from a BINDAT's string table. Read-only parse of
    the *table header*; used only to build the corpus dictionary resource."""
    if len(data) < 12:
        return
    ver, scount, first_id = struct.unpack_from('<3I', data, 0)
    off = 12
    if scount == 0:
        return
    ln = struct.unpack_from('<H', data, off)[0]
    off += 2
    s = data[off:off + ln * 2].decode('utf-16-le', 'surrogatepass')
    off += ln * 2
    yield first_id, s
    for _ in range(scount - 1):
        if off + 6 > len(data):
            break
        h = struct.unpack_from('<I', data, off)[0]
        ln = struct.unpack_from('<H', data, off + 4)[0]
        off += 6
        s = data[off:off + ln * 2].decode('utf-16-le', 'surrogatepass')
        off += ln * 2
        yield h, s


def build_string_dict(media_dir, cache_path=_DEFAULT_PKL, save=True):
    """Scan every *.DAT.BINDAT under `media_dir`, reconstruct the global
    id<->string dictionary, and (optionally) cache it. This is a corpus resource
    build (analogous to parsing every .material), not a per-file template read.

    The shipped corpus is NOT perfectly self-consistent: a handful of binaries
    were compiled in an earlier session and reuse a low id for a *different*
    string than the rest of the corpus does (715 such (id,string) collisions).
    We resolve each string to the id used by the *majority* of files, which is
    the canonical dictionary the bulk of the corpus was compiled against. The
    minority files end up "stale" relative to it (their text no longer matches
    their shipped bytes) -- the same category the old echoer hit.
    """
    from collections import Counter
    # For each string, count how often each id is used; pick the most common.
    counts = {}  # string -> Counter(id -> n)
    max_id = 0
    pattern = os.path.join(media_dir, '**', '*.BINDAT')
    for path in glob.iglob(pattern, recursive=True):
        if not path.upper().endswith('.DAT.BINDAT'):
            continue
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
        except OSError:
            continue
        for i, s in _read_bindat_string_table(data):
            if i != StringDict.EMPTY_ID and i > max_id:
                max_id = i
            c = counts.get(s)
            if c is None:
                counts[s] = c = Counter()
            c[i] += 1
    s2id = {s: c.most_common(1)[0][0] for s, c in counts.items()}
    sd = StringDict(s2id, max_id)
    if save:
        with open(cache_path, 'wb') as fh:
            pickle.dump({'s2id': s2id, 'max_id': max_id}, fh)
    return sd


def load_string_dict(cache_path=_DEFAULT_PKL):
    with open(cache_path, 'rb') as fh:
        d = pickle.load(fh)
    return StringDict(d['s2id'], d['max_id'])


def get_string_dict(media_dir=None, cache_path=_DEFAULT_PKL):
    """Load the cached dictionary, building it from `media_dir` if absent."""
    if os.path.exists(cache_path):
        return load_string_dict(cache_path)
    if media_dir is None:
        raise FileNotFoundError(
            "String dictionary cache not found at %s and no media_dir given to "
            "build it." % cache_path)
    return build_string_dict(media_dir, cache_path)


def _collect_strings(node, out):
    """Collect distinct STRING/TRANSLATE values across the whole tree (the
    string-table contents). `out` is an ordered dict-like set preserving first
    appearance (order doesn't matter -- the table is re-sorted by id)."""
    for type_tag, _key, value in node.props:
        tc = TYPE_MAP.get(_norm_tag(type_tag), 5)
        # Empty string values are not stored in the table (they use the
        # 0xFFFFFFFF sentinel id inline).
        if tc in STRING_TYPES and value != '':
            out[value] = None
    for child in node.children:
        _collect_strings(child, out)


def _serialize_node(node, sdict, parts):
    """Append a node's bytes to `parts`."""
    # key + prop count
    scalar_props = node.props
    parts.append(struct.pack('<II', rg_hash(node.name), len(scalar_props)))
    for type_tag, key, value in scalar_props:
        tc = TYPE_MAP.get(_norm_tag(type_tag), 5)
        kh = rg_hash(key)
        if tc in STRING_TYPES:
            vid = sdict.get(value)
            parts.append(struct.pack('<III', kh, tc, vid))
        elif tc == 6:
            parts.append(struct.pack('<III', kh, tc, _encode_bool(value)))
        elif tc == 2:
            parts.append(struct.pack('<III', kh, tc, _encode_float_bits(value)))
        elif tc == 4:
            parts.append(struct.pack('<III', kh, tc, _encode_int(value) & 0xFFFFFFFF))
        elif tc == 7:
            iv = _encode_int(value) & 0xFFFFFFFFFFFFFFFF
            parts.append(struct.pack('<IIQ', kh, tc, iv))
        else:  # tc == 1 (INTEGER), default
            parts.append(struct.pack('<IIi', kh, tc, _encode_int(value)))
    # children
    parts.append(struct.pack('<I', len(node.children)))
    for child in node.children:
        _serialize_node(child, sdict, parts)


def compile_tree(roots, sdict):
    """Serialize an already-parsed node tree (list of roots; DATs have one) to
    BINDAT bytes using the provided StringDict."""
    if not roots:
        raise ValueError("no root section parsed from DAT")
    # 1. Collect string-table contents.
    string_set = {}
    for r in roots:
        _collect_strings(r, string_set)
    # 2. Resolve ids and sort ascending (matches GUTS' std::map iteration).
    id_list = sorted({sdict.get(s): s for s in string_set}.items())
    # 3. Header.
    parts = []
    if id_list:
        first_id = id_list[0][0]
    else:
        first_id = 0
    parts.append(struct.pack('<III', 2, len(id_list), first_id))
    # 4. String table: first entry has no id prefix (id is in header), rest do.
    for idx, (sid, s) in enumerate(id_list):
        enc = s.encode('utf-16-le', 'surrogatepass')
        ln = len(enc) // 2
        if idx == 0:
            parts.append(struct.pack('<H', ln) + enc)
        else:
            parts.append(struct.pack('<IH', sid, ln) + enc)
    # 5. Body: root node(s).
    for r in roots:
        _serialize_node(r, sdict, parts)
    return b''.join(parts)


def compile_dat(dat_text_or_path, sdict=None, media_dir=None):
    """Compile a .DAT (text string or path) into BINDAT bytes from scratch.

    - `dat_text_or_path`: either the DAT text (str containing '[') or a file path.
    - `sdict`: a string dictionary; if None (the default), each file gets its own
      `HashStringDict` (per-file hash ids — no corpus dict, no shared state, fully
      parallel/deterministic). Pass an explicit StringDict (e.g. the corpus dict)
      only to reproduce the shipped global-id scheme byte-for-byte (tests).
    - `media_dir`: only used when an explicit corpus dict must be built.
    Reads NO existing .BINDAT for the target file.
    """
    if isinstance(dat_text_or_path, bytes):
        text = _decode_dat_bytes(dat_text_or_path)
    elif '\n' in dat_text_or_path or dat_text_or_path.lstrip().startswith('['):
        text = dat_text_or_path
    else:
        with open(dat_text_or_path, 'rb') as fh:
            text = _decode_dat_bytes(fh.read())
    roots = parse_dat_text(text)
    if sdict is None:
        ss = {}
        for r in roots:
            _collect_strings(r, ss)
        sdict = HashStringDict(ss.keys())
    return compile_tree(roots, sdict)


# ---------------------------------------------------------------------------
# CLI / batch validation
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    import time

    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python -m mikuro_mod_packer.bindat build <media_dir>          # build dict cache")
        print("  python -m mikuro_mod_packer.bindat <file.DAT>                 # compile one, compare")
        print("  python -m mikuro_mod_packer.bindat verify <media_dir> [N]     # byte-exact over sample")
        sys.exit(1)

    if args[0] == 'build':
        sd = build_string_dict(args[1])
        print("dict: %d strings, max_id=0x%x -> %s" % (len(sd.s2id), sd.max_id, _DEFAULT_PKL))
        sys.exit(0)

    if args[0] == 'verify':
        media = args[1]
        limit = int(args[2]) if len(args) > 2 else 0
        sd = get_string_dict(media)
        files = glob.glob(os.path.join(media, '**', '*.DAT.BINDAT'), recursive=True)
        if limit:
            import random
            random.seed(1234)
            random.shuffle(files)
            files = files[:limit]
        ok = diff = err = 0
        diffs = []
        t0 = time.time()
        for bp in files:
            dp = bp[:-len('.BINDAT')]
            if not os.path.exists(dp):
                continue
            try:
                with open(bp, 'rb') as fh:
                    shipped = fh.read()
                out = compile_dat(dp, sd)
                if out == shipped:
                    ok += 1
                else:
                    diff += 1
                    if len(diffs) < 40:
                        diffs.append((dp, len(out), len(shipped)))
            except Exception as e:  # noqa
                err += 1
                if len(diffs) < 40:
                    diffs.append((dp, 'ERR', repr(e)))
        print("%d files: %d byte-exact, %d diff, %d err  (%.1fs)" %
              (ok + diff + err, ok, diff, err, time.time() - t0))
        for d in diffs:
            print("  DIFF", d)
        sys.exit(0)

    # single file
    dp = args[0]
    sd = get_string_dict(os.environ.get('TL2_MEDIA_DIR'))
    out = compile_dat(dp, sd)
    bp = dp + '.BINDAT'
    if os.path.exists(bp):
        with open(bp, 'rb') as fh:
            shipped = fh.read()
        if out == shipped:
            print("MATCH (%d bytes)" % len(out))
        else:
            n = min(len(out), len(shipped))
            first = next((i for i in range(n) if out[i] != shipped[i]), n)
            print("DIFF: out=%d shipped=%d first-diff-at=%d" % (len(out), len(shipped), first))
    else:
        print("compiled %d bytes (no shipped .BINDAT to compare)" % len(out))
