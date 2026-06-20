#!/usr/bin/env python3
"""
LAYOUT -> BINLAYOUT compiler for Torchlight 2.

This is a REAL compiler: it parses the .LAYOUT text and serializes the
.BINLAYOUT binary from scratch. It reads NO existing .BINLAYOUT (that is the
whole point -- text edits are honoured). Output is byte-exact to what the
GUTS editor (EditorGuts.dll) produces, reverse-engineered from the writer
chain sub_101169B0 -> sub_10116780 -> sub_10116650 -> sub_10116420 ->
sub_10115320 (per-object) and sub_101150F0 (datagroup tree).

Format (little-endian) -- see tools/build_layout_schema.py for how the
per-descriptor property schema was learned from the shipped corpus:

  HEADER
    u8   magic      = 0x0B
    u8   flag       = 0x04
    u32  dg_off     = byte offset of the trailing datagroup section (0 if none)
    u16  obj_count  = number of TOP-LEVEL objects

  OBJECT (recursive; block_size is back-patched to cover the whole subtree)
    u32  block_size = bytes from this field to the end of this object subtree
    u8   descriptor = code for the object's DESCRIPTOR name
    s64  id         = the object's <INTEGER64>ID
    str  name       = the object's <STRING>NAME  (u16 char-count + UTF-16-LE)
    u8   prop_count
    PROPERTY * prop_count
      u16 mem       = number of bytes that follow (this u16 excluded)
      u8  code      = property code
      ..  value     = per the property's encoder (see ENCODERS)
    u32  adprop     = byte-length of the object's extra-property region. 0 for
                      most objects; for a Logic Group it is the embedded logic
                      graph (_serialize_logicgroup) and for a Timeline the
                      embedded timeline graph (_serialize_timelinedata).
    [adprop bytes]  = that extra-property region, if any
    u16  child_count
    OBJECT * child_count

  DATAGROUP (present iff the layout contains any Group object)
    A CLayoutBinaryGroup tree (sub_101150F0) mirroring the Group-object tree,
    rooted at a synthetic node (id = -1). Each node carries the Group's
    CHOICE/RANDOMIZATION/NUMBER/TAG/GAME MODE/LEVEL UNIQUE and active/deactive
    theme-id lists, plus @28 = the stream offset of the Group's object block.
    See _build_datagroup / _emit_dg_node. TAG resolves to a small global id via
    the registry map in data/binlayout_datagroup_tags.json (built offline, like the
    schema; the compiler reads no per-file binary).

Strings are [u16 char-count][UTF-16-LE] (sub_1028ED40 / WriteShortString).
"""
import os
import re
import json
import struct

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "binlayout_schema.json")
_SCHEMA = None

MAGIC = 0x0B
FLAG = 0x04

# Property keys that are NOT serialized as properties: DESCRIPTOR -> object's
# descriptor byte, NAME -> name field, ID -> id field, PARENTID -> implicit in
# the tree (dropped).
_META_KEYS = frozenset(("DESCRIPTOR", "NAME", "PARENTID", "ID"))

_PROP_RE = re.compile(r'<([^>]+)>([^:]+):(.*)')


def _load_schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            _SCHEMA = json.load(f)["descriptors"]
    return _SCHEMA


# ── value encoders (text -> bytes) ────────────────────────────────────────

def _f32(x):
    return struct.pack("<f", float(x))


def _parse_int(s):
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(float(s)) if ("." in s or "e" in s.lower()) else int(s)


def _enc_float(v):
    return _f32(v[0])


def _enc_u32int(v):
    return struct.pack("<i", _parse_int(v[0]))


def _enc_u32bool(v):
    s = v[0].strip().lower()
    return struct.pack("<I", 0 if s in ("false", "0", "f", "") else 1)


def _enc_short_string(s):
    return struct.pack("<H", len(s)) + s.encode("utf-16-le")


def _enc_string(v):
    return _enc_short_string(v[0])


def _enc_g2(v):
    return _f32(v[0]) + _f32(v[1])


