"""
native.py — a FAITHFUL, un-optimized port of Torchlight 2's MPP pathing-grid
generator, mirroring EditorGuts.dll function-by-function (RE'd via idalib in this
project's deep-dive). Correctness over speed: pure-Python nested loops over
cells x colliders x triangles, no numpy vectorization, no spatial culling beyond
the editor's own behaviour.

This is the clean-room re-implementation of CLevel_BuildWritePathingGrid_MPP,
written straight from the disassembly rather than from approximations.

SOURCE MAP (EditorGuts.dll, ImageBase 0x10000000):
  build_grid          <- CLevel_BuildWritePathingGrid_MPP   @ 0x10200920
  multi_raycast       <- sub_101EF170  (nearest-of-all-colliders down-ray)
  swept_tri           <- sub_10067670  (BVH leaf: ray-plane hit + in-tri / radius-edge,
                                         the radius-edge branch gated by sub_10293B50)
  ray_plane           <- sub_10293D50  (ray vs the triangle's plane)
  (side gate)         <- sub_10293B50  (signed plane side: dot(vertA - p, n) vs +/-1e-5)
  point_in_tri        <- sub_10066E50  (is the plane hit inside the triangle)
  clearance_blocked   <- the four sub_101EEEA0 probes
  enclosure_pass      <- the `if(!v69)` second pass inside 0x10200920
  per-triangle NOPATH = piece NOPATH property OR a `nocollide` collision submesh.
  This is the editor's ACTUAL source (RE-confirmed, NOT a slope proxy):
    * CRoomPieceDescriptor prop 110 (sub_100BA140) -> whole-piece NOPATH: the bake
      (sub_10203710 @0x10205ede) sets the collision type to 100 for NOPATH pieces.
    * For non-NOPATH pieces, sub_10068CB0 COPIES the per-triangle type from the
      collision mesh's OWN type array (a2[49]); the artists author that as the
      `multi_collision/nocollide` submesh (the non-pathable walls).
  NO SLOPE IS COMPUTED ANYWHERE — the MPP classifier (0x10200920), the pathing bake
  (0x10203710 -> 0x10068CB0) and the whole collision module contain no slope->NOPATH
  test (verified: no `store 100` in 0x10066000..0x1006A000). An earlier "steep >
  30deg" geometric proxy scored worse: BB_A 81 vs 21 diffs, PB_A 188 vs 27.
"""
from __future__ import annotations

import math
import os
import struct

from .layout import iter_room_pieces
from .region import _resolve_mesh_path, select_collision_file  # noqa: F401

# ---- constants, read straight from sub_10200920 / sub_101EF170 ----
CELL = 0.4                  # pathing cell size (world units)
HALF = 0.2                  # cell-center offset (i*0.4 + 0.2)
RADIUS = 0.10000001         # down-ray swept-capsule radius (sub_101EF170 a4 = 0.1f)
CLEARANCE_RADIUS = 0.0      # clearance probe is a THIN segment (sub_101EEEA0 takes no
                            # radius arg, unlike the down-ray) — a 0.1 capsule here
                            # over-blocks (BB_A 21 vs 12, PB_A 27 vs 24 diffs)
CLEARANCE_LEN = 0.30000001  # clearance probe length (Vector3(0.30000001,0,0) in 0x10200920)
CLEARANCE_LIFT = 1.5        # head height above the ground hit (v86.y = v89 + 1.5)
HEIGHT_CLAMP = 80.0         # gate: |hit.y| > 80 -> wall (flt_11E51004 / flt_11E87054; never fires)
NOCOLLIDE_MAT = "nocollide" # collision-submesh material that marks NOPATH walls
SIDE_EPS = 9.9999997e-06    # sub_10293B50 plane-side deadband (the editor's exact 1e-5)
# Layout-Link targets that are RUNTIME / RANDOM / spawned content the editor does NOT bake
# into the master pass collision (case-insensitive substrings of the LAYOUT FILE basename).
# Structural geometry links (STAIRS/MANA_CRACK/CHIMNEY/VAULT_FLOOR_TRAP/FLOOR_*/...) are NOT
# matched and ARE baked. Used only by gather(assemble_links=True). See that flag's note.
# Layout-Link targets whose sub-layout is RUNTIME / RANDOMIZED / SPAWN content the editor leaves
# out of the .mpp. A name fallback for links NOT under a feature-tagged group (see
# _link_under_feature_tagged_group, the principled signal): a few runtime sub-layouts sit directly
# under an untagged container yet are still spawn content.
# NOTE: NOT "RANDOM" — it false-positives on "..._RANDOMIZED" STRUCTURAL pieces (e.g.
# TUTARAN_CAVEBASE_02_RANDOMIZED, the nocollide mesa/canyon base the editor DOES bake -> wall;
# DLL-hook ground truth: the .mpp pass#1 down-ray hits it type-100 at the mesa-top cells).
# Real runtime random content (RandomEvents/RandomDungeonEntrances) is caught by the Random*
# group-NAME filter (_in_backdrop_group) and the feature-TAG filter instead.
# NOT "SHRINE": the structural LANDMARK shrine PB_SHRINE_MAIN (169 collision pieces, the shrine
# building/floor the editor bakes) matched it; runtime loot shrines are ALL_LOOTABLE_SHRINES
# (caught by "LOOTABLE"). SHRINE was a structural false-positive (w2V 9093->0 on LANDMARK_SHRINES).
_RUNTIME_LINK_SUBSTR = (
    "FILLER", "CHEST", "LOOTABLE",
    "ADVENTURER", "DAPPLE", "BONEPILE", "SUNDIAL", "FISHINGHOLE", "BIGMONSTER",
)


