"""
region.py — region-AABB computation -> grid dims + the 4 .mpp header floats.

RE grounding (definitive, EditorGuts.dll / idalib):

  * .mpp HEADER WRITER  CLevel_BuildWritePathingGrid_MPP @ 0x10200920
    The writer is called once per pathing region with
        a3 = box.getMinimum()   (region collision AABB minimum)
        a4 = box.getMaximum()   (region collision AABB maximum)
        a5 = unk_134BB57C        -- a global Vector3 == (0,0,0)   (worldExt origin)
        ox/oz = this->originX/Z (CLevel +0x2B0/+0x2B4) if this->hasOrigin (+0x5C) else 0
    and writes a 24-byte header (6 fwrites):
        [0]  int32  gridW   = ceil((a4.x-ox)/0.4) - floor((a3.x-ox)/0.4)
        [4]  int32  gridH   = ceil((a4.z-oz)/0.4) - floor((a3.z-oz)/0.4)
        [8]  float  worldW  = a5.x - a3.x         (== -a3.x, a5==0)
        [12] float  worldD  = a5.z - a3.z         (== -a3.z)
        [16] float  boundsW = a4.x - a3.x
        [20] float  boundsD = a4.z - a3.z
    All of the divide/floor/ceil is done in 32-bit float; the divisor is the
    float32 constant 0.4 (dbl_11E7B708 = float32(0.4) promoted).

  * GRID ORIGIN  CLevel_RebuildLevel_GenPathing @ 0x10203710 (block @ 0x10204FD0)
    Before the per-region writes, the level computes a single level-internal grid
    origin from the *master* level AABB (the merge of all region boxes), stored at
    CLevel +0x2B0 (X) / +0x2B4 (Z):
        originX = (floor((masterMin.x - 0.2)/0.4) - 1.0) * 0.4
        originZ = (floor((masterMin.z - 0.2)/0.4) - 1.0) * 0.4
    with the constants  PAD = float32(0.2) (dbl_11E50E88),  CELL = float32(0.4)
    (dbl_11E7B708),  EXPAND = 1.0 (dbl_11E4FA20). The compute promotes the
    float32 min to double, but the RESULT is stored as a float32 (`fstp dword`),
    so the origin carries float32 rounding — that rounding is exactly what makes
    the writer's ceil/floor straddle by +1 on some tiles and not others.

    For a single-region template the master AABB == the region box, so we feed the
    region box min into the origin formula. The origin does NOT cancel out of the
    writer's ceil/floor (it would only cancel if it were a multiple of 0.4, which
    it is not — it is offset by the PAD/EXPAND terms): reproducing it is what lifts
    header byte-exactness from ~16% to ~66% on the 1293 ground-truth files.

REGION-BOX SOURCE  (definitive, re-traced in CLevel_RebuildLevel_GenPathing
@ 0x10203931..0x10204795 — the master-AABB loop).  The master level AABB
`var_BC8` (the box the header origin/dims come from, @ 0x10204FD0) is built as the
merge of a per-REGION box, one per element of the region vector [CLevel+0x10]
(count [CLevel+0x14]). For each region the editor:
  1. Reads the region's local collision AABB via a vfunc (the CDamageShape at
     obj->[+0x58]: opposite corners at +0x8 / +0x14), composes the region world
     matrix (sub_1022B910 = offset/scale getter + node orientation), and transforms
     the 8 corners by it — Ogre AxisAlignedBox 8-corner refit (var_AAC). This is
     the SAME geometry as a per-room-piece collision-bounds refit; for a single
     pre-baked room .MPP the region == the whole room, so the region box == the
     merge of every "Room Piece" collision AABB in that room.
  2. SNAPS that refit box outward to the 10-unit tile boundary WITH A 0.2 PAD per
     face (0x102043af..0x10204511):
        snappedMin = floor((min - 0.2)/10)*10 ,  snappedMax = ceil((max + 0.2)/10)*10
     (constants dbl_11E50E88=0.2, dbl_11E7ED10=10.0; all in float32).
  3. Merges the snapped region box into var_BC8 (merge @ 0x1020457a). There is NO
     +-0.4 per-piece pad anywhere in this loop — the earlier model's 0.4 face pad
     was a coincidental fit, now replaced by the exact +-0.2-then-snap-10 rule.
We reproduce step 1 with the collision mesh's stored M_MESH_BOUNDS (== its vertex
AABB; verified equal on the cliff colliders) transformed in float32, merged
UNPADDED across all collision-enabled room pieces (the offline proxy for the
region's aggregate box), then step 2's +-0.2-snap-10 in float32 (snap_box_outward).
This is byte-exact for the single-region case and lifts header exactness from
87.9% (old 0.4-pad model) to 88.8% over the 1293 ground-truth files with no
template/plain regression.

ACTIVE-VISUAL-PIECE SELECTION (settled DETERMINISTIC; lifts 88.8% -> 90.9%).
A LEVELSETS [PIECE] is a SET of visual sub-pieces (multiple <STRING>FILE: entries,
each with a paired <STRING>COLLISIONFILE:); the layout's per-instance
<STRING>VISUAL:N picks which one. The earlier model always took the index-0
collider, which mis-sized the region by one tile wherever an instance used a
NON-zero visual whose collider had a different extent (e.g. NETHER cap-rock _01 vs
_02, z2desert tree/tablerock variants — 220 pieces ship multiple colliders).
This selection is DETERMINISTIC, proven by RE + on-disk data:
  * The editor resolves the visual index in sub_10230ED0: it reads the STORED index
    CRoomPiece[+0x170] (== prop 102 "VISUAL PIECE INDEX", getter sub_100B9B20) and
    uses it verbatim when in range (idx < visualCount). Only when the index is OUT
    of range (the -1/"RANDOM" sentinel) AND visualCount>1 does it draw a SEEDED RNG
    (sub_10285F80 "Rand Integer Between Seed"). Every one of the 1293 shipped
    layouts stores a concrete in-range VISUAL:N on every piece (N>=0; "VISUAL PIECE
    INDEX"/-1 is NEVER serialised), so the RNG branch is never taken offline.
  * The collision-mesh index is mapped from the visual index in sub_102317F0
    (@ 0x10231ba8 / 0x10231bd0): collisionIdx = visualIdx when collisionCount ==
    visualCount, else 0 (one shared collider); sub_1000CF20 clamps over-range to 0.
select_collision_file() reproduces this exactly. NB: the region master-AABB loop's
sub_1022FF80 gate (@ 0x10203fb8) is NOT a piece-exclusion test — it only routes a
piece into one of two accumulators that are both merged into the master box
afterwards (@ 0x102040c4); the real per-piece inclusion gate is COLLISION ENABLED
(CRoomPiece[+0x184], sub_10230CA0), which we already honour. Exhaustively traced the
whole per-piece body (0x10203b00..0x102040be): the ONLY box gates are (1) RTTI is
CRoomPiece, (2) COLLISION ENABLED [+0x184], (3) the CDamageShape exists & has faces
([entity+0x58]!=0 @ 0x10203ca2). NOPATH ([+0x192], getter sub_100B9990 / setter
sub_100B99C0) is read in the loop only to drive the sub_10068CB0 physics-world
collider REGISTRATION (the [+0x180]/[+0x191] branch @ 0x10203fc5) — it is a SIDE
EFFECT, NOT a box gate; a NOPATH piece still contributes its box. BAKE (prop 98) and
CHANCE (prop 107) are never serialised on any shipped room piece (confirmed: 0 of
the 1293 layouts carry CHANCE or BAKE on a Room Piece), so neither gates inclusion.

STRUCTURAL-EXIT LAYOUT-LINK BAKE (DETERMINISTIC; lifts 90.9% -> 91.2%, +4, 0 regr).
A connection tile carries an "Exit" <DESCRIPTOR>Layout Link whose <STRING>LAYOUT
FILE references a structural doorway prop layout (CAVE_EXIT / EXIT / ENTRANCE_EXIT /
CATACOMBS_EXIT / ...). That prop layout holds a collision-enabled Room Piece, and
the editor bakes it into the level so the region master-AABB loop sees it — the
shipped .MPP's connection-side face is extended one tile by that doorway whenever
its collision box crosses a tile boundary. _merge_structural_exit_links() reproduces
this: load the linked layout, transform its collision pieces by the LINK world
matrix, merge. PROVEN exact on 1X1_EXIT_N_JT_A (ACT2_CAVES: the -X "Exit" link to
CAVE_EXIT extends minx -36->-41.3 => snap -50, matching GT) and 1X1_EXIT_S_JT_A
(+Z link extends maxz 68->72.1 => snap 80). This is the ONLY Layout-Link target that
deterministically enters the region: blanket inclusion of ALL link geometry flips
+70 but REGRESSES 125 (the other links are FILLER_*/  *_SPAWNER_*/CHEST_*/LOOTABLE_*/
*RANDOMDUNGEON*/shrine/lamp/brazier props — runtime/random-instance content chosen
at bake time, NOT baked into a deterministic pathing region). Restricting to the
structural-exit targets gives +4/0 — see _STRUCT_EXIT_LAYOUTS.

HONEST RESIDUAL (~11% still off).  Two causes, both inherent to offline geometry —
neither is closeable without the runtime collision-world assembly state:
  - Multi-CHUNK procedurally-assembled levels (EXACTLY the 4 ACT1_PASS1 rooms
    PASS_JT_A/PASS_JD_A/PASS_PB_A/PASS1_LM_A, classified by rules.py: their level
    dir's RULES.TEMPLATE has >=2 [CHUNK_RANDOM] slots and GENERATION_TYPE 1, the
    road/pass assembler). The shipped .MPP is the editor's bake of the ASSEMBLED
    level: the assembler places random exit-matched NEIGHBOUR chunks into the empty
    slots, and the master-AABB region loop (only ACTIVE-random-group pieces, via
    sub_1022FF80 membership @ 0x10203fb8) spans them. PROOF it is a runtime instance
    and not a fixed declared envelope: each of these 4 rooms' shipped .MPP holds
    69k-104k PASSABLE cells lying OUTSIDE that room's ENTIRE piece span (road
    geometry present in NO single .LAYOUT; verified 0 layout pieces in the extension
    zones). e.g. PASS_JT_A footprint x[-80,180] z[-160,200] vs this room's geom
    x[-99,70] z[-11,192], with a separate +X road limb at x[100,180] and a -Z limb
    at z[-160,-20] belonging to neighbour chunks. Neighbour content is random-group
    selected at build time, so the union is genuinely seed/instance dependent and
    NOT reconstructible from one layout's collision merge. We FLAG these (pipeline
    `multichunk`) and report them as a separate class rather than fabricate the
    union. (GENERATION_TYPE 0 levels declare slots but bake an empty default region
    and stay byte-exact; single-slot PASS rooms in other acts ARE byte-exact.)
  - A residual set of leaf tiles (~110) that still miss by exactly one 10-tile on
    one axis even with the correct visual collider + structural-exit bake. They split
    two ways, BOTH proven non-closeable from one layout's static geometry:
      * "UNDER by 1" (B's box smaller than GT) on a connection face that has NO
        structural "Exit" link — the doorway/neighbour geometry that GT bakes is
        random/spawned link content (FILLER/SPAWNER/RANDOMDUNGEON), chosen at bake
        time, so the extension is a runtime instance (same root cause as the
        multi-CHUNK rooms, just one tile). Including it regresses far more than it
        fixes (the +70/-125 blanket-link result above).
      * "OVER by 1" (B's box LARGER than GT) on corner/wall tiles (e.g. 1X1_NW_BB_A,
        1X1_SE_PB_A): the editor's region is TIGHTER than the collision merge.
        PROOF it is not an inclusion rule we could apply: 1X1_NW_BB_A has 21
        collision-enabled pieces reaching x<-20 (out to -36), yet GT's region minx
        is -20 — no subset of THIS layout's pieces can produce a box tighter than
        its own geometry. GT's tighter box comes from the runtime collision-world
        assembly (neighbour-aware region clipping at bake), which the static layout
        does not carry.
    CHANCE/BAKE/NOPATH were each checked and ruled out as the gate (see above);
    these residual tiles carry no CHANCE/BAKE and NOPATH is not a box gate.
We do NOT snap harder or add a fudge epsilon to hide any of these. The model stays
the RE-grounded one (per-region 0.2-pad-snap-10 + active visual collider +
structural-exit Layout-Link bake).
"""
from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass

