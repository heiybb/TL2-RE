"""
pipeline.py — high-level Version B .mpp generation, end to end.

generate_header(layout_path, ...) -> dict(gridW, gridH, worldExtX/Z, boundsX/Z, box, region, layout)
generate_mpp(layout_path, out_path, ...) writes a full .mpp (header + grid).

Region model (RE-grounded; see region.py for the full citation):
  1. The region AABB is the merge of every collision-enabled room-piece's
     COLLISION-mesh M_MESH_BOUNDS, transformed to world (float32, 8-corner refit),
     merged UNPADDED. This is the offline proxy for the editor's per-region
     aggregate collision box (RebuildLevel master-AABB loop @ 0x10203931..0x10204795;
     for a single pre-baked room the region == the whole room). A piece with no
     COLLISIONFILE / COLLISION ENABLED:false contributes nothing.
  2. That merged box is snapped OUTWARD to the 10-unit editor tile boundary WITH a
     0.2 pad per face, exactly as the editor snaps each region box before merging:
        snappedMin = floor((min - 0.2)/10)*10 ,  snappedMax = ceil((max + 0.2)/10)*10
     (RE @ 0x102043af..0x10204511; consts 0.2 / 10.0; all float32). The 0.2 pad
     pushes a hull that lands on (or a hair inside) a 10-multiple to the next tile.
  3. worldExt = -boxMin (writer a5 == Vector3(0,0,0)); bounds = boxMax - boxMin.
  4. The grid dims use the writer's exact float32 ceil/floor with the CLevel grid
     ORIGIN (RebuildLevel @ 0x10204FD0): origin = float32((floor((min-0.2)/0.4) -
     1) * 0.4) per axis. The origin does NOT cancel — its float32 rounding is what
     produces the +1 cell straddle on some tiles.

The per-region 0.2-snap-10 (replacing the earlier coincidental 0.4-pad heuristic)
gives 88.8% header byte-exact; selecting each piece's ACTIVE visual collider from
the stored <STRING>VISUAL:N index (region.select_collision_file, RE'd deterministic
— see region.py) lifts it to 90.9% over the 1293 ground-truth files (+27 leaf tiles,
no plain/template/portal regression). The VISUAL index picks among a [PIECE]'s set
of collision variants; the old model always took variant 0 and mis-sized tiles that
ship a non-zero visual.

Honest residual (~9%), both inherent to offline geometry: (a) multi-CHUNK assembled
outdoor PASS rooms (e.g. the 4 ACT1_PASS1 rooms) whose .MPP footprint unions
adjacent randomly-chosen chunk regions / terrain added at runtime to [CLevel+0x10]
— not present in this one .LAYOUT, so undershoots toward the neighbor slots; (b) a
thin residual of leaf tiles (ENTRANCE/EXIT/CLIFF) that still miss by one 10-tile on
one axis even with the correct visual collider — a collision-world assembly subtlety
(NOT sub_1022FF80, which does not exclude pieces from the master AABB). We do not
snap harder or add a fudge epsilon to hide it.

The grid BODY is produced by the faithful DLL-port classifier (native.build_grid /
build_grid_fast), validated to ~99.56% cell / 99.71% de-floated across the 1293
shipped .mpp (tools/eval_all_mpp.py, tools/mpp_compare_full.csv). For BYTE-EXACT
output use the DLL backend (dll.regen_mpp_via_dll).
"""
from __future__ import annotations

import os

from .dat import load_all_levelsets
from .geom import AABB, Vec3
from .layout import load_layout_file
from .rules import is_multichunk_assembled
from .region import (
    CELL,
    MeshBoundsCache,
    SNAP,
    compute_region_aabb_collision,
    grid_dims,
    grid_origin,
    header_floats,
    pack_header,
    snap_box_outward,
)

DEFAULT_PORTAL_HALF = 10.0  # files with no room pieces default to a 20x20 box


class Context:
    """Holds the shared guid table + mesh cache so a batch run parses once."""

    def __init__(self, media_dir: str):
        self.media_dir = media_dir
        self.guid = load_all_levelsets(os.path.join(media_dir, "LEVELSETS"))
        self.mesh_cache = MeshBoundsCache(media_dir)      # bounds (header sizing)
        # Full collision-mesh GEOMETRY cache (rel -> parsed mesh|None), reused by
        # native.gather across every tile this Context serves (one per pool worker),
        # so a shared room-piece .mesh is parsed once, not once per tile.
        self.mesh_geom_cache = {}