def _link_under_feature_tagged_group(layout, obj):
    """The editor's master-collision base/detail split (RE'd: CLevel_RebuildLevel_GenPathing,
    sub_1022FF80) excludes pieces under a CRandomGroup that is FEATURE-TAGGED — a CRandomGroup
    whose theme/feature string [+540] is non-empty (EditorGroupNodeIsFeatureTagged @0x100eee90)
    and doesn't match the bake's active theme. In the .LAYOUT that feature string is the group's
    <STRING>TAG. So a Layout-Link is runtime/conditional content (NOT in the .mpp) iff any of its
    ancestor groups carries a non-empty TAG — e.g. MerchantShip (TAG 'A2-MERCHANTSHIP'), chests
    (CHESTS*), shrines (SHRINE*), dead adventurers (DEADADVENTURERS), region spawns (A2-*). A
    structural placed sub-layout sits under an UNTAGGED group (e.g. METALSHIP under 'decoration')
    and stays in. This is the generic, offline form of the editor's RTTI feature-tag check; the
    _RUNTIME_LINK_SUBSTR name list is only a fallback for spawn links under an untagged parent."""
    by_id = getattr(layout, "by_id", None)
    if not by_id:
        return False
    pid = obj.props.get("PARENTID")
    seen = 0
    while pid and pid != "-1" and seen < 24:
        o = by_id.get(pid) or by_id.get(str(pid))
        if o is None:
            break
        if (o.props.get("TAG") or "").strip() or (o.props.get("ACTIVE THEMES") or "").strip():
            return True
        pid = o.props.get("PARENTID") if hasattr(o, "props") else None
        seen += 1
    return False


# ---- tiny Vector3 helpers (plain float tuples) ----
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])
def _len(a): return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


# ---- sub_10293D50: ray (s->e) vs the plane through p0 with normal n ----
def ray_plane(s, e, p0, n):
    """Returns the plane-crossing point, or None if the ray is parallel to the
    plane (|n.dir| < 1e-5, the editor's exact reject threshold)."""
    dx, dy, dz = e[0] - s[0], e[1] - s[1], e[2] - s[2]
    denom = n[0] * dx + n[1] * dy + n[2] * dz
    if abs(denom) < 9.9999997e-06:
        return None
    t = (n[0] * (p0[0] - s[0]) + n[1] * (p0[1] - s[1]) + n[2] * (p0[2] - s[2])) / denom
    return (s[0] + dx * t, s[1] + dy * t, s[2] + dz * t)


# ---- sub_10066E50: is the plane-hit point inside the triangle (barycentric) ----
def point_in_tri(p, a, b, c):
    v0 = _sub(c, a); v1 = _sub(b, a); v2 = _sub(p, a)
    d00 = _dot(v0, v0); d01 = _dot(v0, v1); d02 = _dot(v0, v2)
    d11 = _dot(v1, v1); d12 = _dot(v1, v2)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return False
    inv = 1.0 / den
    u = (d11 * d02 - d01 * d12) * inv
    v = (d00 * d12 - d01 * d02) * inv
    return u >= -1e-6 and v >= -1e-6 and (u + v) <= 1.0 + 1e-6


# ---- closest point on triangle (Ericson RTCD): the swept-radius edge rounding ----
def closest_on_tri(p, a, b, c):
    ab = _sub(b, a); ac = _sub(c, a); ap = _sub(p, a)
    d1 = _dot(ab, ap); d2 = _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = _sub(p, b); d3 = _dot(ab, bp); d4 = _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return (a[0] + ab[0] * v, a[1] + ab[1] * v, a[2] + ab[2] * v)
    cp = _sub(p, c); d5 = _dot(ab, cp); d6 = _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return (a[0] + ac[0] * w, a[1] + ac[1] * w, a[2] + ac[2] * w)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (b[0] + (c[0] - b[0]) * w, b[1] + (c[1] - b[1]) * w, b[2] + (c[2] - b[2]) * w)
    den = 1.0 / (va + vb + vc)
    v = vb * den; w = vc * den
    return (a[0] + ab[0] * v + ac[0] * w,
            a[1] + ab[1] * v + ac[1] * w,
            a[2] + ab[2] * v + ac[2] * w)


# ---- sub_10067670 BVH leaf: swept (radius) ray vs one triangle ----
def swept_tri(s, e, radius, a, b, c):
    """Ray-plane hit; if inside the triangle the hit is the plane point; else if the
    plane point is within `radius` of the triangle, the hit rounds to the closest
    point on the triangle (the capsule edge). Returns (hitpoint, dist_from_s) or
    None. A ray parallel to the plane (a vertical down-ray vs a vertical wall) never
    hits here — such walls are found only by the horizontal clearance probes."""
    n = _cross(_sub(b, a), _sub(c, a))
    hp = ray_plane(s, e, a, n)
    if hp is None:
        return None
    # the plane crossing must lie ON the segment [s,e] (within the radius slack),
    # not just on the infinite line — else a 0.3 clearance probe would "hit" any
    # far plane the line crosses. (For the 400-unit down-ray this is always true.)
    dx, dy, dz = e[0] - s[0], e[1] - s[1], e[2] - s[2]
    seg2 = dx * dx + dy * dy + dz * dz
    t = ((hp[0] - s[0]) * dx + (hp[1] - s[1]) * dy + (hp[2] - s[2]) * dz) / seg2
    slack = radius / math.sqrt(seg2)
    if t < -slack or t > 1.0 + slack:
        return None
    if point_in_tri(hp, a, b, c):
        return hp, _len(_sub(hp, s))
    cp = closest_on_tri(hp, a, b, c)
    if _len(_sub(cp, hp)) <= radius:
        # sub_10067670's radius-edge branch is gated by sub_10293B50(rayEnd, vertA, n) == 0,
        # i.e. dot(vertA - e, n) < -1e-5: accept the capsule-edge (grazing) hit only when the
        # ray END is strictly on the +normal (front) side of the triangle's plane. This is the
        # leaf's back-face cull for grazes: a vertical down-ray skimming the EDGE of an elevated
        # NOPATH platform (top face, normal up; e is far below -> dot >> 0) is REJECTED so the
        # cell stays walkable (matching the DLL), while an underside-facing NOPATH (normal down)
        # is still caught. Without this the 0.1 capsule over-catches platform edges as walls
        # (BB_A 12->4 diffs, PB_A's 6 spurious interior walls removed, mainmenu_town3 9->0).
        # n is the raw cross(b-a,c-a) as elsewhere here; vertical walls (n.y~0) never reach this
        # branch (ray_plane rejects the parallel ray), so leaving n un-normalised is exact.
        if _dot(_sub(a, e), n) < -SIDE_EPS:
            return cp, _len(_sub(cp, s))
    return None


# ---- sub_101EF170: nearest hit over every collider triangle ----
def multi_raycast(s, e, radius, tris):
    """`tris` = list of (a, b, c, nopath). Returns (hitpoint, hitType) of the
    nearest hit (min Vector3::length from s = topmost), or None. hitType = 100 if
    the winning triangle is NOPATH, else 0 (the editor's hitType==100 wall flag)."""
    best_d = None; best_hp = None; best_nop = False
    for (a, b, c, nop) in tris:
        r = swept_tri(s, e, radius, a, b, c)
        if r is None:
            continue
        hp, d = r
        if best_d is None or d < best_d:
            best_d = d; best_hp = hp; best_nop = nop
    if best_d is None:
        return None
    return best_hp, (100 if best_nop else 0)