def _enc_g3(v):
    return _f32(v[0]) + _f32(v[1]) + _f32(v[2])


def _enc_g4(v):
    return _f32(v[0]) + _f32(v[1]) + _f32(v[2]) + _f32(v[3])


def _enc_curve(v):
    parts = v[0].split(",") if v[0] != "" else []
    out = struct.pack("<H", len(parts))
    for p in parts:
        out += _f32(p)
    return out


ENCODERS = {
    "float": _enc_float,
    "u32int": _enc_u32int,
    "u32bool": _enc_u32bool,
    "string": _enc_string,
    "g2": _enc_g2,
    "g3": _enc_g3,
    "g4": _enc_g4,
    "curve": _enc_curve,
}


# ── .LAYOUT text parser ───────────────────────────────────────────────────

def _read_text(path_or_text):
    """Accept a path or already-decoded text; return the UTF-16 text."""
    if "\n" in path_or_text or "[Layout]" in path_or_text or "[OBJECTS]" in path_or_text:
        # Looks like raw text already.
        return path_or_text
    raw = open(path_or_text, "rb").read()
    if raw[:2] == b"\xff\xfe":
        raw = raw[2:]
    return raw.decode("utf-16-le", "replace")


def parse_layout(path_or_text):
    """Parse a .LAYOUT into a list of top-level objects.

    Each object is {'props': [(type, key, value), ...], 'children': [...]}.
    Property order is preserved from the source text.
    """
    txt = _read_text(path_or_text)
    # Strip the CR and the leading indentation (tabs) only -- the VALUE part of
    # a property line may legitimately end in spaces, which are significant
    # (GUTS preserves them in the NAME / string fields), so we must NOT strip
    # the trailing whitespace off the whole line.
    lines = [l.rstrip("\r").lstrip("\t ") for l in txt.split("\n")]
    pos = [0]

    def baseobjs(end_tag):
        objs = []
        while pos[0] < len(lines):
            l = lines[pos[0]]
            if l == end_tag:
                return objs
            if l == "[BASEOBJECT]":
                pos[0] += 1
                obj = {"props": [], "children": [], "logic": None, "timeline": None}
                while pos[0] < len(lines):
                    l = lines[pos[0]]
                    if l == "[/BASEOBJECT]":
                        pos[0] += 1
                        break
                    if l == "[PROPERTIES]":
                        pos[0] += 1
                        while pos[0] < len(lines) and lines[pos[0]] != "[/PROPERTIES]":
                            ln = lines[pos[0]]
                            if ln == "[LOGICGROUP]":
                                # A Logic Group object embeds a logic graph inside
                                # its [PROPERTIES] block (not as a normal property).
                                obj["logic"] = _parse_logicgroup(lines, pos)
                                continue
                            if ln == "[TIMELINEDATA]":
                                # A Timeline object embeds its timeline graph inside
                                # [PROPERTIES] (analogous to [LOGICGROUP]).
                                obj["timeline"] = _parse_timelinedata(lines, pos)
                                continue
                            m = _PROP_RE.match(ln)
                            if m:
                                obj["props"].append((m.group(1).strip(), m.group(2).strip(), m.group(3)))
                            pos[0] += 1
                        pos[0] += 1
                    elif l == "[CHILDREN]":
                        pos[0] += 1
                        obj["children"] = baseobjs("[/CHILDREN]")
                        pos[0] += 1
                    else:
                        pos[0] += 1
                objs.append(obj)
            else:
                pos[0] += 1
        return objs

    while pos[0] < len(lines) and lines[pos[0]] != "[OBJECTS]":
        pos[0] += 1
    pos[0] += 1
    return baseobjs("[/OBJECTS]")


