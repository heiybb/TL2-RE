"""
native_nb.py — numba @njit kernel for the MPP pathing-grid classifier.

A BYTE-IDENTICAL, JIT-compiled port of native.build_grid: the scalar
swept-triangle math (ray_plane / point_in_tri / closest_on_tri / swept_tri) and
the per-cell down-ray + clearance + enclosure passes, mirrored op-for-op into
@njit(fastmath=False) functions. fastmath=False keeps IEEE-754 semantics (no FMA
contraction, no reassociation), so every intermediate float matches the pure-Python
reference bit-for-bit — verified vs build_grid across the corpus.

gather() (mesh parse + world transform) stays pure-Python; this module only
compiles the hot classifier. build_grid_nb() converts the gathered triangle list
to numpy arrays and calls the kernel. native.py keeps build_grid (reference) and
build_grid_np for cross-checking.

Constants are duplicated from native.py (kept in sync); the kernel can't import
module globals at @njit compile time as Python objects, so they're literals here.
"""
from __future__ import annotations

import math
import numpy as np

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:                      # numba/llvmlite absent -> caller falls back
    HAVE_NUMBA = False
    def njit(*a, **k):                 # no-op shim so the module still imports
        def deco(f):
            return f
        return f if (len(a) == 1 and callable(a[0])) else deco

# --- constants (mirror native.py) ---
CELL = 0.4
HALF = 0.2
RADIUS = 0.10000001
CLEARANCE_LEN = 0.30000001
CLEARANCE_LIFT = 1.5
HEIGHT_CLAMP = 80.0
SIDE_EPS = 9.9999997e-06


@njit(cache=True, fastmath=False)
def _point_in_tri_nb(px, py, pz, a0, a1, a2, b0, b1, b2, c0, c1, c2):
    # v0 = c-a, v1 = b-a, v2 = p-a
    v0x = c0 - a0; v0y = c1 - a1; v0z = c2 - a2
    v1x = b0 - a0; v1y = b1 - a1; v1z = b2 - a2
    v2x = px - a0; v2y = py - a1; v2z = pz - a2
    d00 = v0x * v0x + v0y * v0y + v0z * v0z
    d01 = v0x * v1x + v0y * v1y + v0z * v1z
    d02 = v0x * v2x + v0y * v2y + v0z * v2z
    d11 = v1x * v1x + v1y * v1y + v1z * v1z
    d12 = v1x * v2x + v1y * v2y + v1z * v2z
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return False
    inv = 1.0 / den
    u = (d11 * d02 - d01 * d12) * inv
    v = (d00 * d12 - d01 * d02) * inv
    return u >= -1e-6 and v >= -1e-6 and (u + v) <= 1.0 + 1e-6


@njit(cache=True, fastmath=False)
def _closest_on_tri_nb(px, py, pz, a0, a1, a2, b0, b1, b2, c0, c1, c2):
    abx = b0 - a0; aby = b1 - a1; abz = b2 - a2
    acx = c0 - a0; acy = c1 - a1; acz = c2 - a2
    apx = px - a0; apy = py - a1; apz = pz - a2
    d1 = abx * apx + aby * apy + abz * apz
    d2 = acx * apx + acy * apy + acz * apz
    if d1 <= 0.0 and d2 <= 0.0:
        return a0, a1, a2
    bpx = px - b0; bpy = py - b1; bpz = pz - b2
    d3 = abx * bpx + aby * bpy + abz * bpz
    d4 = acx * bpx + acy * bpy + acz * bpz
    if d3 >= 0.0 and d4 <= d3:
        return b0, b1, b2
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return a0 + abx * v, a1 + aby * v, a2 + abz * v
    cpx = px - c0; cpy = py - c1; cpz = pz - c2
    d5 = abx * cpx + aby * cpy + abz * cpz
    d6 = acx * cpx + acy * cpy + acz * cpz
    if d6 >= 0.0 and d5 <= d6:
        return c0, c1, c2
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return a0 + acx * w, a1 + acy * w, a2 + acz * w
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b0 + (c0 - b0) * w, b1 + (c1 - b1) * w, b2 + (c2 - b2) * w
    den = 1.0 / (va + vb + vc)
    v = vb * den
    w = vc * den
    return (a0 + abx * v + acx * w,
            a1 + aby * v + acy * w,
            a2 + abz * v + acz * w)


