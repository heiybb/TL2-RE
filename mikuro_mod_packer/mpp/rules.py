"""
rules.py — RULES.TEMPLATE reader + multi-chunk classification.

A level directory under MEDIA/LAYOUTS/<ACT_LEVEL>/ may carry a RULES.TEMPLATE
(UTF-16-LE, BOM) that drives PROCEDURAL CHUNK ASSEMBLY of that level. The room
.LAYOUT files live one level down, in chunk folders (e.g. 1X1SINGLE_ROOM_A). The
RULES.TEMPLATE for the *level* lives in the PARENT directory of the chunk folder
(and, for a few levels, alongside the rooms). Parsed by EditorGuts.dll's template
reader sub_10211ED0 (strings "CHUNK_RANDOM", "CHUNKWIDTHBASIS", "GENERATION_TYPE",
"TILEBASIS", etc. all resolve there).

Shape (the fields we need):
    [LEVEL]
        <FLOAT>TILEBASIS:4
        <FLOAT>CHUNKWIDTHBASIS:25
        <FLOAT>CHUNKHEIGHTBASIS:25
        <BOOL>RANDOMIZED:true
        <INTEGER>GENERATION_TYPE:1
        [LAYOUT]
            [CHUNK_RANDOM]
                <STRING>TYPE:1X1SINGLE_ROOM
                <FLOAT>X:100  <FLOAT>Y:0  <FLOAT>Z:300
            [/CHUNK_RANDOM]
        [/LAYOUT]
        ... (one [LAYOUT] per chunk SLOT)
        [CHUNKTYPE]
            <STRING>NAME:1X1SINGLE_ROOM
            <BOOL>ENTRANCE_CHUNK:true
            <INTEGER>WIDTH:1  <INTEGER>HEIGHT:1
            <STRING>FOLDER:1X1SINGLE_ROOM_A
        [/CHUNKTYPE]
    [/LEVEL]

WHY THIS MATTERS FOR THE .MPP HEADER (RE-grounded, decisive — see region.py).

The shipped .MPP next to a room is the editor's pathing bake of the *assembled*
level, not the single room. When a level has >= 2 CHUNK_RANDOM slots the assembler
places NEIGHBOUR chunks (random picks, exit-matched) into the empty slots before
the pathing grid is built; the master AABB (CLevel_RebuildLevel_GenPathing region
loop, only ACTIVE-random-group pieces — sub_1022FF80 membership) then spans those
neighbours. PROOF this is genuinely runtime-assembled and NOT reconstructible from
one .LAYOUT: each of the 4 ACT1_PASS1 rooms' shipped .MPP has tens of thousands of
PASSABLE cells (69k-104k) sitting OUTSIDE that room's entire piece span — road
geometry that exists in no single layout file. The neighbour content is chosen by
the random-group assembler, so the union is a runtime instance, not a fixed
declared envelope. A single-slot level (n_slots <= 1, no neighbours) bakes to just
its own room and IS byte-exact under the per-region collision model.

We therefore do NOT try to fabricate the neighbour union (that would require
running the full procedural assembler over all candidate chunk layouts with the
shipped instance's RNG state, which the offline data does not carry). Instead we
PARSE the rules, CLASSIFY a room as multi-chunk-assembled, and let the pipeline
report it honestly. `is_multichunk_assembled(layout_path)` is the gate.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


def _decode(data: bytes) -> str:
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16-le", errors="replace")
    if data[:2] == b"\xfe\xff":
        return data.decode("utf-16-be", errors="replace")
    return data.decode("latin-1", errors="replace")


@dataclass
class ChunkSlot:
    type: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class ChunkType:
    name: str = ""
    folder: str = ""
    width: int = 1
    height: int = 1
    entrance: bool = False


@dataclass
class RulesTemplate:
    path: str = ""
    name: str = ""
    tile_basis: float = 0.0
    chunk_width_basis: float = 0.0
    chunk_height_basis: float = 0.0
    randomized: bool = False
    generation_type: int = 0
    min_chunks: int = 0
    max_chunks: int = 0
    slots: list[ChunkSlot] = field(default_factory=list)
    chunk_types: list[ChunkType] = field(default_factory=list)

    @property
    def n_slots(self) -> int:
        return len(self.slots)

    @property
    def is_multichunk(self) -> bool:
        """A level whose pathing bake merges NEIGHBOUR-chunk geometry: >= 2 declared
        chunk slots AND GENERATION_TYPE 1 (the road/pass procedural assembler that
        exit-matches and places real neighbour rooms). GENERATION_TYPE 0 levels
        (the editor TEST stubs) declare slots too but bake to an empty default
        region, so they stay byte-exact and are NOT flagged. (Surveyed over every
        RULES.TEMPLATE under MEDIA/LAYOUTS: only gen==1 & slots>=2 merge neighbour
        geometry — the 4 ACT1_PASS1 rooms and the big hand-assembled ACT1\\SNOW.)"""
        return self.n_slots >= 2 and self.generation_type == 1


_FLOAT_RE = re.compile(r"<FLOAT>([A-Z0-9 _]+):\s*([-+0-9.eE]+)")
_INT_RE = re.compile(r"<INTEGER>([A-Z0-9 _]+):\s*([-+0-9]+)")
_STR_RE = re.compile(r"<STRING>([A-Z0-9 _]+):\s*(.*)")
_BOOL_RE = re.compile(r"<BOOL>([A-Z0-9 _]+):\s*(\w+)")


def parse_rules_template(data: bytes, path: str = "") -> RulesTemplate:
    txt = _decode(data)
    lines = [ln.strip() for ln in txt.splitlines()]
    rt = RulesTemplate(path=path)

    # top-level scalars (search the whole text — they live directly under [LEVEL])
    def fval(key, default=0.0):
        m = re.search(r"<FLOAT>" + re.escape(key) + r":\s*([-+0-9.eE]+)", txt)
        return float(m.group(1)) if m else default

    def ival(key, default=0):
        m = re.search(r"<INTEGER>" + re.escape(key) + r":\s*([-+0-9]+)", txt)
        return int(m.group(1)) if m else default

    def bval(key, default=False):
        m = re.search(r"<BOOL>" + re.escape(key) + r":\s*(\w+)", txt)
        return (m.group(1).lower() == "true") if m else default

    ms = re.search(r"<STRING>NAME:\s*(.*)", txt)
    rt.name = ms.group(1).strip() if ms else ""
    rt.tile_basis = fval("TILEBASIS")
    rt.chunk_width_basis = fval("CHUNKWIDTHBASIS")
    rt.chunk_height_basis = fval("CHUNKHEIGHTBASIS")
    rt.randomized = bval("RANDOMIZED")
    rt.generation_type = ival("GENERATION_TYPE")
    rt.min_chunks = ival("MINCHUNKS")
    rt.max_chunks = ival("MAXCHUNKS")

    # walk for [CHUNK_RANDOM] and [CHUNKTYPE] blocks
    i, n = 0, len(lines)
    while i < n:
        s = lines[i]
        if s == "[CHUNK_RANDOM]":
            slot = ChunkSlot()
            i += 1
            while i < n and lines[i] != "[/CHUNK_RANDOM]":
                m = _STR_RE.match(lines[i])
                if m and m.group(1).strip() == "TYPE":
                    slot.type = m.group(2).strip()
                m = _FLOAT_RE.match(lines[i])
                if m:
                    k = m.group(1).strip()
                    v = float(m.group(2))
                    if k == "X":
                        slot.x = v
                    elif k == "Y":
                        slot.y = v
                    elif k == "Z":
                        slot.z = v
                i += 1
            rt.slots.append(slot)
        elif s == "[CHUNKTYPE]":
            ct = ChunkType()
            i += 1
            while i < n and lines[i] != "[/CHUNKTYPE]":
                sm = _STR_RE.match(lines[i])
                if sm:
                    k = sm.group(1).strip()
                    if k == "NAME":
                        ct.name = sm.group(2).strip()
                    elif k == "FOLDER":
                        ct.folder = sm.group(2).strip()
                im = _INT_RE.match(lines[i])
                if im:
                    k = im.group(1).strip()
                    if k == "WIDTH":
                        ct.width = int(im.group(2))
                    elif k == "HEIGHT":
                        ct.height = int(im.group(2))
                bm = _BOOL_RE.match(lines[i])
                if bm and bm.group(1).strip() == "ENTRANCE_CHUNK":
                    ct.entrance = bm.group(2).lower() == "true"
                i += 1
            rt.chunk_types.append(ct)
        else:
            i += 1
    return rt


def find_rules_for_layout(layout_path: str) -> str | None:
    """Locate the RULES.TEMPLATE that governs a room .LAYOUT. The room lives in a
    chunk FOLDER (e.g. .../ACT1_PASS1/1X1SINGLE_ROOM_A/PASS_JT_A.LAYOUT); the level
    rules are in the PARENT of that folder (.../ACT1_PASS1/RULES.TEMPLATE). A few
    levels keep RULES.TEMPLATE alongside the rooms — check that too."""
    d = os.path.dirname(layout_path)
    for cand in (
        os.path.join(os.path.dirname(d), "RULES.TEMPLATE"),
        os.path.join(d, "RULES.TEMPLATE"),
    ):
        if os.path.exists(cand):
            return cand
    return None


# small cache so a 1293-file batch re-parses each RULES.TEMPLATE once
_RULES_CACHE: dict[str, RulesTemplate | None] = {}


def load_rules_for_layout(layout_path: str) -> RulesTemplate | None:
    rp = find_rules_for_layout(layout_path)
    if rp is None:
        return None
    if rp in _RULES_CACHE:
        return _RULES_CACHE[rp]
    rt = None
    try:
        with open(rp, "rb") as f:
            rt = parse_rules_template(f.read(), rp)
    except Exception:
        rt = None
    _RULES_CACHE[rp] = rt
    return rt


def is_multichunk_assembled(layout_path: str) -> bool:
    """True when the room's level is a >= 2-slot procedural assembly: its shipped
    .MPP is the editor's bake of THIS room PLUS runtime-placed neighbour chunks, so
    the header footprint spans geometry that is NOT in this single .LAYOUT and is
    NOT offline-reconstructible. (Single-slot levels bake to just their own room.)"""
    rt = load_rules_for_layout(layout_path)
    return bool(rt and rt.is_multichunk)