def _parse_logicgroup(lines, pos):
    """Parse a [LOGICGROUP]..[/LOGICGROUP] block sitting inside a Logic Group
    object's [PROPERTIES]. Returns a list of logic objects:
      {'id': int, 'objectid': int, 'x': float, 'y': float,
       'links': [{'linkingto': int, 'output': str, 'input': str}, ...]}
    `pos[0]` is advanced past the closing [/LOGICGROUP]."""
    pos[0] += 1  # consume [LOGICGROUP]
    lobjs = []
    while pos[0] < len(lines):
        l = lines[pos[0]]
        if l == "[/LOGICGROUP]":
            pos[0] += 1
            break
        if l == "[LOGICOBJECT]":
            pos[0] += 1
            lo = {"id": 0, "objectid": 0, "x": 0.0, "y": 0.0, "links": []}
            while pos[0] < len(lines):
                l = lines[pos[0]]
                if l == "[/LOGICOBJECT]":
                    pos[0] += 1
                    break
                if l == "[LOGICLINK]":
                    pos[0] += 1
                    link = {"linkingto": 0, "output": "", "input": ""}
                    while pos[0] < len(lines):
                        l = lines[pos[0]]
                        if l == "[/LOGICLINK]":
                            pos[0] += 1
                            break
                        m = _PROP_RE.match(l)
                        if m:
                            key, val = m.group(2).strip(), m.group(3)
                            if key == "LINKINGTO":
                                link["linkingto"] = _parse_int(val)
                            elif key == "OUTPUTNAME":
                                link["output"] = val
                            elif key == "INPUTNAME":
                                link["input"] = val
                        pos[0] += 1
                    lo["links"].append(link)
                    continue
                m = _PROP_RE.match(l)
                if m:
                    key, val = m.group(2).strip(), m.group(3)
                    if key == "ID":
                        lo["id"] = _parse_int(val)
                    elif key == "OBJECTID":
                        lo["objectid"] = _parse_int(val)
                    elif key == "X":
                        lo["x"] = float(val)
                    elif key == "Y":
                        lo["y"] = float(val)
                pos[0] += 1
            lobjs.append(lo)
        else:
            pos[0] += 1
    return lobjs


def _parse_timelinedata(lines, pos):
    """Parse a [TIMELINEDATA]..[/TIMELINEDATA] block inside a Timeline object's
    [PROPERTIES]. Returns a list of timeline objects:
      {'objectid': int, 'entries': [
          {'property': str, 'event': str,
           'points': [{'time': float, 'interp': str, 'value': str}, ...]},
          ...]}
    `pos[0]` is advanced past the closing [/TIMELINEDATA]. The leading
    <INTEGER64>ID inside [TIMELINEDATA] is not serialized (the runtime re-derives
    it from the object), so it is parsed and discarded."""
    pos[0] += 1  # consume [TIMELINEDATA]
    tobjs = []
    while pos[0] < len(lines):
        l = lines[pos[0]]
        if l == "[/TIMELINEDATA]":
            pos[0] += 1
            break
        if l == "[TIMELINEOBJECT]":
            pos[0] += 1
            to = {"objectid": 0, "entries": []}
            while pos[0] < len(lines):
                l = lines[pos[0]]
                if l == "[/TIMELINEOBJECT]":
                    pos[0] += 1
                    break
                if l in ("[TIMELINEOBJECTEVENT]", "[TIMELINEOBJECTPROPERTY]"):
                    end = "[/" + l[1:]
                    pos[0] += 1
                    entry = {"property": "", "event": "", "points": []}
                    while pos[0] < len(lines):
                        l = lines[pos[0]]
                        if l == end:
                            pos[0] += 1
                            break
                        if l == "[TIMELINEPOINT]":
                            pos[0] += 1
                            pt = {"time": 0.0, "interp": "Linear", "value": ""}
                            while pos[0] < len(lines):
                                l = lines[pos[0]]
                                if l == "[/TIMELINEPOINT]":
                                    pos[0] += 1
                                    break
                                m = _PROP_RE.match(l)
                                if m:
                                    key, val = m.group(2).strip(), m.group(3)
                                    if key == "TIMEPERCENT":
                                        pt["time"] = float(val)
                                    elif key == "INTERPOLATION":
                                        pt["interp"] = val
                                    elif key == "VALUE":
                                        pt["value"] = val
                                pos[0] += 1
                            entry["points"].append(pt)
                            continue
                        m = _PROP_RE.match(l)
                        if m:
                            key, val = m.group(2).strip(), m.group(3)
                            if key == "OBJECTEVENTNAME":
                                entry["event"] = val
                            elif key == "OBJECTPROPERTYNAME":
                                entry["property"] = val
                        pos[0] += 1
                    to["entries"].append(entry)
                    continue
                m = _PROP_RE.match(l)
                if m and m.group(2).strip() == "OBJECTID":
                    to["objectid"] = _parse_int(m.group(3))
                pos[0] += 1
            tobjs.append(to)
        else:
            pos[0] += 1
    return tobjs