# ---- the four sub_101EEEA0 clearance probes ----
def clearance_blocked(origin, nopath_tris, radius):
    """From the ground hit raised +1.5 (head height), cast 4 horizontal segments of
    length 0.30000001 in +/-X / +/-Z; block the cell if ANY hits a NOPATH triangle
    (hitType==100). A vertical NOPATH wall beside the cell is found here (the
    horizontal segment crosses the vertical wall plane)."""
    for ox, oz in ((CLEARANCE_LEN, 0.0), (-CLEARANCE_LEN, 0.0),
                   (0.0, CLEARANCE_LEN), (0.0, -CLEARANCE_LEN)):
        e = (origin[0] + ox, origin[1], origin[2] + oz)
        for (a, b, c) in nopath_tris:
            if swept_tri(origin, e, radius, a, b, c) is not None:
                return True
    return False


# ---- the `if(!v69)` second pass: wall off cells pinched on any of the 4 axes ----
def enclosure_pass(grid, gw, gh):
    """In-place, X-outer Z-inner (the editor's order, so it cascades): wall a
    walkable cell if both ends of any axis (H, V, the two diagonals) are blocked,
    where blocked = grid edge or a wall(1); an oob(0xFF) cell counts as open."""
    def blk(x, z):
        if x < 0 or z < 0 or x >= gw or z >= gh:
            return True
        return grid[z * gw + x] == 1
    for x in range(gw):
        for z in range(gh):
            if grid[z * gw + x] != 0:
                continue
            if ((blk(x - 1, z) and blk(x + 1, z)) or
                (blk(x, z - 1) and blk(x, z + 1)) or
                (blk(x - 1, z - 1) and blk(x + 1, z + 1)) or
                (blk(x + 1, z - 1) and blk(x - 1, z + 1))):
                grid[z * gw + x] = 1


REACH_STEP = 2.0          # max walkable height step between adjacent cells for connectivity
REACH_ELEVATION = 2.0     # a disconnected component is only voided if its floor sits this
                          # far ABOVE the main ground component (elevated scenery)