import numpy as np

from .geom import AABB, Matrix4, Vec3
from .layout import Layout, iter_room_pieces, load_layout_file
from .ogre_mesh import load_mesh_file

f32 = np.float32

# Editor constants (EditorGuts.dll). CELL/PAD are the float32 forms promoted to
# double in the DLL; we keep the float32 value so the origin rounds identically.
CELL = 0.4
CELL32 = f32(0.4)
PAD32 = f32(0.2)
EXPAND = 1.0
SNAP = 10.0  # editor tile boundary the region is quantized to

# Ablation-only per-piece face pad (NOT the editor's behaviour). The header model
# merges per-piece collision boxes UNPADDED and applies the editor's outward
# expansion as a per-REGION 0.2-pad-snap-to-10 (snap_box_outward). This 0.4 face
# pad is kept only so _transform_bounds_f32(pad=True) can reproduce the earlier,
# now-superseded model in tests/ablations; the pipeline never sets pad=True.
PIECE_PAD32 = f32(0.4)


def _resolve_mesh_path(media_dir: str, rel: str) -> str | None:
    if not rel:
        return None
    rel = rel.replace("/", os.sep).replace("\\", os.sep)
    # paths in DAT begin with "media/..." — strip a leading "media" component
    parts = rel.split(os.sep)
    if parts and parts[0].lower() == "media":
        rel2 = os.sep.join(parts[1:])
    else:
        rel2 = rel
    cand = os.path.join(media_dir, rel2)
    if os.path.exists(cand):
        return cand
    # case-insensitive fallback
    d = os.path.dirname(cand)
    base = os.path.basename(cand)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.lower() == base.lower():
                return os.path.join(d, fn)
    return None