def compute_region(layout, ctx: Context, snap: float = SNAP):
    """Compute the level passability region AABB (X,Z): collision M_MESH_BOUNDS
    merge (float32), snapped OUTWARD to `snap` units. Geometry-free layouts get
    the editor's default 20x20 region at the world origin."""
    res = compute_region_aabb_collision(layout, ctx)
    box = res.aabb
    if box.null:
        h = DEFAULT_PORTAL_HALF
        box = AABB(Vec3(-h, 0.0, -h), Vec3(h, 0.0, h))
    elif snap:
        box = snap_box_outward(box, snap)
    return box, res


def generate_header(layout_path, ctx: Context, snap: float = SNAP, world_ext=None):
    layout = load_layout_file(layout_path)
    box, res = compute_region(layout, ctx, snap=snap)
    # worldExt = world origin (0,0). y irrelevant for header.
    we = world_ext if world_ext is not None else Vec3(0.0, 0.0, 0.0)
    ox, oz = grid_origin(box.min)
    gw, gh = grid_dims(box.min, box.max, ox, oz)
    wW, wD, bW, bD = header_floats(box.min, box.max, we)
    return {
        "gridW": gw, "gridH": gh,
        "worldExtX": wW, "worldExtZ": wD,
        "boundsX": bW, "boundsZ": bD,
        "originX": ox, "originZ": oz,
        "box": box, "region": res, "layout": layout,
        # True => the level is a >=2-slot procedural chunk assembly (rules.py):
        # the shipped .MPP bakes THIS room plus runtime-placed neighbour chunks
        # (each randomly selected at build time), so the header footprint is a
        # runtime instance not reconstructible from a single .LAYOUT. The box above
        # is this room's own region only (the honest offline answer); we flag it
        # rather than fabricate the neighbour union.
        "multichunk": is_multichunk_assembled(layout_path),
    }


def _generate_mpp(layout_path, ctx: Context, **kw):
    """Shared core: returns (hdr_dict, full_.mpp_bytes). Both generate_mpp (writes
    to a path, returns the dict) and generate_mpp_bytes (returns just the bytes)
    wrap this, so they emit byte-identical .mpp content."""
    hdr = generate_header(layout_path, ctx, **{k: v for k, v in kw.items()
                                               if k in ("snap", "world_ext")})
    box = hdr["box"]
    layout = hdr["layout"]
    # Grid body: the faithful DLL-port classifier, byte-identical to the pure-Python
    # reference native.build_grid. Prefer the numba-compiled kernel (build_grid_nb,
    # ~30x the numpy builder); fall back to the numpy build_grid_np when numba is
    # unavailable. Rasterized on the same grid the writer indexes: cell (i,j) ->
    # coord (i*0.4 + 0.2 + origin), so it uses the grid origin from the header.
    from .native_nb import build_grid_nb, HAVE_NUMBA
    if HAVE_NUMBA:
        grid_bytes, _, _ = build_grid_nb(layout, ctx, box, hdr["originX"],
                                         hdr["originZ"], hdr["gridW"], hdr["gridH"])
    else:
        from .native import build_grid_np
        grid_bytes, _, _ = build_grid_np(layout, ctx, box, hdr["originX"],
                                         hdr["originZ"], hdr["gridW"], hdr["gridH"])
    header = pack_header(hdr["gridW"], hdr["gridH"], hdr["worldExtX"],
                         hdr["worldExtZ"], hdr["boundsX"], hdr["boundsZ"])
    return hdr, header + grid_bytes


def generate_mpp_bytes(layout_path, ctx: Context, **kw) -> bytes:
    """Return the full .mpp content (24-byte header + grid body) as bytes — the
    exact bytes generate_mpp writes to disk, without touching the filesystem."""
    _, data = _generate_mpp(layout_path, ctx, **kw)
    return data


def generate_mpp(layout_path, out_path, ctx: Context, **kw):
    hdr, data = _generate_mpp(layout_path, ctx, **kw)
    with open(out_path, "wb") as f:
        f.write(data)
    return hdr