# ── property grouping (POSITIONX/Y/Z -> a single grouped property) ────────

def _grouped_props(tprops):
    """Return list of (name, type_tag, [values...]) skipping meta keys and
    folding consecutive *X/*Y/*Z(/*W) triples/quads into one grouped prop."""
    seq = []
    i = 0
    n = len(tprops)
    seen_name = False
    seen_choice = False
    seen_gamemode = False
    # The object's identity NAME (the FIRST <STRING>NAME). A descriptor that
    # also carries a NAME *property* (e.g. Timeline, code 105) stores the
    # OBJECT name there, not the literal text of the 2nd NAME line -- GUTS reads
    # the property value from the object's name member, and the 2nd NAME line is
    # frequently empty/stale (verified byte-exact across the shipped corpus).
    identity_name = ""
    for (_t, _k, _v) in tprops:
        if _k == "NAME":
            identity_name = _v
            break
    while i < n:
        t, k, v = tprops[i]
        # DESCRIPTOR/PARENTID/ID and the FIRST NAME are object-identity meta
        # fields. A SECOND <STRING>NAME is a genuine property and must be
        # emitted -- but with the object's identity name as its value.
        # CHOICE / GAME MODE behave the same way for a Group: the FIRST feeds a
        # datagroup field (@16 / @27), the SECOND is a real object property
        # (code 101 / 118). Both occurrences always carry the same value.
        if k in ("DESCRIPTOR", "PARENTID", "ID") or (k == "NAME" and not seen_name) \
                or (k == "CHOICE" and not seen_choice) \
                or (k == "GAME MODE" and not seen_gamemode):
            if k == "NAME":
                seen_name = True
            if k == "CHOICE":
                seen_choice = True
            if k == "GAME MODE":
                seen_gamemode = True
            i += 1
            continue
        if k == "NAME":
            v = identity_name
        # Transform grouping (POSITIONX/Y/Z -> one 12-byte prop) applies ONLY
        # to concatenated orientation names like POSITION/FORWARD/RIGHT/UP --
        # i.e. a non-empty base that does not end in a space. Bare X/Y/Z keys
        # (Scale curves) and "SCALE X" (space) stay as separate properties.
        base = k[:-1]
        if (k.endswith("X") and base and not base.endswith(" ") and i + 1 < n
                and tprops[i + 1][1] == base + "Y"):
            if (i + 2 < n and tprops[i + 2][1] == base + "Z"):
                if i + 3 < n and tprops[i + 3][1] == base + "W":
                    seq.append((base, t, [v, tprops[i + 1][2], tprops[i + 2][2], tprops[i + 3][2]]))
                    i += 4
                else:
                    seq.append((base, t, [v, tprops[i + 1][2], tprops[i + 2][2]]))
                    i += 3
            else:
                # X/Y-only group (e.g. PADDINGX/PADDINGY -> one 8-byte "PADDING").
                seq.append((base, t, [v, tprops[i + 1][2]]))
                i += 2
        else:
            seq.append((k, t, [v]))
            i += 1
    return seq


def _obj_meta(obj):
    """Pull DESCRIPTOR / NAME / ID from an object's props. NAME is the FIRST
    <STRING>NAME (the object identity); a 2nd NAME is a separate property."""
    desc = name = oid = None
    for (t, k, v) in obj["props"]:
        if k == "DESCRIPTOR":
            desc = v
        elif k == "NAME" and name is None:
            name = v
        elif k == "ID":
            oid = v
    return desc, (name or ""), oid