class MeshBoundsCache:
    def __init__(self, media_dir: str):
        self.media_dir = media_dir
        self._cache: dict[str, AABB | None] = {}

    def bounds(self, rel: str) -> AABB | None:
        if rel in self._cache:
            return self._cache[rel]
        path = _resolve_mesh_path(self.media_dir, rel)
        box = None
        if path:
            try:
                mesh = load_mesh_file(path)
                if not mesh.bounds.null:
                    box = mesh.bounds
            except Exception:
                box = None
        self._cache[rel] = box
        return box


@dataclass
class RegionResult:
    aabb: AABB
    n_pieces_used: int
    n_pieces_missing: int


def _collision_enabled(piece) -> bool:
    """COLLISION ENABLED room-piece property. Absent => default true.

    RE: this is CRoomPiece byte [+0x184] (CRoomPieceDescriptor prop 97 "COLLISION
    ENABLED", set by sub_100B98B0->sub_10230EA0). It defaults to 1 in the ctor and
    is the gate the editor reads in the region master-AABB loop
    (sub_10230CA0 @ 0x10230ca0, checked at 0x10203b62): a piece with it cleared has
    its collision-mesh path blanked (sub_10230460 @ 0x102305ec) and contributes no
    collision box. COLLISION ENABLED:false is the only value ever serialised."""
    ce = piece.props.get("COLLISION ENABLED")
    if ce is None:
        return True
    return ce.strip().lower() != "false"