def reachability_void(grid, heights, gw, gh, step=REACH_STEP, elevation=REACH_ELEVATION):
    """In-place: void (0xFF) walkable cells that form a component which is BOTH
    disconnected from the main ground component (height-aware 4-neighbour adjacency,
    connect only if |dH| <= step) AND elevated (its median floor height is >= `elevation`
    above the main component's median).

    The editor's MPP navigates the CONNECTED GROUND-LEVEL surface and EXCLUDES
    disconnected ELEVATED scenery (platforms/dunes) from the classifier's master
    collision -> those become void; native's single global topmost-hit raycast instead
    fills them. The elevation guard is essential: ground floors split into pieces by
    walls (boss rooms, caves) are disconnected but NOT elevated -> they must NOT be
    voided (otherwise the corpus regresses ~740 tiles). No-op on single-surface tiles
    (BB_A = one component)."""
    n_cells = gw * gh
    walk = bytearray(1 if grid[i] == 0 else 0 for i in range(n_cells))
    comp = [0] * n_cells
    members = {}
    cid = 0
    stack = []
    for s in range(n_cells):
        if not walk[s] or comp[s]:
            continue
        cid += 1
        comp[s] = cid
        m = [s]
        stack.append(s)
        while stack:
            p = stack.pop()
            x = p % gw
            z = p // gw
            hp = heights[p]
            for nx, nz in ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1)):
                if 0 <= nx < gw and 0 <= nz < gh:
                    nn = nz * gw + nx
                    if walk[nn] and not comp[nn]:
                        hn = heights[nn]
                        if hp is None or hn is None or abs(hn - hp) <= step:
                            comp[nn] = cid
                            m.append(nn)
                            stack.append(nn)
        members[cid] = m
    if not members:
        return

    def med_h(cells):
        hs = sorted(heights[c] for c in cells if heights[c] is not None)
        return hs[len(hs) // 2] if hs else 0.0

    main = max(members, key=lambda c: len(members[c]))
    main_h = med_h(members[main])
    for c, cells in members.items():
        if c == main:
            continue
        if med_h(cells) - main_h >= elevation:      # disconnected AND elevated -> void
            for i in cells:
                grid[i] = 0xFF


def _xform(M, v):
    return (M[0][0] * v.x + M[0][1] * v.y + M[0][2] * v.z + M[0][3],
            M[1][0] * v.x + M[1][1] * v.y + M[1][2] * v.z + M[1][3],
            M[2][0] * v.x + M[2][1] * v.y + M[2][2] * v.z + M[2][3])


def _in_backdrop_group(layout, piece, weighted=False):
    """The .mpp's whole-tile master pass (the only pass written to the file — RE'd from the
    404-pass driver sub_10203710: the .mpp = pass#1 over the BASE collision subset, NOT the
    later per-piece passes) builds its collision from the main room/scenery groups ONLY. The
    editor's RANDOMIZED / VARIATION backdrop groups — alternate visual-only scenery placed for
    distant variety (GUTS calls these "Randomized"/"Variations": e.g. Buildings/Ruins/Var Top
    Liner under a "Var*" container, or a "Random"/"Randomization" set) — are EXCLUDED from the
    pathing collision. Walk the piece's Group ancestry; return True if any ancestor group is a
    Var* / Variation* / Random* backdrop group. Excluding these takes OPEN/cave/catacomb tiles
    from ~72-95% to ~99% byte-match with ZERO room-tile regression (room tiles have no such
    group, so the filter is a no-op there). The "Randomized" backdrop convention is documented
    for the GUTS editor (random alternative piece set); "VarkProps" etc. are NOT matched.

    `weighted` (used for Layout-Link sub-pieces): also exclude pieces under any group with
    CHOICE=='Weight' — that is the editor's actual CRandomGroup marker (a weighted variation
    roll), independent of the group NAME. The master-collision add gate (RE'd, sub_1022FF80 @
    CLevel_RebuildLevel_GenPathing 0x10203710) skips a piece whose ancestor is a CRandomGroup
    with its selection-flag inactive; since native cannot reproduce the runtime roll, it
    conservatively excludes ALL weighted-variation children. Link sub-layouts use UNNAMED
    weighted groups ("Group"/"glowy"/"0".."3", e.g. FLOOR_WITH_LIGHTBEAMS_01) that the
    name-only filter misses; without this, assembling those links over-floors VOID cells
    (DWARVENLAB 1X1_NS_PB_A diff 2006->0 byte-exact with this on)."""
    by_id = getattr(layout, "by_id", None)
    if not by_id:
        return False
    pid = piece.props.get("PARENTID")
    seen = 0
    while pid and pid != "-1" and seen < 16:
        o = by_id.get(pid) or by_id.get(str(pid))
        if o is None:
            break
        nm = (o.props.get("NAME") or "") if hasattr(o, "props") else ""
        if (nm == "Var" or nm.startswith("Var ")
                or nm.startswith("Variation") or nm.startswith("Random")):
            return True
        # CRandomGroup conditional-load gates excluded from the .mpp master collision
        # (sub_1022FF80 / EditorGroupNodeHasTheme, CRandomGroup props from sub_100B7990):
        #  - CHOICE != 0 (id 101): a randomization MODE (Weight / 'Random Chance') — the whole
        #    group's variants are left out (the pick is a runtime roll, never baked).
        #  - ACTIVE THEMES: a theme/feature requirement the bake doesn't activate -> excluded
        #    (DLL-hook ground truth: GENERIC_CAVE 'Goblins' group ACTIVE THEMES=... -> its props
        #    appear only in later a7=1 passes, NOT pass#1's .mpp collision -> native over-walled).
        # A non-empty CHOICE or ACTIVE THEMES on ANY ancestor group => excluded.
        if (o.props.get("CHOICE") or "").strip() or (o.props.get("ACTIVE THEMES") or "").strip():
            return True
        pid = o.props.get("PARENTID") if hasattr(o, "props") else None
        seen += 1
    return False


def _collision_enabled(piece) -> bool:
    """A room piece contributes pathing collision unless it carries
    `COLLISION ENABLED=false` (the editor's collider early-out). Default TRUE when
    the property is absent."""
    ce = piece.props.get("COLLISION ENABLED")
    return not (ce is not None and ce.strip().lower() == "false")


def gather(layout, ctx, assemble_links=False):
    """Collect world-space collision triangles with the per-triangle NOPATH flag:
    NOPATH = (piece NOPATH property) OR (the submesh is a `nocollide` collision
    submesh). No slope — this is the editor's authored source (see module docstring).
    Iterates submeshes (not the flattened triangle stream) so each triangle carries
    its submesh's material. Pieces with no COLLISIONFILE or COLLISION ENABLED=false
    contribute nothing (matches the editor's collider early-out). Returns list of
    (a, b, c, nopath).

    `assemble_links` (default OFF, OPT-IN): also assemble one level of structural
    Layout-Link sub-layout collision (link_world @ piece_local), EXCLUDING links flagged
    NO ROOMPIECE COLLISION=true or whose target is runtime/random content
    (_RUNTIME_LINK_SUBSTR). This fixes the missing floor (w2V) on VAULT/MANAVENT/boss tiles
    whose floor lives in STAIRS/VAULT_FLOOR_TRAP/FLOOR_* sub-layouts (per-tile wins:
    ESTHSHRINE_E_JT_B 86->95%, MANAVENT_EW_JT_B 95->99.6%, VAULT_SE_JT_A 88->92%). It is OFF
    by default because the link sub-layouts' nocollide/machinery submeshes hit native's
    nocollide OVER-WALLING (the unrecoverable authored-collision-type issue): corpus pathing
    98.96%->98.91% (w2V/W2w drop but w2W/V2w rise). Enable per-tile when the missing floor
    matters more than the over-wall (special/boss tiles)."""
    from .ogre_mesh import load_mesh_file
    # Reuse the Context's cross-tile geometry cache when present (parsed mesh is
    # read-only downstream, so sharing across tiles is safe); fall back to a local
    # per-call cache for any Context built without it.
    cache = ctx.__dict__.setdefault("mesh_geom_cache", {})

    def get_mesh(rel):
        if rel in cache:
            return cache[rel]
        path = _resolve_mesh_path(ctx.media_dir, rel)
        m = None
        if path:
            try:
                m = load_mesh_file(path)
            except Exception:
                m = None
        cache[rel] = m
        return m

    tris = []

    def emit_piece(piece, M):
        """Append `piece`'s world-space (matrix M) collision triangles to `tris`."""
        if not _collision_enabled(piece):
            return
        pd = ctx.guid.get(piece.guid)
        if pd is None:
            return
        # Master-collision add gate (RE'd @ CLevel_RebuildLevel_GenPathing 0x10203fd0):
        #   add iff `descriptor.ALWAYSBAKECOLLISION || piece[+0x191]`.
        # piece[+0x191] (effective BAKE) defaults TRUE (CRoomPiece ctor 0x1023283c) and is
        # FORCED back to 1 when the descriptor is NEVERBAKE (SetMesh sub_10231080: a non-bakeable
        # type stays a separate static collider, so it IS in the pathing collision). So a piece is
        # EXCLUDED only when <BOOL>BAKE:false AND the type is neither ALWAYSBAKECOLLISION nor
        # NEVERBAKE. (NOPATH -> the existing piece.nopath/type-100 path.)
        bake = piece.props.get("BAKE")
        if (bake is not None and bake.strip().lower() == "false"
                and not getattr(pd, "alwaysbakecollision", False)
                and not getattr(pd, "neverbake", False)):
            return
        coll = select_collision_file(pd, piece.visual)
        if not coll:
            return
        mesh = get_mesh(coll)
        if mesh is None:
            return
        pnop = bool(piece.nopath)
        for sm in mesh.submeshes:
            geo = sm.geometry if (sm.geometry and not sm.use_shared) else mesh.shared_geometry
            if geo is None or not geo.positions:
                continue
            nop = pnop or (NOCOLLIDE_MAT in sm.material.lower())
            idx = sm.indices
            vc = geo.vertex_count
            pos = geo.positions

            def W(vi):
                p = pos[vi]
                return (M[0][0] * p[0] + M[0][1] * p[1] + M[0][2] * p[2] + M[0][3],
                        M[1][0] * p[0] + M[1][1] * p[1] + M[1][2] * p[2] + M[1][3],
                        M[2][0] * p[0] + M[2][1] * p[1] + M[2][2] * p[2] + M[2][3])

            if sm.operation in (4, 0):                  # triangle list
                for t in range(0, len(idx) - 2, 3):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if a < vc and b < vc and c < vc:
                        tris.append((W(a), W(b), W(c), nop))
            elif sm.operation == 5:                     # triangle strip
                for t in range(len(idx) - 2):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if t & 1:
                        b, c = c, b
                    if a < vc and b < vc and c < vc:
                        tris.append((W(a), W(b), W(c), nop))

    # the tile's own room pieces. Exclude (a) randomized/variation backdrop groups and
    # (b) feature/theme/quest-TAGGED groups — both are the editor's base/detail split
    # (sub_1022FF80) and apply to a tile's OWN pieces too, not only to links. Without (b),
    # quest/event scenery placed directly in the tile leaks in, e.g. ACT2_Z2 LAKE z2_lighthouse_*
    # / Ruins_footer_* under Group[KingCrab] TAG=A2-KINGCRABQUEST, whose nocollide over-walls
    # the lake/ruins floor (w2W over-block).
    for piece in iter_room_pieces(layout):
        if _in_backdrop_group(layout, piece) or _link_under_feature_tagged_group(layout, piece):
            continue
        emit_piece(piece, (piece._world or piece.local_matrix()).m)

    if assemble_links:
        from .layout import load_layout_file
        from .region import _resolve_link_layout
        sub_cache = {}
        for o in getattr(layout, "all_objects", ()):
            if o.descriptor != "Layout Link":
                continue
            norpc = o.props.get("NO ROOMPIECE COLLISION")
            if norpc is not None and norpc.strip().lower() == "true":
                continue
            tgt = os.path.basename(o.props.get("LAYOUT FILE", "")).upper()
            if any(s in tgt for s in _RUNTIME_LINK_SUBSTR):
                continue
            # "RANDOM" = runtime random spawns (VARK_RANDOM_*_SPAWN, FIREPLACE_RANDOM,
            # ALL_RANDOMEVENTS) — but NOT "..._RANDOMIZED", which is a STRUCTURAL randomized-variant
            # piece the editor BAKES (e.g. TUTARAN_CAVEBASE_02_RANDOMIZED, the nocollide mesa/canyon
            # base; DLL-hook ground truth: pass#1 down-ray hits it type-100 -> wall on mesa tiles).
            if "RANDOM" in tgt and "RANDOMIZED" not in tgt:
                continue
            # "SPAWNER" = runtime spawn doors/portals (FLOORGRATESPAWNER, WALLGRATESPAWNER —
            # excluded) — but NOT "FLYER" spawners, whose static desert_anthil_* nest IS baked
            # (DLL-hook ground truth: cliff DESERT_FLYER_SPAWNER anthill nocollide -> pass#1
            # down-ray type-100 -> wall). The runtime spawn itself is a collisionless unit.
            if "SPAWNER" in tgt and "FLYER" not in tgt:
                continue
            # principled: a link under a feature-tagged group is runtime/conditional content
            # the editor's master-collision build excludes from the .mpp (sub_1022FF80 theme/
            # feature gate). Generic — subsumes the MerchantShip/chest/shrine/POI cases without a
            # name list, and keeps structural links under untagged groups (e.g. METALSHIP).
            if _link_under_feature_tagged_group(layout, o):
                continue
            # A LINK under a Var*/Variation*/Random* backdrop group (or a CHOICE/THEMES
            # weighted group) is a runtime-SELECTED variation the editor does NOT bake into the
            # base .mpp — same rule already applied to the tile's own pieces above. Without this,
            # links-ON leaks decorative variation walls (e.g. CATACOMB SKELETON_DOUBLEWALL/
            # TRIPLEWALL/WALL_TORCH under Group[Variation]) whose nocollide over-walls the
            # adjacent/under cells -> w2W over-block.
            if _in_backdrop_group(layout, o):
                continue
            sub_path = _resolve_link_layout(ctx.media_dir, o.props.get("LAYOUT FILE", ""))
            if not sub_path:
                continue
            if sub_path not in sub_cache:
                try:
                    sub_cache[sub_path] = load_layout_file(sub_path)
                except Exception:
                    sub_cache[sub_path] = None
            sub = sub_cache[sub_path]
            if sub is None:
                continue
            link_world = o._world or o.local_matrix()
            for piece in iter_room_pieces(sub):
                # the editor excludes link sub-pieces under an inactive weighted CRandomGroup
                # (CHOICE=='Weight') — see _in_backdrop_group(weighted=True). Conservatively
                # drop all weighted-variation children (and any named Var*/Random* backdrop).
                if _in_backdrop_group(sub, piece, weighted=True):
                    continue
                world = (link_world @ (piece._world or piece.local_matrix())).m
                emit_piece(piece, world)

    return tris


def build_grid(layout, ctx, box, origin_x, origin_z, gw, gh, reachability=False,
               assemble_links=False):
    """CLevel_BuildWritePathingGrid_MPP main loop (generation path). `gw`/`gh` are
    the header's gridW/gridH (the editor's box->grid rounding is taken from the
    region header, not recomputed); the cell origin i0/j0 = floor((box.min -
    origin) / 0.4) matches the classifier's index<->coord mapping. Returns
    (grid_bytes, gridW, gridH). grid byte: 0 walkable, 1 wall, 0xFF oob; index
    z*gridW + x (X is the fast axis), matching the .mpp body layout.

    `reachability` (default OFF): the editor navigates the connected ground level and
    voids disconnected ELEVATED scenery (the open/cave footprint mechanism, RE'd). The
    reachability_void() approximation correctly voids OPEN-tile platforms (+CATACOMB),
    BUT a full-corpus sweep shows it NET-REGRESSES (98.19%->96.67%, ~740 tiles worse):
    connectivity+elevation heuristics cannot distinguish scenery platforms (void) from
    legitimate elevated walkways (walk) in boss rooms / multi-level caves — that
    distinction is the editor's BUILD-TIME master-collision exclusion (a separate
    subsystem, not yet RE'd). So it is gated OFF; the safe state is the per-cell model
    (98.19% corpus, ~byte-exact on single-level tiles). Pass reachability=True to opt in
    per-tile (validated win on OPEN/CATACOMB-type elevated-scenery tiles)."""
    i0 = math.floor((box.min.x - origin_x) / CELL)
    j0 = math.floor((box.min.z - origin_z) / CELL)

    tris = gather(layout, ctx, assemble_links=assemble_links)
    nopath_tris = [(a, b, c) for (a, b, c, nop) in tris if nop]

    grid = bytearray(b"\xff" * (gw * gh))
    heights = [None] * (gw * gh)
    for jj in range(gh):
        cz = (j0 + jj) * CELL + HALF + origin_z
        for ii in range(gw):
            cx = (i0 + ii) * CELL + HALF + origin_x
            s = (cx, 200.0, cz)
            e = (cx, -200.0, cz)
            hit = multi_raycast(s, e, RADIUS, tris)
            idx = jj * gw + ii
            if hit is None:
                grid[idx] = 0xFF                      # no ground -> oob
                continue
            hp, htype = hit
            heights[idx] = hp[1]
            if hp[1] > HEIGHT_CLAMP or hp[1] < -HEIGHT_CLAMP or htype == 100:
                grid[idx] = 1                         # height clamp or NOPATH -> wall
            else:
                origin = (hp[0], hp[1] + CLEARANCE_LIFT, hp[2])
                grid[idx] = 1 if clearance_blocked(origin, nopath_tris, CLEARANCE_RADIUS) else 0

    enclosure_pass(grid, gw, gh)
    if reachability:
        reachability_void(grid, heights, gw, gh)
    return bytes(grid), gw, gh


BUCKET = 2.0  # XZ spatial-hash cell for triangle culling (>> radius 0.1 & clearance 0.3)


def _build_index(tris, pad):
    """Bucket triangle indices by the XZ cells their (pad-expanded) AABB overlaps,
    so a cell's down-ray only tests triangles that can possibly hit it."""
    idx = {}
    for ti, (a, b, c, _nop) in enumerate(tris):
        minx = min(a[0], b[0], c[0]) - pad; maxx = max(a[0], b[0], c[0]) + pad
        minz = min(a[2], b[2], c[2]) - pad; maxz = max(a[2], b[2], c[2]) + pad
        for gx in range(int(math.floor(minx / BUCKET)), int(math.floor(maxx / BUCKET)) + 1):
            for gz in range(int(math.floor(minz / BUCKET)), int(math.floor(maxz / BUCKET)) + 1):
                idx.setdefault((gx, gz), []).append(ti)
    return idx


def build_grid_fast(layout, ctx, box, origin_x, origin_z, gw, gh,
                    reachability=False, assemble_links=False, return_heights=False):
    """BYTE-IDENTICAL to build_grid, but XZ-bucket-culled so each cell's down-ray
    and clearance probes only test triangles whose padded AABB overlaps the cell's
    bucket. This is the production grid builder (build_grid is the un-culled
    reference; the two are cross-checked equal). Same args/return as build_grid:
    returns (grid_bytes, gridW, gridH)."""
    i0 = math.floor((box.min.x - origin_x) / CELL)
    j0 = math.floor((box.min.z - origin_z) / CELL)
    tris = gather(layout, ctx, assemble_links=assemble_links)
    nopath_tris = [(a, b, c) for (a, b, c, nop) in tris if nop]
    all_idx = _build_index(tris, RADIUS + 1e-4)
    # nopath index keeps the ORIGINAL nopath_tris ordering for identical iteration
    nop_idx = {}
    for ti, (a, b, c) in enumerate(nopath_tris):
        minx = min(a[0], b[0], c[0]) - CLEARANCE_LEN; maxx = max(a[0], b[0], c[0]) + CLEARANCE_LEN
        minz = min(a[2], b[2], c[2]) - CLEARANCE_LEN; maxz = max(a[2], b[2], c[2]) + CLEARANCE_LEN
        for gx in range(int(math.floor(minx / BUCKET)), int(math.floor(maxx / BUCKET)) + 1):
            for gz in range(int(math.floor(minz / BUCKET)), int(math.floor(maxz / BUCKET)) + 1):
                nop_idx.setdefault((gx, gz), []).append(ti)

    grid = bytearray(b"\xff" * (gw * gh))
    heights = [None] * (gw * gh)
    for jj in range(gh):
        cz = (j0 + jj) * CELL + HALF + origin_z
        gz = int(math.floor(cz / BUCKET))
        for ii in range(gw):
            cx = (i0 + ii) * CELL + HALF + origin_x
            gx = int(math.floor(cx / BUCKET))
            s = (cx, 200.0, cz); e = (cx, -200.0, cz)
            idx = jj * gw + ii
            cand = all_idx.get((gx, gz))
            if not cand:
                grid[idx] = 0xFF; continue
            # nearest-by-distance over candidates only (same order as multi_raycast)
            best_d = None; best_hp = None; best_nop = False
            for ti in cand:
                a, b, c, nop = tris[ti]
                r = swept_tri(s, e, RADIUS, a, b, c)
                if r is None:
                    continue
                hp, d = r
                if best_d is None or d < best_d:
                    best_d = d; best_hp = hp; best_nop = nop
            if best_d is None:
                grid[idx] = 0xFF; continue
            heights[idx] = best_hp[1]
            hp = best_hp; htype = 100 if best_nop else 0
            if hp[1] > HEIGHT_CLAMP or hp[1] < -HEIGHT_CLAMP or htype == 100:
                grid[idx] = 1
            else:
                origin = (hp[0], hp[1] + CLEARANCE_LIFT, hp[2])
                ncand = nop_idx.get((gx, gz))
                blocked = False
                if ncand:
                    for ox, oz in ((CLEARANCE_LEN, 0.0), (-CLEARANCE_LEN, 0.0),
                                   (0.0, CLEARANCE_LEN), (0.0, -CLEARANCE_LEN)):
                        ee = (origin[0] + ox, origin[1], origin[2] + oz)
                        for ti in ncand:
                            a, b, c = nopath_tris[ti]
                            if swept_tri(origin, ee, CLEARANCE_RADIUS, a, b, c) is not None:
                                blocked = True; break
                        if blocked:
                            break
                grid[idx] = 1 if blocked else 0

    enclosure_pass(grid, gw, gh)
    if reachability:
        reachability_void(grid, heights, gw, gh)
    if return_heights:
        # heights[idx] = ground-hit Y per cell (None where the down-ray missed). Caller bakes a
        # terrain-height grid so a walker can follow slopes instead of staying at a fixed Y.
        return bytes(grid), gw, gh, heights
    return bytes(grid), gw, gh


def _closest_on_tri_vec(px, py, pz, a, b, c):
    """Vectorized closest_on_tri (Ericson RTCD): `p*` are float64 arrays, a/b/c are
    scalar 3-tuples. Returns (cpx, cpy, cpz) arrays. BIT-IDENTICAL to closest_on_tri:
    every region's candidate point is computed with the SAME arithmetic, then
    selected by np.where in REVERSE priority (face base ... vertex A last) so the
    highest-priority region wins exactly as the scalar's first-return does."""
    import numpy as np
    a0, a1, a2 = a; b0, b1, b2 = b; c0, c1, c2 = c
    abx, aby, abz = b0 - a0, b1 - a1, b2 - a2          # scalar ab
    acx, acy, acz = c0 - a0, c1 - a1, c2 - a2          # scalar ac
    apx, apy, apz = px - a0, py - a1, pz - a2          # vec ap
    d1 = abx * apx + aby * apy + abz * apz
    d2 = acx * apx + acy * apy + acz * apz
    bpx, bpy, bpz = px - b0, py - b1, pz - b2
    d3 = abx * bpx + aby * bpy + abz * bpz
    d4 = acx * bpx + acy * bpy + acz * bpz
    vc = d1 * d4 - d3 * d2
    cqx, cqy, cqz = px - c0, py - c1, pz - c2
    d5 = abx * cqx + aby * cqy + abz * cqz
    d6 = acx * cqx + acy * cqy + acz * cqz
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        v_ab = d1 / (d1 - d3)
        w_ac = d2 / (d2 - d6)
        w_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        den = 1.0 / (va + vb + vc)
    vv = vb * den; ww = vc * den
    # face (default)
    cx = a0 + abx * vv + acx * ww
    cy = a1 + aby * vv + acy * ww
    cz = a2 + abz * vv + acz * ww
    # edge BC: b + (c-b)*w
    mBC = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    cx = np.where(mBC, b0 + (c0 - b0) * w_bc, cx)
    cy = np.where(mBC, b1 + (c1 - b1) * w_bc, cy)
    cz = np.where(mBC, b2 + (c2 - b2) * w_bc, cz)
    # edge AC: a + ac*w
    mAC = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    cx = np.where(mAC, a0 + acx * w_ac, cx)
    cy = np.where(mAC, a1 + acy * w_ac, cy)
    cz = np.where(mAC, a2 + acz * w_ac, cz)
    # vertex C
    mC = (d6 >= 0) & (d5 <= d6)
    cx = np.where(mC, c0, cx); cy = np.where(mC, c1, cy); cz = np.where(mC, c2, cz)
    # edge AB: a + ab*v
    mAB = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    cx = np.where(mAB, a0 + abx * v_ab, cx)
    cy = np.where(mAB, a1 + aby * v_ab, cy)
    cz = np.where(mAB, a2 + abz * v_ab, cz)
    # vertex B
    mB = (d3 >= 0) & (d4 <= d3)
    cx = np.where(mB, b0, cx); cy = np.where(mB, b1, cy); cz = np.where(mB, b2, cz)
    # vertex A
    mA = (d1 <= 0) & (d2 <= 0)
    cx = np.where(mA, a0, cx); cy = np.where(mA, a1, cy); cz = np.where(mA, a2, cz)
    return cx, cy, cz


def build_grid_np(layout, ctx, box, origin_x, origin_z, gw, gh,
                  reachability=False, assemble_links=False):
    """numpy-vectorized build_grid: BYTE-IDENTICAL output, the vertical down-ray
    nearest-hit is vectorized per-triangle over its padded-XZ-bbox cells (the only
    cells it can hit), accumulating the nearest hit in triangle order with a strict
    `<` update (== the scalar first-min tie-break). The horizontal clearance probes
    stay scalar (bucket-culled) — they consume the same hit point, so identical.

    Down-ray specialization is bit-exact: s=(cx,200,cz), e=(cx,-200,cz) => dx=dz=0,
    and 0.0*t==0.0 / cx+0.0==cx in IEEE754, so the zeroed terms vanish exactly."""
    import numpy as np
    INF = np.inf
    i0 = math.floor((box.min.x - origin_x) / CELL)
    j0 = math.floor((box.min.z - origin_z) / CELL)
    tris = gather(layout, ctx, assemble_links=assemble_links)
    nopath_tris = [(a, b, c) for (a, b, c, nop) in tris if nop]

    best_d = np.full(gw * gh, INF, dtype=np.float64)
    best_hx = np.zeros(gw * gh, dtype=np.float64)
    best_hy = np.zeros(gw * gh, dtype=np.float64)
    best_hz = np.zeros(gw * gh, dtype=np.float64)
    best_nop = np.zeros(gw * gh, dtype=bool)
    pad = RADIUS + 1e-4

    for (a, b, c, nop) in tris:
        a0, a1, a2 = a; b0, b1, b2 = b; c0, c1, c2 = c
        # n = cross(b-a, c-a)
        e1x, e1y, e1z = b0 - a0, b1 - a1, b2 - a2
        e2x, e2y, e2z = c0 - a0, c1 - a1, c2 - a2
        n0 = e1y * e2z - e1z * e2y
        n1 = e1z * e2x - e1x * e2z
        n2 = e1x * e2y - e1y * e2x
        denom = n1 * (-400.0)
        if abs(denom) < SIDE_EPS:        # ray_plane parallel reject (vertical wall)
            continue
        minx = min(a0, b0, c0) - pad; maxx = max(a0, b0, c0) + pad
        minz = min(a2, b2, c2) - pad; maxz = max(a2, b2, c2) + pad
        i_lo = max(0, int(math.floor((minx - HALF - origin_x) / CELL)) - i0 - 1)
        i_hi = min(gw - 1, int(math.ceil((maxx - HALF - origin_x) / CELL)) - i0 + 1)
        j_lo = max(0, int(math.floor((minz - HALF - origin_z) / CELL)) - j0 - 1)
        j_hi = min(gh - 1, int(math.ceil((maxz - HALF - origin_z) / CELL)) - j0 + 1)
        if i_lo > i_hi or j_lo > j_hi:
            continue
        iis = np.arange(i_lo, i_hi + 1)
        jjs = np.arange(j_lo, j_hi + 1)
        cxs = (i0 + iis) * CELL + HALF + origin_x          # (nii,)
        czs = (j0 + jjs) * CELL + HALF + origin_z          # (njj,)
        CX = cxs[None, :]; CZ = czs[:, None]               # broadcast (njj,nii)
        # ray_plane (vertical): t, hit y
        num = n0 * (a0 - CX) + n1 * (a1 - 200.0) + n2 * (a2 - CZ)
        t = num / denom
        hpy = 200.0 + (-400.0) * t
        # segment-range slack (down-ray: x,z terms are 0)
        t_seg = ((hpy - 200.0) * (-400.0)) / 160000.0
        slack = RADIUS / 400.0
        inrange = (t_seg >= -slack) & (t_seg <= 1.0 + slack)
        # point_in_tri(hp, a, b, c)   v0=c-a, v1=b-a, v2=hp-a
        v2x = CX - a0; v2y = hpy - a1; v2z = CZ - a2
        d00 = e2x * e2x + e2y * e2y + e2z * e2z
        d01 = e2x * e1x + e2y * e1y + e2z * e1z
        d02 = e2x * v2x + e2y * v2y + e2z * v2z
        d11 = e1x * e1x + e1y * e1y + e1z * e1z
        d12 = e1x * v2x + e1y * v2y + e1z * v2z
        denb = d00 * d11 - d01 * d01
        if abs(denb) < 1e-20:
            inside = np.zeros(hpy.shape, dtype=bool)
        else:
            inv = 1.0 / denb
            uu = (d11 * d02 - d01 * d12) * inv
            vv2 = (d00 * d12 - d01 * d02) * inv
            inside = (uu >= -1e-6) & (vv2 >= -1e-6) & ((uu + vv2) <= 1.0 + 1e-6)
        dyy = hpy - 200.0
        dist_in = np.sqrt(dyy * dyy)
        # edge branch (closest_on_tri within radius + back-face cull)
        cpx, cpy, cpz = _closest_on_tri_vec(CX, hpy, CZ, a, b, c)
        ex = cpx - CX; ey = cpy - hpy; ez = cpz - CZ
        d_cp = np.sqrt(ex * ex + ey * ey + ez * ez)
        within = d_cp <= RADIUS
        bdot = (a0 - CX) * n0 + (a1 + 200.0) * n1 + (a2 - CZ) * n2
        backface = bdot < -SIDE_EPS
        edge = inrange & (~inside) & within & backface
        sx = cpx - CX; sy = cpy - 200.0; sz = cpz - CZ
        dist_ed = np.sqrt(sx * sx + sy * sy + sz * sz)
        hit = inrange & (inside | edge)
        dist = np.where(inside, dist_in, dist_ed)
        hx = np.where(inside, CX + 0.0 * t, cpx)
        hy = np.where(inside, hpy, cpy)
        hz = np.where(inside, CZ + 0.0 * t, cpz)
        # accumulate nearest (strict <), in triangle order
        flat = (jjs[:, None] * gw + iis[None, :]).ravel()
        hit1 = hit.ravel(); dist1 = dist.ravel()
        upd = hit1 & (dist1 < best_d[flat])
        idxs = flat[upd]
        best_d[idxs] = dist1[upd]
        best_hx[idxs] = hx.ravel()[upd]
        best_hy[idxs] = hy.ravel()[upd]
        best_hz[idxs] = hz.ravel()[upd]
        best_nop[idxs] = nop

    # ---- per-cell classify + scalar bucket-culled clearance (identical to build_grid_fast) ----
    nop_idx = {}
    for ti, (a, b, c) in enumerate(nopath_tris):
        minx = min(a[0], b[0], c[0]) - CLEARANCE_LEN; maxx = max(a[0], b[0], c[0]) + CLEARANCE_LEN
        minz = min(a[2], b[2], c[2]) - CLEARANCE_LEN; maxz = max(a[2], b[2], c[2]) + CLEARANCE_LEN
        for gx in range(int(math.floor(minx / BUCKET)), int(math.floor(maxx / BUCKET)) + 1):
            for gz in range(int(math.floor(minz / BUCKET)), int(math.floor(maxz / BUCKET)) + 1):
                nop_idx.setdefault((gx, gz), []).append(ti)

    grid = bytearray(b"\xff" * (gw * gh))
    heights = [None] * (gw * gh) if reachability else None
    for jj in range(gh):
        cz = (j0 + jj) * CELL + HALF + origin_z
        gz = int(math.floor(cz / BUCKET))
        for ii in range(gw):
            idx = jj * gw + ii
            if best_d[idx] == INF:
                continue
            hpy = float(best_hy[idx]); nop = bool(best_nop[idx])
            if reachability:
                heights[idx] = hpy
            if hpy > HEIGHT_CLAMP or hpy < -HEIGHT_CLAMP or nop:
                grid[idx] = 1
                continue
            origin = (float(best_hx[idx]), hpy + CLEARANCE_LIFT, float(best_hz[idx]))
            cx = (i0 + ii) * CELL + HALF + origin_x
            gx = int(math.floor(cx / BUCKET))
            ncand = nop_idx.get((gx, gz))
            blocked = False
            if ncand:
                for ox, oz in ((CLEARANCE_LEN, 0.0), (-CLEARANCE_LEN, 0.0),
                               (0.0, CLEARANCE_LEN), (0.0, -CLEARANCE_LEN)):
                    ee = (origin[0] + ox, origin[1], origin[2] + oz)
                    for ti in ncand:
                        a, b, c = nopath_tris[ti]
                        if swept_tri(origin, ee, CLEARANCE_RADIUS, a, b, c) is not None:
                            blocked = True; break
                    if blocked:
                        break
            grid[idx] = 1 if blocked else 0

    enclosure_pass(grid, gw, gh)
    if reachability:
        reachability_void(grid, heights, gw, gh)
    return bytes(grid), gw, gh


def compile_mpp_native(layout_path, ctx):
    """Full .mpp bytes (24-byte header + faithful grid). Reuses generate_header for
    the header floats; the grid body is the faithful build_grid output."""
    from .pipeline import generate_header
    hdr = generate_header(layout_path, ctx)
    box = hdr["box"]
    grid, gw, gh = build_grid(hdr["layout"], ctx, box, hdr["originX"], hdr["originZ"],
                              hdr["gridW"], hdr["gridH"])
    header = struct.pack("<ii4f", gw, gh,
                         box.max.x - box.min.x, box.max.z - box.min.z,
                         box.max.x - box.min.x, box.max.z - box.min.z)
    return header + grid