# ── Logic Group sub-structure (mirrors the descriptor writer sub_10109C30 /
#    binary reader sub_10108CC0 + sub_1010C030) ──────────────────────────────

def _serialize_logicgroup(lobjs, out):
    """Append the binary logic graph (written into the ADPROP region of a Logic
    Group object). Layout:
      u8  obj_count
      per object:
        u8  ID
        s64 OBJECTID
        f32 X
        f32 Y
        u32 end_offset   (absolute stream offset of the END of this object's
                          data == start of the next object, back-patched)
        u8  link_count
        per link:
          u8  LINKINGTO
          str OUTPUTNAME  ([u16 char-count][UTF-16-LE])
          str INPUTNAME
    """
    out.append(len(lobjs) & 0xFF)
    for lo in lobjs:
        out.append(lo["id"] & 0xFF)
        out += struct.pack("<q", lo["objectid"])
        out += _f32(lo["x"])
        out += _f32(lo["y"])
        end_pos = len(out)
        out += b"\x00\x00\x00\x00"  # end_offset placeholder (absolute)
        out.append(len(lo["links"]) & 0xFF)
        for link in lo["links"]:
            out.append(link["linkingto"] & 0xFF)
            out += _enc_short_string(link["output"])
            out += _enc_short_string(link["input"])
        struct.pack_into("<I", out, end_pos, len(out))


# ── Timeline sub-structure (mirrors the descriptor writer sub_1010FA60 /
#    binary reader sub_10116B00) ──────────────────────────────────────────────

# INTERPOLATION name -> u8 index. Order is the static table initialised in
# sub_1149D180 (unk_133AF900, 28-byte stride). The writer linear-scans this
# table and stores the matching index; an unknown name maps to 0 (Linear).
_INTERP_INDEX = {
    "Linear": 0,
    "Linear Round": 1,
    "Linear Round Down": 2,
    "Linear Round Up": 3,
    "Spline": 4,
    "Quaternion": 5,
    "No Interpolation": 6,
    "Use Timeline Default": 7,
}


def _serialize_timelinedata(tobjs, out):
    """Append the binary timeline graph (written into the ADPROP region of a
    Timeline object). Layout:
      u8  obj_count
      per TIMELINEOBJECT:
        s64 OBJECTID
        u8  entry_count
        per entry (event or property):
          str OBJECTPROPERTYNAME   (empty for an event)
          str OBJECTEVENTNAME      (empty for a property)
          u8  point_count
          per TIMELINEPOINT:
            f32 TIMEPERCENT
            u8  INTERPOLATION index
            str VALUE              (only when OBJECTEVENTNAME is empty -- i.e.
                                    this entry is a property, not an event)
    """
    out.append(len(tobjs) & 0xFF)
    for to in tobjs:
        out += struct.pack("<q", to["objectid"])
        out.append(len(to["entries"]) & 0xFF)
        for ent in to["entries"]:
            out += _enc_short_string(ent["property"])
            out += _enc_short_string(ent["event"])
            is_property = (ent["event"] == "")
            out.append(len(ent["points"]) & 0xFF)
            for pt in ent["points"]:
                out += _f32(pt["time"])
                out.append(_INTERP_INDEX.get(pt["interp"], 0) & 0xFF)
                if is_property:
                    out += _enc_short_string(pt["value"])


# ── per-object serializer (mirrors sub_10116420 + sub_10115320) ───────────