def select_collision_file(pd, visual: int) -> str:
    """Pick the room piece's ACTIVE collision mesh for a stored VISUAL index,
    exactly as the editor resolves it (sub_102317F0 / sub_10230ED0 / sub_1000CF20,
    EditorGuts.dll).

    A [PIECE] is a SET of visual sub-pieces (pd.files) with paired collision meshes
    (pd.collision_files). The editor:

      * resolves the visual index v (sub_10230ED0): the STORED index [+0x170] is
        used verbatim when it is in range (v < visualCount); when out of range
        (the -1/RANDOM sentinel) AND there is more than one visual, a SEEDED RNG
        ("Rand Integer Between Seed", sub_10285F80) draws one. The shipped layouts
        store a concrete in-range index on every piece (VISUAL:N, N>=0), so the
        RNG branch is never taken offline — the selection is deterministic.

      * maps the visual index to a collision index (sub_102317F0 @ 0x10231ba8):
        if collisionCount == visualCount  -> collisionIdx = v   (per-visual collider)
        else                              -> collisionIdx = 0   (one shared collider)
        with sub_1000CF20 clamping an over-range index back to entry 0.

    We mirror that exactly. For the unreproducible RNG case (stored index out of
    range, count>1 — vanishingly rare: ~28 piece instances across all 1293 layouts)
    we fall back to index 0 rather than fabricate a seed; it cannot regress a
    byte-exact template (none of them hit it)."""
    colls = pd.collision_files or ((pd.collision_file,) if pd.collision_file else ())
    if not colls:
        return ""
    nvis = len(pd.files) if pd.files else len(colls)
    ncol = len(colls)
    v = visual
    # sub_10230ED0: in-range stored index used as-is; otherwise (RNG/-1) -> 0.
    if not (0 <= v < max(nvis, 1)):
        v = 0
    # sub_102317F0: per-visual collider only when counts match, else shared idx 0.
    col_idx = v if ncol == nvis else 0
    if col_idx >= ncol or col_idx < 0:   # sub_1000CF20 clamp
        col_idx = 0
    return colls[col_idx]