@njit(cache=True, fastmath=False)
def _swept_tri_nb(sx, sy, sz, ex, ey, ez, radius,
                  a0, a1, a2, b0, b1, b2, c0, c1, c2):
    """Returns (hit, hx, hy, hz, dist). hit = 1 if the swept ray hits the triangle,
    else 0. Mirrors native.swept_tri op-for-op."""
    # n = cross(b-a, c-a)
    e1x = b0 - a0; e1y = b1 - a1; e1z = b2 - a2
    e2x = c0 - a0; e2y = c1 - a1; e2z = c2 - a2
    n0 = e1y * e2z - e1z * e2y
    n1 = e1z * e2x - e1x * e2z
    n2 = e1x * e2y - e1y * e2x
    # ray_plane
    dx = ex - sx; dy = ey - sy; dz = ez - sz
    denom = n0 * dx + n1 * dy + n2 * dz
    if abs(denom) < SIDE_EPS:
        return 0, 0.0, 0.0, 0.0, 0.0
    t = (n0 * (a0 - sx) + n1 * (a1 - sy) + n2 * (a2 - sz)) / denom
    hpx = sx + dx * t; hpy = sy + dy * t; hpz = sz + dz * t
    # segment-range check
    seg2 = dx * dx + dy * dy + dz * dz
    tseg = ((hpx - sx) * dx + (hpy - sy) * dy + (hpz - sz) * dz) / seg2
    slack = radius / math.sqrt(seg2)
    if tseg < -slack or tseg > 1.0 + slack:
        return 0, 0.0, 0.0, 0.0, 0.0
    if _point_in_tri_nb(hpx, hpy, hpz, a0, a1, a2, b0, b1, b2, c0, c1, c2):
        ddx = hpx - sx; ddy = hpy - sy; ddz = hpz - sz
        d = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
        return 1, hpx, hpy, hpz, d
    qx, qy, qz = _closest_on_tri_nb(hpx, hpy, hpz, a0, a1, a2, b0, b1, b2, c0, c1, c2)
    ex2 = qx - hpx; ey2 = qy - hpy; ez2 = qz - hpz
    if math.sqrt(ex2 * ex2 + ey2 * ey2 + ez2 * ez2) <= radius:
        # back-face cull: dot(a - rayEnd, n) < -SIDE_EPS
        bd = (a0 - ex) * n0 + (a1 - ey) * n1 + (a2 - ez) * n2
        if bd < -SIDE_EPS:
            sx2 = qx - sx; sy2 = qy - sy; sz2 = qz - sz
            return 1, qx, qy, qz, math.sqrt(sx2 * sx2 + sy2 * sy2 + sz2 * sz2)
    return 0, 0.0, 0.0, 0.0, 0.0


@njit(cache=True, fastmath=False)
def _blk(grid, gw, gh, x, z):
    if x < 0 or z < 0 or x >= gw or z >= gh:
        return True
    return grid[z * gw + x] == 1