def _serialize_object(obj, out, offsets=None):
    schema = _load_schema()
    desc, name, oid_s = _obj_meta(obj)
    dinfo = schema.get(desc)
    if dinfo is None or dinfo.get("code") is None:
        raise KeyError("unknown DESCRIPTOR %r (no schema)" % desc)

    block_start = len(out)
    # Record where this object's block_size field begins -- the datagroup's @28
    # ("DATAGROUP MEM LOCATION") field is exactly this stream offset.
    if offsets is not None and oid_s is not None:
        offsets[int(oid_s)] = block_start
    out += b"\x00\x00\x00\x00"  # block_size placeholder

    out.append(dinfo["code"] & 0xFF)
    oid = int(oid_s) if oid_s is not None else 0
    out += struct.pack("<q", oid)
    # NAME field: GUTS writes the object NAME only when it differs from the
    # descriptor's default name (which is the DESCRIPTOR string itself);
    # otherwise the field is empty. (sub_10115320: operator!= against default.)
    name_field = name if name != desc else ""
    out += _enc_short_string(name_field)

    # Emit properties in SOURCE (text) order: GUTS writes exactly the values
    # the object carries, and for text-authored layouts that order matches the
    # .LAYOUT property order. The schema only supplies each property's code and
    # value encoder. Properties not registered for this descriptor are skipped.
    pinfo = dinfo["props"]
    emitted = []
    for (nm, ttag, vals) in _grouped_props(obj["props"]):
        spec = pinfo.get(nm)
        if spec is None:
            continue
        emitted.append((spec["code"], spec["enc"], vals))

    out.append(len(emitted) & 0xFF)  # prop_count (u8)
    for (code, enc, vals) in emitted:
        body = bytes([code & 0xFF]) + ENCODERS[enc](vals)
        out += struct.pack("<H", len(body))
        out += body

    # ADPROP field. Normally 0. For a Logic Group it carries the embedded logic
    # graph (the editor's "extra-property" writer, vtable+116 in sub_10115320):
    # the u32 is the byte-length of everything the logic writer appends, and the
    # logic data follows it directly.
    adprop_pos = len(out)
    out += b"\x00\x00\x00\x00"  # adprop placeholder (= sub-struct byte-count, else 0)
    logic = obj.get("logic")
    timeline = obj.get("timeline")
    if logic is not None:
        _serialize_logicgroup(logic, out)
        struct.pack_into("<I", out, adprop_pos, len(out) - (adprop_pos + 4))
    elif timeline is not None:
        _serialize_timelinedata(timeline, out)
        struct.pack_into("<I", out, adprop_pos, len(out) - (adprop_pos + 4))

    children = obj["children"]
    out += struct.pack("<H", len(children))
    for ch in children:
        _serialize_object(ch, out, offsets)

    block_size = len(out) - block_start
    struct.pack_into("<I", out, block_start, block_size)


# ── datagroup (CLayoutBinaryGroup tree, writer sub_101150F0 / sub_10116780) ─

_DGTAGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "binlayout_datagroup_tags.json")
_DGTAGS = None

# CHOICE -> @16 index (table unk_133F41F8 from sub_114D37D0).
_CHOICE_INDEX = {"ALL": 0, "WEIGHT": 1, "RANDOM CHANCE": 2}
# GAME MODE -> @27 (sub_10115320: 0 if absent, 1 NORMAL, 2 otherwise/NEW GAME PLUS).
_GAMEMODE_INDEX = {"NORMAL": 1, "NEW GAME PLUS": 2}


def _load_dgtags():
    global _DGTAGS
    if _DGTAGS is None:
        try:
            with open(_DGTAGS_PATH, "r", encoding="utf-8") as f:
                _DGTAGS = json.load(f)
        except FileNotFoundError:
            _DGTAGS = {}
    return _DGTAGS


def _parse_id_list(s):
    """Parse a comma-separated theme-id list (trailing comma tolerated)."""
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out


def _has_group(objs):
    for o in objs:
        desc, _, _ = _obj_meta(o)
        if desc == "Group":
            return True
        if _has_group(o["children"]):
            return True
    return False


def _collect_group_nodes(objs):
    """Build the datagroup tree mirroring the Group-object tree. Returns a list
    of nodes; each Group becomes a node whose children are the Groups nested
    beneath it (re-parented to the nearest Group ancestor, so non-Group objects
    in between are transparent)."""
    nodes = []
    for o in objs:
        desc, _, oid = _obj_meta(o)
        child_nodes = _collect_group_nodes(o["children"])
        if desc == "Group":
            tprops = {k: v for (t, k, v) in o["props"]}
            nodes.append({"id": int(oid) if oid is not None else -1,
                          "props": tprops, "children": child_nodes})
        else:
            # Non-Group: its Group descendants bubble up to this level.
            nodes.extend(child_nodes)
    return nodes