def _transform_bounds_f32(box: AABB, m, pad: bool = False) -> tuple[float, float, float, float]:
    """Ogre AxisAlignedBox::transform of a mesh-bounds AABB by a world matrix,
    refit around the 8 transformed corners, done in float32. Returns the X/Z
    extents (minx, minz, maxx, maxz) as Python floats holding float32 values.

    `pad` defaults OFF: the editor does NOT pad the per-piece box before merging
    it into the region accumulator — the per-region box is the raw refit collision
    AABB, and the only outward expansion is the +-0.2-then-snap-to-10 quantization
    applied to the whole region box (snap_box_outward / RE @ 0x102043af..0x10204511).
    The `pad=True` branch (a +-0.4 face pad) is retained only for ablation; it is
    NOT the editor's behaviour and is unused by the pipeline."""
    mn, mx = box.min, box.max
    M = [[f32(m[r][c]) for c in range(4)] for r in range(4)]
    corners = (
        (mn.x, mn.y, mn.z), (mx.x, mn.y, mn.z), (mn.x, mx.y, mn.z), (mx.x, mx.y, mn.z),
        (mn.x, mn.y, mx.z), (mx.x, mn.y, mx.z), (mn.x, mx.y, mx.z), (mx.x, mx.y, mx.z),
    )
    minx = minz = f32(np.inf)
    maxx = maxz = f32(-np.inf)
    for (cx, cy, cz) in corners:
        cx, cy, cz = f32(cx), f32(cy), f32(cz)
        x = f32(f32(f32(M[0][0] * cx) + f32(M[0][1] * cy)) + f32(f32(M[0][2] * cz) + M[0][3]))
        z = f32(f32(f32(M[2][0] * cx) + f32(M[2][1] * cy)) + f32(f32(M[2][2] * cz) + M[2][3]))
        minx = min(minx, x)
        maxx = max(maxx, x)
        minz = min(minz, z)
        maxz = max(maxz, z)
    if pad:
        minx = f32(minx - PIECE_PAD32); minz = f32(minz - PIECE_PAD32)
        maxx = f32(maxx + PIECE_PAD32); maxz = f32(maxz + PIECE_PAD32)
    return float(minx), float(minz), float(maxx), float(maxz)