@njit(cache=True, fastmath=False)
def _grid_kernel(verts, nop, gw, gh, i0, j0, ox, oz):
    """Down-ray nearest-hit (per triangle, bbox-culled) + classify + scalar
    clearance (per NOPATH triangle) + enclosure. Returns the grid (uint8)."""
    N = verts.shape[0]
    ncell = gw * gh
    best_d = np.empty(ncell, np.float64)
    best_hx = np.zeros(ncell, np.float64)
    best_hy = np.zeros(ncell, np.float64)
    best_hz = np.zeros(ncell, np.float64)
    best_nop = np.zeros(ncell, np.uint8)
    has = np.zeros(ncell, np.uint8)
    pad = RADIUS + 1e-4

    # ---- down-ray nearest hit, per triangle over its padded-bbox cells ----
    for ti in range(N):
        a0 = verts[ti, 0, 0]; a1 = verts[ti, 0, 1]; a2 = verts[ti, 0, 2]
        b0 = verts[ti, 1, 0]; b1 = verts[ti, 1, 1]; b2 = verts[ti, 1, 2]
        c0 = verts[ti, 2, 0]; c1 = verts[ti, 2, 1]; c2 = verts[ti, 2, 2]
        minx = min(a0, b0, c0) - pad; maxx = max(a0, b0, c0) + pad
        minz = min(a2, b2, c2) - pad; maxz = max(a2, b2, c2) + pad
        i_lo = int(math.floor((minx - HALF - ox) / CELL)) - i0 - 1
        i_hi = int(math.ceil((maxx - HALF - ox) / CELL)) - i0 + 1
        j_lo = int(math.floor((minz - HALF - oz) / CELL)) - j0 - 1
        j_hi = int(math.ceil((maxz - HALF - oz) / CELL)) - j0 + 1
        if i_lo < 0:
            i_lo = 0
        if i_hi > gw - 1:
            i_hi = gw - 1
        if j_lo < 0:
            j_lo = 0
        if j_hi > gh - 1:
            j_hi = gh - 1
        nf = nop[ti]
        for jj in range(j_lo, j_hi + 1):
            cz = (j0 + jj) * CELL + HALF + oz
            row = jj * gw
            for ii in range(i_lo, i_hi + 1):
                cx = (i0 + ii) * CELL + HALF + ox
                hit, hx, hy, hz, dist = _swept_tri_nb(
                    cx, 200.0, cz, cx, -200.0, cz, RADIUS,
                    a0, a1, a2, b0, b1, b2, c0, c1, c2)
                if hit == 1:
                    idx = row + ii
                    if has[idx] == 0 or dist < best_d[idx]:
                        best_d[idx] = dist
                        best_hx[idx] = hx
                        best_hy[idx] = hy
                        best_hz[idx] = hz
                        best_nop[idx] = nf
                        has[idx] = 1

    # ---- classify (oob / height-clamp / NOPATH -> wall, else tentatively walkable) ----
    grid = np.empty(ncell, np.uint8)
    for idx in range(ncell):
        if has[idx] == 0:
            grid[idx] = 255
        else:
            hy = best_hy[idx]
            if hy > HEIGHT_CLAMP or hy < -HEIGHT_CLAMP or best_nop[idx] == 1:
                grid[idx] = 1
            else:
                grid[idx] = 0

    # ---- clearance: per NOPATH triangle, block walkable cells whose 4 head-height
    #      probes hit it (origin = ground hit + 1.5). radius 0 thin segment. ----
    cmargin = CLEARANCE_LEN + RADIUS + 1e-4
    for ti in range(N):
        if nop[ti] == 0:
            continue
        a0 = verts[ti, 0, 0]; a1 = verts[ti, 0, 1]; a2 = verts[ti, 0, 2]
        b0 = verts[ti, 1, 0]; b1 = verts[ti, 1, 1]; b2 = verts[ti, 1, 2]
        c0 = verts[ti, 2, 0]; c1 = verts[ti, 2, 1]; c2 = verts[ti, 2, 2]
        minx = min(a0, b0, c0) - cmargin; maxx = max(a0, b0, c0) + cmargin
        minz = min(a2, b2, c2) - cmargin; maxz = max(a2, b2, c2) + cmargin
        i_lo = int(math.floor((minx - HALF - ox) / CELL)) - i0 - 1
        i_hi = int(math.ceil((maxx - HALF - ox) / CELL)) - i0 + 1
        j_lo = int(math.floor((minz - HALF - oz) / CELL)) - j0 - 1
        j_hi = int(math.ceil((maxz - HALF - oz) / CELL)) - j0 + 1
        if i_lo < 0:
            i_lo = 0
        if i_hi > gw - 1:
            i_hi = gw - 1
        if j_lo < 0:
            j_lo = 0
        if j_hi > gh - 1:
            j_hi = gh - 1
        for jj in range(j_lo, j_hi + 1):
            row = jj * gw
            for ii in range(i_lo, i_hi + 1):
                idx = row + ii
                if grid[idx] != 0:
                    continue
                px = best_hx[idx]; py = best_hy[idx] + CLEARANCE_LIFT; pz = best_hz[idx]
                blocked = False
                for d in range(4):
                    if d == 0:
                        ex = px + CLEARANCE_LEN; ez = pz
                    elif d == 1:
                        ex = px - CLEARANCE_LEN; ez = pz
                    elif d == 2:
                        ex = px; ez = pz + CLEARANCE_LEN
                    else:
                        ex = px; ez = pz - CLEARANCE_LEN
                    hit, _hx, _hy, _hz, _d = _swept_tri_nb(
                        px, py, pz, ex, py, ez, 0.0,
                        a0, a1, a2, b0, b1, b2, c0, c1, c2)
                    if hit == 1:
                        blocked = True
                        break
                if blocked:
                    grid[idx] = 1

    # ---- enclosure pass (X-outer, Z-inner, cascades in place) ----
    for x in range(gw):
        for z in range(gh):
            idx = z * gw + x
            if grid[idx] != 0:
                continue
            if ((_blk(grid, gw, gh, x - 1, z) and _blk(grid, gw, gh, x + 1, z)) or
                (_blk(grid, gw, gh, x, z - 1) and _blk(grid, gw, gh, x, z + 1)) or
                (_blk(grid, gw, gh, x - 1, z - 1) and _blk(grid, gw, gh, x + 1, z + 1)) or
                (_blk(grid, gw, gh, x + 1, z - 1) and _blk(grid, gw, gh, x - 1, z + 1))):
                grid[idx] = 1
    return grid


def build_grid_nb(layout, ctx, box, origin_x, origin_z, gw, gh,
                  reachability=False, assemble_links=False):
    """numba-compiled build_grid: BYTE-IDENTICAL to native.build_grid / build_grid_np.
    Same signature/return (grid_bytes, gridW, gridH). `reachability` is not yet
    supported by the kernel; callers needing it use build_grid_np."""
    from .native import gather
    i0 = math.floor((box.min.x - origin_x) / CELL)
    j0 = math.floor((box.min.z - origin_z) / CELL)
    tris = gather(layout, ctx, assemble_links=assemble_links)
    n = len(tris)
    if n == 0:                                 # geometry-free tile -> all-oob grid
        return np.full(gw * gh, 255, np.uint8).tobytes(), gw, gh
    # Build the (n,3,3) vertex array in one C-level np.array pass (t[:3] = (a,b,c),
    # each a 3-tuple) rather than 9*n element-wise assignments. Same float64 bits.
    verts = np.array([t[:3] for t in tris], np.float64)
    nop = np.fromiter((1 if t[3] else 0 for t in tris), np.uint8, n)
    grid = _grid_kernel(verts, nop, gw, gh, int(i0), int(j0),
                        float(origin_x), float(origin_z))
    return grid.tobytes(), gw, gh