def _emit_dg_node(node, off28, offsets, out):
    """Serialize one CLayoutBinaryGroup node (mirrors sub_101150F0)."""
    tp = node["props"]
    # @8 s64 id
    out += struct.pack("<q", node["id"])
    # @16 u8 CHOICE index
    choice = _CHOICE_INDEX.get((tp.get("CHOICE") or "").strip().upper(), 0)
    out.append(choice & 0xFF)
    # @20 u32 RANDOMIZATION (default 1)
    rnd = tp.get("RANDOMIZATION")
    out += struct.pack("<I", 1 if rnd is None else (_parse_int(rnd) & 0xFFFFFFFF))
    # @24 u8 NUMBER (default 1)
    num = tp.get("NUMBER")
    out.append((1 if num is None else _parse_int(num)) & 0xFF)
    # @28 u32 stream offset of this object's block (DATAGROUP MEM LOCATION)
    out += struct.pack("<I", off28 & 0xFFFFFFFF)
    # @92 u32 TAG id (default 0xFFFFFFFF; resolved via the baked registry map)
    tag = (tp.get("TAG") or "").strip().upper()
    tagid = _load_dgtags().get(tag, 0xFFFFFFFF) if tag else 0xFFFFFFFF
    out += struct.pack("<I", tagid & 0xFFFFFFFF)
    # @25 NO TAG FOUND, @26 LEVEL UNIQUE, @27 GAME MODE
    out.append(0)  # @25 (corpus: 0 except a handful of stale binaries)
    out.append(1 if (tp.get("LEVEL UNIQUE") or "").strip().lower() == "true" else 0)
    out.append(_GAMEMODE_INDEX.get((tp.get("GAME MODE") or "").strip().upper(), 0) & 0xFF)
    # active / deactive theme id lists
    active = _parse_id_list(tp.get("ACTIVE THEMES"))
    out += struct.pack("<I", len(active))
    for v in active:
        out += struct.pack("<q", v)
    deactive = _parse_id_list(tp.get("DEACTIVE THEMES"))
    out += struct.pack("<I", len(deactive))
    for v in deactive:
        out += struct.pack("<q", v)
    # children
    out += struct.pack("<H", len(node["children"]))
    for ch in node["children"]:
        _emit_dg_node(ch, offsets.get(ch["id"], 0), offsets, out)


def _build_datagroup(objs, offsets, root_off28):
    """Build the trailing datagroup tree. Returns bytes, or None when the layout
    has no Group object (then dg_off stays 0).

    The section is a CLayoutBinaryGroup tree rooted at a synthetic node
    (id = -1, all fields 0, @28 = stream position right after the header) whose
    children are the layout's top-level Groups, mirroring the Group-object tree.
    """
    if not _has_group(objs):
        return None
    top_nodes = _collect_group_nodes(objs)
    out = bytearray()
    # synthetic root: sub_10116780 -> sub_10112C10(-1, ..., tellp(=6), 0)
    root = {"id": -1, "props": {}, "children": top_nodes}
    # Root's RANDOMIZATION/NUMBER are 0 (constructor args a5=a6=0), unlike the
    # default-1 a real Group gets, so emit the root by hand.
    out += struct.pack("<q", -1)
    out.append(0)                       # @16
    out += struct.pack("<I", 0)         # @20 (root randomization = 0)
    out.append(0)                       # @24 (root number = 0)
    out += struct.pack("<I", root_off28 & 0xFFFFFFFF)  # @28
    out += struct.pack("<I", 0xFFFFFFFF)  # @92 tag
    out += b"\x00\x00\x00"              # @25 @26 @27
    out += struct.pack("<I", 0)         # active count
    out += struct.pack("<I", 0)         # deactive count
    out += struct.pack("<H", len(top_nodes))
    for ch in top_nodes:
        _emit_dg_node(ch, offsets.get(ch["id"], 0), offsets, out)
    return bytes(out)