# Structural EXIT doorway prop layouts that a connection tile's "Exit" Layout Link
# instantiates. The editor bakes their collision geometry into the pathing region
# (the doorway is a permanent structural connection, unlike random/spawned link
# content). These are the ONLY Layout-Link targets that deterministically enter the
# region master AABB; everything else a tile links to (FILLER_*, *_SPAWNER_*,
# CHEST_*, LOOTABLE_*, *RANDOMDUNGEON*, shrines, lamps, braziers, portals) is
# runtime/random-instance content and is NOT baked (verified: blanket link
# inclusion flips +70 but regresses 125 over the 1293 GT files; structural-exit
# inclusion flips +4 with 0 regressions). See the EXIT residual note below.
_STRUCT_EXIT_LAYOUTS = frozenset((
    "EXIT.LAYOUT", "CAVE_EXIT.LAYOUT", "ENTRANCE_EXIT.LAYOUT",
    "CATACOMBS_EXIT.LAYOUT", "EXIT_01.LAYOUT", "EXIT_TOWER.LAYOUT",
    "CAVEEXIT_LIT.LAYOUT", "ARENA_EXIT.LAYOUT", "ARENA_EXIT2.LAYOUT",
))


def _resolve_link_layout(media_dir: str, link_file: str) -> str | None:
    """Resolve a Layout Link's `LAYOUT FILE` (a 'MEDIA/...' relative path) to an
    absolute .LAYOUT path on disk, case-insensitively."""
    if not link_file:
        return None
    rel = link_file.replace("/", os.sep).replace("\\", os.sep)
    parts = rel.split(os.sep)
    if parts and parts[0].lower() == "media":
        rel = os.sep.join(parts[1:])
    cand = os.path.join(media_dir, rel)
    if os.path.exists(cand):
        return cand
    d = os.path.dirname(cand)
    base = os.path.basename(cand)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.lower() == base.lower():
                return os.path.join(d, fn)
    return None


def _is_structural_exit_link(obj) -> bool:
    """A Layout Link whose target is a structural EXIT doorway prop (baked into the
    pathing region), distinguished from random/spawned/decorative links."""
    if obj.descriptor != "Layout Link":
        return False
    base = os.path.basename(obj.props.get("LAYOUT FILE", "")).upper()
    return base in _STRUCT_EXIT_LAYOUTS


def _merge_structural_exit_links(layout: Layout, ctx, get_bounds, extents):
    """Merge each structural EXIT Layout-Link sub-layout's collision-enabled room
    pieces (transformed by the LINK world transform) into the running X/Z extents.

    The shipped .MPP bakes a connection tile's exit DOORWAY geometry into the
    pathing region: the room's "Exit" Layout Link references a structural prop
    layout (CAVE_EXIT / EXIT / ENTRANCE_EXIT / ...) holding a collision Room Piece,
    and the editor's region loop sees that baked piece. We reproduce it by loading
    the linked layout and merging its collision pieces under the link's world
    matrix. Returns the updated (minx, maxx, minz, maxz, used) tuple."""
    minx, maxx, minz, maxz, used = extents
    link_cache: dict[str, Layout | None] = {}
    for obj in layout.all_objects:
        if not _is_structural_exit_link(obj):
            continue
        link_file = obj.props.get("LAYOUT FILE", "")
        sub_path = _resolve_link_layout(ctx.media_dir, link_file)
        if not sub_path:
            continue
        if sub_path in link_cache:
            sub = link_cache[sub_path]
        else:
            try:
                sub = load_layout_file(sub_path)
            except Exception:
                sub = None
            link_cache[sub_path] = sub
        if sub is None:
            continue
        link_world = obj._world or obj.local_matrix()
        for piece in iter_room_pieces(sub):
            if not _collision_enabled(piece):
                continue
            pd = ctx.guid.get(piece.guid)
            if pd is None:
                continue
            coll = select_collision_file(pd, piece.visual)
            if not coll:
                continue
            b = get_bounds(coll)
            if b is None:
                continue
            pw = piece._world or piece.local_matrix()
            world = link_world @ pw
            pmnx, pmnz, pmxx, pmxz = _transform_bounds_f32(b, world.m)
            minx = min(minx, f32(pmnx)); maxx = max(maxx, f32(pmxx))
            minz = min(minz, f32(pmnz)); maxz = max(maxz, f32(pmxz))
            used += 1
    return minx, maxx, minz, maxz, used


def compute_region_aabb_collision(layout: Layout, ctx) -> RegionResult:
    """Region AABB (X,Z) = merge of each collision-enabled room-piece's COLLISION
    mesh M_MESH_BOUNDS, transformed to world (float32), then quantized OUTWARD to
    the editor's 10-unit tile boundary.

    This is the RE-correct per-piece source for the header: the same collision
    mesh the cell classifier raycasts (raycast.gather_collision_triangles), so the
    header box and the cells come from one consistent geometry source. A piece
    with no COLLISIONFILE or COLLISION ENABLED:false contributes nothing. The
    per-piece world AABB is merged UNPADDED; the only outward expansion is the
    +-0.2-then-snap-to-10 quantization applied to the merged region box
    (snap_box_outward), exactly as the editor snaps each region box before merging
    into the master level AABB (RebuildLevel @ 0x102043af..0x10204511).
    """
    mesh_cache: dict[str, AABB | None] = {}

    def get_bounds(rel):
        if rel in mesh_cache:
            return mesh_cache[rel]
        path = _resolve_mesh_path(ctx.media_dir, rel)
        b = None
        if path:
            try:
                mesh = load_mesh_file(path)
                if not mesh.bounds.null:
                    b = mesh.bounds
            except Exception:
                b = None
        mesh_cache[rel] = b
        return b

    minx = minz = f32(np.inf)
    maxx = maxz = f32(-np.inf)
    used = 0
    missing = 0
    for piece in iter_room_pieces(layout):
        if not _collision_enabled(piece):
            continue
        pd = ctx.guid.get(piece.guid)
        if pd is None:
            continue
        # the ACTIVE collision mesh for this instance's stored VISUAL index
        coll = select_collision_file(pd, piece.visual)
        if not coll:
            continue
        b = get_bounds(coll)
        if b is None:
            missing += 1
            continue
        w = piece._world or piece.local_matrix()
        pmnx, pmnz, pmxx, pmxz = _transform_bounds_f32(b, w.m)
        minx = min(minx, f32(pmnx)); maxx = max(maxx, f32(pmxx))
        minz = min(minz, f32(pmnz)); maxz = max(maxz, f32(pmxz))
        used += 1

    # Bake the structural EXIT doorway geometry the tile's "Exit" Layout Link
    # instantiates (deterministic; extends the connection-side face by one tile on
    # the EXIT_N/EXIT_S-type tiles whose doorway collision crosses a tile boundary).
    minx, maxx, minz, maxz, used = _merge_structural_exit_links(
        layout, ctx, get_bounds, (minx, maxx, minz, maxz, used))

    if used == 0:
        return RegionResult(AABB(), 0, missing)
    box = AABB(Vec3(float(minx), 0.0, float(minz)),
               Vec3(float(maxx), 0.0, float(maxz)))
    return RegionResult(box, used, missing)