def compile_layout(path_or_text):
    """Compile a .LAYOUT (path or text) into BINLAYOUT bytes from scratch.

    Reads NO existing binary. Returns bytes, or raises on a parse/schema error.
    """
    objs = parse_layout(path_or_text)

    out = bytearray()
    out.append(MAGIC)
    out.append(FLAG)
    dg_off_pos = len(out)
    out += b"\x00\x00\x00\x00"          # dg_off placeholder
    # The synthetic datagroup root's @28 is tellp right after the 6-byte header.
    root_off28 = len(out)
    out += struct.pack("<H", len(objs))  # obj_count (top-level only)

    offsets = {}
    for o in objs:
        _serialize_object(o, out, offsets)

    # Datagroup section: present iff the layout has any Group object.
    dg = _build_datagroup(objs, offsets, root_off28)
    if dg is not None:
        struct.pack_into("<I", out, dg_off_pos, len(out))
        out += dg

    return bytes(out)


def convert(layout_path, binlayout_path=None):
    """Drop-in for the old API. binlayout_path is accepted for signature
    compatibility but IGNORED -- this compiler reads no existing binary."""
    return compile_layout(layout_path)


# ── CLI: validate byte-exactness over a MEDIA tree ────────────────────────

if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) >= 3 and sys.argv[1] == "compile":
        # compile one file: python -m mikuro_mod_packer.binlayout compile in.LAYOUT out.BINLAYOUT
        data = compile_layout(sys.argv[2])
        with open(sys.argv[3], "wb") as f:
            f.write(data)
        print("wrote %d bytes" % len(data))
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python -m mikuro_mod_packer.binlayout <media_dir>            # validate")
        print("       python -m mikuro_mod_packer.binlayout compile <in> <out>     # compile one")
        sys.exit(1)

    media_dir = sys.argv[1]
    t0 = time.time()
    no_dg_pass = no_dg_total = dg_pass = dg_total = err = 0
    misses = []
    dg_misses = []
    for root, _, files in os.walk(media_dir):
        for f in files:
            if not f.endswith(".BINLAYOUT"):
                continue
            bp = os.path.join(root, f)
            lp = bp[:-len(".BINLAYOUT")]
            if not os.path.exists(lp):
                continue
            orig = open(bp, "rb").read()
            has_datagroup = len(orig) >= 6 and struct.unpack_from("<I", orig, 2)[0] != 0
            try:
                gen = compile_layout(lp)
            except Exception as e:
                err += 1
                misses.append((lp, "ERR: %s" % e))
                continue
            if has_datagroup:
                dg_total += 1
                if gen == orig:
                    dg_pass += 1
                else:
                    dg_misses.append((lp, "MISMATCH len %d vs %d" % (len(gen), len(orig))))
            else:
                no_dg_total += 1
                if gen == orig:
                    no_dg_pass += 1
                else:
                    misses.append((lp, "MISMATCH len %d vs %d" % (len(gen), len(orig))))

    elapsed = time.time() - t0
    print("== LAYOUT->BINLAYOUT compile (no existing binary read) ==")
    print("no-datagroup files: %d/%d byte-exact = %.2f%%" % (
        no_dg_pass, no_dg_total, 100.0 * no_dg_pass / max(1, no_dg_total)))
    print("datagroup files:    %d/%d byte-exact = %.2f%%" % (
        dg_pass, dg_total, 100.0 * dg_pass / max(1, dg_total)))
    print("errors: %d   (%.1fs)" % (err, elapsed))
    if misses:
        print("-- no-datagroup misses --")
        for m in misses[:25]:
            print("  MISS", m[0], "->", m[1])
    if dg_misses:
        print("-- datagroup misses --")
        for m in dg_misses[:25]:
            print("  MISS", m[0], "->", m[1])