def snap_box_outward(box: AABB, quantum: float = SNAP) -> AABB:
    """Quantize a (X,Z) AABB OUTWARD to the 10-unit editor tile boundary, EXACTLY
    as the editor snaps each pathing-region box before merging it into the master
    level AABB (CLevel_RebuildLevel_GenPathing @ 0x102043af .. 0x10204511):

        snappedMin = floor((min - 0.2) / 10) * 10      (per X/Z face)
        snappedMax = ceil ((max + 0.2) / 10) * 10

    i.e. a 0.2 pad is applied to each face BEFORE the floor/ceil to 10. The pad is
    what lifts a hull that sits exactly on (or a hair inside) a 10-multiple out to
    the next tile, matching the shipped bounds floats. The divide / floor / ceil /
    multiply are all done in float32 in the DLL, so we round each step to float32 —
    that is load-bearing at the ULP boundaries the snap straddles.

    The constants are dbl_11E50E88 = 0.2 (PAD) and dbl_11E7ED10 = 10.0 (SNAP). Y is
    left untouched. `quantum` is kept as a parameter only for the --no-snap ablation
    (quantum=0 disables snapping upstream); the 0.2 pad is tied to the 10 boundary.
    """
    if box.null:
        return AABB()
    q = f32(quantum)
    pad = f32(0.2)

    def lo(v):
        t = f32((f32(v) - pad) / q)
        return float(f32(f32(math.floor(t)) * q))

    def hi(v):
        t = f32((f32(v) + pad) / q)
        return float(f32(f32(math.ceil(t)) * q))

    return AABB(Vec3(lo(box.min.x), box.min.y, lo(box.min.z)),
                Vec3(hi(box.max.x), box.max.y, hi(box.max.z)))


def grid_origin(box_min: Vec3) -> tuple[float, float]:
    """CLevel grid origin (RebuildLevel @ 0x10204FD0), float32:

        origin = float32((floor((float32(min) - 0.2)/0.4) - 1.0) * 0.4)

    Computed per axis from the (master==region) box minimum. The intermediate
    floor/divide promote to double in the DLL, but the stored origin is a float32,
    so we round the product to float32 — that rounding drives the +1 grid straddle.
    """
    def _ax(mn: float) -> float:
        t = (np.float64(f32(mn)) - np.float64(PAD32)) / np.float64(CELL32)
        t = math.floor(t)
        return float(f32((t - EXPAND) * float(CELL32)))

    return _ax(box_min.x), _ax(box_min.z)


def grid_dims(box_min: Vec3, box_max: Vec3, ox: float, oz: float):
    """Writer grid-dim formula, exactly (float32 divide, floor/ceil):

        gridW = ceil((box_max.x - ox)/0.4) - floor((box_min.x - ox)/0.4)
        gridH = ceil((box_max.z - oz)/0.4) - floor((box_min.z - oz)/0.4)
    """
    def _floor(coord, o):
        return int(math.floor(float(f32((f32(coord) - f32(o)) / CELL32))))

    def _ceil(coord, o):
        return int(math.ceil(float(f32((f32(coord) - f32(o)) / CELL32))))

    gw = _ceil(box_max.x, ox) - _floor(box_min.x, ox)
    gh = _ceil(box_max.z, oz) - _floor(box_min.z, oz)
    return gw, gh


def header_floats(box_min: Vec3, box_max: Vec3, world_ext: Vec3):
    worldW = f32(world_ext.x) - f32(box_min.x)
    worldD = f32(world_ext.z) - f32(box_min.z)
    boundsW = f32(box_max.x) - f32(box_min.x)
    boundsD = f32(box_max.z) - f32(box_min.z)
    return float(worldW), float(worldD), float(boundsW), float(boundsD)


def pack_header(gridW: int, gridH: int, worldW: float, worldD: float,
                boundsW: float, boundsD: float) -> bytes:
    return struct.pack("<iiffff", gridW, gridH,
                       f32(worldW), f32(worldD),
                       f32(boundsW), f32(boundsD))
