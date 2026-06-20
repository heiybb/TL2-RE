"""
ogre_mesh.py — clean Ogre .mesh reader for the pathing pipeline.

Extracts:
  - the mesh AABB (from M_MESH_BOUNDS if present, else computed from the
    POSITION vertex element of every geometry, exactly as Ogre does when no
    bounds were authored), and
  - triangle geometry (positions + index triples) for collision raycasting.

TL2 meshes are MeshSerializer_v1.40 (chunk id 0x1000 header). Chunk lengths
are sometimes overstated / unreliable, so the reader is structural: it trusts
chunk IDs and the documented per-chunk field layout, and only uses chunk
length as a skip hint for chunks it does not descend into. When a length looks
implausible it re-syncs by scanning for the next plausible chunk id.

References (Ogre 1.x OgreMeshFileFormat.h):
  M_HEADER                 0x1000
  M_MESH                   0x3000
    M_SUBMESH              0x4000
      M_SUBMESH_OPERATION 0x4010
      M_SUBMESH_BONE_ASSIGNMENT 0x4100
      M_SUBMESH_TEXTURE_ALIAS   0x4200
    M_GEOMETRY            0x5000
      M_GEOMETRY_VERTEX_DECLARATION 0x5100
        M_GEOMETRY_VERTEX_ELEMENT   0x5110
      M_GEOMETRY_VERTEX_BUFFER      0x5200
        M_GEOMETRY_VERTEX_BUFFER_DATA 0x5210
    M_MESH_SKELETON_LINK 0x6000
    M_MESH_BONE_ASSIGNMENT 0x7000
    M_MESH_LOD           0x8000
    M_MESH_BOUNDS        0x9000
    M_SUBMESH_NAME_TABLE 0xA000
    M_EDGE_LISTS         0xB000
    M_POSES              0xC000
    M_ANIMATIONS         0xE000
    M_TABLE_EXTREMES     0xF000
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .geom import AABB, Vec3

M_HEADER = 0x1000
M_MESH = 0x3000
M_SUBMESH = 0x4000
M_SUBMESH_OPERATION = 0x4010
M_SUBMESH_BONE_ASSIGNMENT = 0x4100
M_SUBMESH_TEXTURE_ALIAS = 0x4200
M_GEOMETRY = 0x5000
M_GEOMETRY_VERTEX_DECLARATION = 0x5100
M_GEOMETRY_VERTEX_ELEMENT = 0x5110
M_GEOMETRY_VERTEX_BUFFER = 0x5200
M_GEOMETRY_VERTEX_BUFFER_DATA = 0x5210
M_MESH_SKELETON_LINK = 0x6000
M_MESH_BONE_ASSIGNMENT = 0x7000
M_MESH_LOD = 0x8000
M_MESH_BOUNDS = 0x9000
M_SUBMESH_NAME_TABLE = 0xA000
M_EDGE_LISTS = 0xB000
M_POSES = 0xC000
M_ANIMATIONS = 0xE000
M_TABLE_EXTREMES = 0xF000

# Vertex element type ids (Ogre VertexElementType) -> (n_floats_or_bytes, struct)
VET_FLOAT1 = 0
VET_FLOAT2 = 1
VET_FLOAT3 = 2
VET_FLOAT4 = 3
VET_COLOUR = 4
VET_SHORT1 = 5
VET_SHORT2 = 6
VET_SHORT3 = 7
VET_SHORT4 = 8
VET_UBYTE4 = 9
VET_COLOUR_ARGB = 10
VET_COLOUR_ABGR = 11

# semantic ids (VertexElementSemantic): 1 = POSITION
VES_POSITION = 1

_ELEM_SIZE = {
    VET_FLOAT1: 4, VET_FLOAT2: 8, VET_FLOAT3: 12, VET_FLOAT4: 16,
    VET_COLOUR: 4, VET_COLOUR_ARGB: 4, VET_COLOUR_ABGR: 4,
    VET_SHORT1: 2, VET_SHORT2: 4, VET_SHORT3: 6, VET_SHORT4: 8,
    VET_UBYTE4: 4,
}

# Set of chunk ids that are valid as top-level-of-mesh / sub-chunk markers,
# used for re-sync when a length is implausible.
_KNOWN_IDS = {
    M_SUBMESH, M_SUBMESH_OPERATION, M_SUBMESH_BONE_ASSIGNMENT,
    M_SUBMESH_TEXTURE_ALIAS, M_GEOMETRY, M_GEOMETRY_VERTEX_DECLARATION,
    M_GEOMETRY_VERTEX_ELEMENT, M_GEOMETRY_VERTEX_BUFFER,
    M_GEOMETRY_VERTEX_BUFFER_DATA, M_MESH_SKELETON_LINK,
    M_MESH_BONE_ASSIGNMENT, M_MESH_LOD, M_MESH_BOUNDS, M_SUBMESH_NAME_TABLE,
    M_EDGE_LISTS, M_POSES, M_ANIMATIONS, M_TABLE_EXTREMES,
}


@dataclass
class Geometry:
    vertex_count: int = 0
    positions: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class SubMesh:
    use_shared: bool = True
    operation: int = 4  # OT_TRIANGLE_LIST
    indices: list[int] = field(default_factory=list)
    index_32bit: bool = False
    geometry: Geometry | None = None  # dedicated geometry if not shared
    material: str = ""                # submesh material name (collision type marker:
                                      # "multi_collision/nocollide" => NOPATH wall)


@dataclass
class Mesh:
    bounds: AABB
    bounds_radius: float
    bounds_from_chunk: bool
    shared_geometry: Geometry | None
    submeshes: list[SubMesh]

    def iter_positions(self):
        if self.shared_geometry:
            yield from self.shared_geometry.positions
        for sm in self.submeshes:
            if sm.geometry:
                yield from sm.geometry.positions

    def computed_bounds(self) -> AABB:
        box = AABB()
        for p in self.iter_positions():
            box.merge_point(Vec3(*p))
        return box

    def triangles(self):
        """Yield (Vec3, Vec3, Vec3) world-space-agnostic triangles."""
        for sm in self.submeshes:
            geo = sm.geometry if (sm.geometry and not sm.use_shared) else self.shared_geometry
            if geo is None or not geo.positions:
                continue
            idx = sm.indices
            if sm.operation in (4, 0):  # triangle list (treat unknown as list)
                for t in range(0, len(idx) - 2, 3):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if a < geo.vertex_count and b < geo.vertex_count and c < geo.vertex_count:
                        yield (Vec3(*geo.positions[a]), Vec3(*geo.positions[b]), Vec3(*geo.positions[c]))
            elif sm.operation == 5:  # triangle strip
                for t in range(len(idx) - 2):
                    a, b, c = idx[t], idx[t + 1], idx[t + 2]
                    if t & 1:
                        b, c = c, b
                    yield (Vec3(*geo.positions[a]), Vec3(*geo.positions[b]), Vec3(*geo.positions[c]))


class _Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.n = len(data)

    def u16(self, off):
        return struct.unpack_from("<H", self.d, off)[0]

    def u32(self, off):
        return struct.unpack_from("<I", self.d, off)[0]

    def f32(self, off):
        return struct.unpack_from("<f", self.d, off)[0]

    def chunk_hdr(self, off):
        return self.u16(off), self.u32(off + 2)  # id, length(includes 6-byte header)


def _read_geometry(r: _Reader, off: int, hard_end: int) -> tuple[Geometry, int]:
    """Read an M_GEOMETRY chunk body starting at `off` (just past the 6-byte
    M_GEOMETRY header). Returns (Geometry, offset-after)."""
    geo = Geometry()
    geo.vertex_count = r.u32(off)
    off += 4

    # vertex declaration: list of M_GEOMETRY_VERTEX_ELEMENT
    # element: u16 source, u16 type, u16 semantic, u16 offset, u16 index
    pos_source = None
    pos_offset = 0
    pos_type = VET_FLOAT3
    # Each source's stride accumulates; we need source->stride and where the
    # vertex buffer for the position source lives.
    buffers: dict[int, tuple[int, bytes]] = {}  # source -> (stride, raw)

    cur = off
    while cur + 6 <= hard_end:
        cid, clen = r.chunk_hdr(cur)
        if cid == M_GEOMETRY_VERTEX_DECLARATION:
            decl_end = min(cur + clen, hard_end)
            inner = cur + 6
            while inner + 6 <= hard_end:
                eid, elen = r.chunk_hdr(inner)
                if eid != M_GEOMETRY_VERTEX_ELEMENT:
                    break
                source = r.u16(inner + 6)
                vtype = r.u16(inner + 8)
                semantic = r.u16(inner + 10)
                voffset = r.u16(inner + 12)
                # index = r.u16(inner + 14)
                if semantic == VES_POSITION and pos_source is None:
                    pos_source = source
                    pos_offset = voffset
                    pos_type = vtype
                inner += 8 + 6  # element body is 5x u16 = 10? -> actually 5 u16 = 10 bytes + 6 hdr
                # element chunk total = 6 hdr + 10 body = 16; use elen if plausible
                if 6 <= elen <= 64:
                    inner = inner  # already advanced by 16
            # advance past declaration: trust clen if plausible else jump to inner
            cur = cur + clen if 6 <= clen <= (hard_end - cur) else inner
        elif cid == M_GEOMETRY_VERTEX_BUFFER:
            bind = r.u16(cur + 6)
            stride = r.u16(cur + 8)
            # next sub-chunk should be M_GEOMETRY_VERTEX_BUFFER_DATA
            data_off = cur + 10
            did, dlen = r.chunk_hdr(data_off)
            raw_start = data_off + 6
            nbytes = geo.vertex_count * stride
            raw = r.d[raw_start:raw_start + nbytes]
            buffers[bind] = (stride, raw)
            # advance: data chunk = 6 + nbytes
            cur = raw_start + nbytes
        else:
            # unknown / end of geometry sub-chunks
            break

    # decode positions
    if pos_source is not None and pos_source in buffers:
        stride, raw = buffers[pos_source]
        positions = []
        for i in range(geo.vertex_count):
            base = i * stride + pos_offset
            if base + 12 <= len(raw):
                x, y, z = struct.unpack_from("<fff", raw, base)
                positions.append((x, y, z))
        geo.positions = positions
    return geo, cur


def _read_submesh(r: _Reader, off: int, hard_end: int) -> tuple[SubMesh, int]:
    """Read M_SUBMESH body (past 6-byte header). Returns (SubMesh, off-after)."""
    sm = SubMesh()
    # material name: null/newline-terminated string (the collision-type marker)
    start = off
    while off < hard_end and r.d[off] not in (0x0A,):
        off += 1
    sm.material = r.d[start:off].decode("latin1", "replace")
    off += 1  # consume newline
    # use shared geometry: bool (1 byte)
    sm.use_shared = bool(r.d[off])
    off += 1
    # index count: u32
    index_count = r.u32(off)
    off += 4
    # 32-bit indices? bool
    sm.index_32bit = bool(r.d[off])
    off += 1
    # index data
    if sm.index_32bit:
        sm.indices = list(struct.unpack_from("<%dI" % index_count, r.d, off))
        off += 4 * index_count
    else:
        sm.indices = list(struct.unpack_from("<%dH" % index_count, r.d, off))
        off += 2 * index_count

    # if not shared, a dedicated M_GEOMETRY chunk follows
    if not sm.use_shared:
        if off + 6 <= hard_end:
            cid, clen = r.chunk_hdr(off)
            if cid == M_GEOMETRY:
                geo, after = _read_geometry(r, off + 6, hard_end)
                sm.geometry = geo
                off = after
    # optional sub-chunks: operation, bone assignments, texture alias
    while off + 6 <= hard_end:
        cid, clen = r.chunk_hdr(off)
        if cid == M_SUBMESH_OPERATION:
            sm.operation = r.u16(off + 6)
            off += clen if 6 <= clen <= (hard_end - off) else 8
        elif cid in (M_SUBMESH_BONE_ASSIGNMENT, M_SUBMESH_TEXTURE_ALIAS):
            off += clen if 6 <= clen <= (hard_end - off) else 6
        else:
            break
    return sm, off


def parse_mesh(data: bytes) -> Mesh:
    r = _Reader(data)
    off = 0
    # header
    hid = r.u16(off)
    off += 2
    if hid != M_HEADER:
        raise ValueError(f"not an Ogre mesh (header 0x{hid:04x})")
    # version string up to newline
    while off < r.n and r.d[off] != 0x0A:
        off += 1
    off += 1

    # M_MESH
    cid, clen = r.chunk_hdr(off)
    if cid != M_MESH:
        raise ValueError(f"expected M_MESH, got 0x{cid:04x}")
    mesh_end = r.n  # do not trust clen; walk to EOF
    off += 6
    # bool skeletallyAnimated
    off += 1

    shared_geo = None
    submeshes: list[SubMesh] = []
    bounds = None
    bounds_radius = 0.0
    bounds_from_chunk = False

    while off + 6 <= mesh_end:
        cid, clen = r.chunk_hdr(off)
        if cid == M_GEOMETRY:
            shared_geo, off = _read_geometry(r, off + 6, mesh_end)
        elif cid == M_SUBMESH:
            sm, off = _read_submesh(r, off + 6, mesh_end)
            submeshes.append(sm)
        elif cid == M_MESH_BOUNDS:
            mnx, mny, mnz = struct.unpack_from("<fff", r.d, off + 6)
            mxx, mxy, mxz = struct.unpack_from("<fff", r.d, off + 18)
            bounds_radius = r.f32(off + 30)
            bounds = AABB(Vec3(mnx, mny, mnz), Vec3(mxx, mxy, mxz))
            bounds_from_chunk = True
            off += 6 + 28
        elif cid == M_MESH_SKELETON_LINK:
            off += clen if 6 <= clen <= (mesh_end - off) else 6
        elif cid in _KNOWN_IDS:
            # skip with length; if implausible, re-sync below
            step = clen if 6 <= clen <= (mesh_end - off) else None
            if step is None:
                off = _resync(r, off + 6, mesh_end)
            else:
                off += step
        else:
            # unknown id: try to re-sync to next known chunk
            nxt = _resync(r, off + 2, mesh_end)
            if nxt <= off:
                break
            off = nxt

    if bounds is None:
        bounds = AABB()
        for p in (shared_geo.positions if shared_geo else []):
            bounds.merge_point(Vec3(*p))
        for sm in submeshes:
            if sm.geometry:
                for p in sm.geometry.positions:
                    bounds.merge_point(Vec3(*p))

    return Mesh(
        bounds=bounds,
        bounds_radius=bounds_radius,
        bounds_from_chunk=bounds_from_chunk,
        shared_geometry=shared_geo,
        submeshes=submeshes,
    )


def _resync(r: _Reader, off: int, end: int) -> int:
    """Scan forward for the next plausible known chunk id."""
    o = off
    while o + 6 <= end:
        cid, clen = r.chunk_hdr(o)
        if cid in _KNOWN_IDS and 6 <= clen <= (end - o):
            return o
        o += 1
    return end


def load_mesh_file(path: str) -> Mesh:
    with open(path, "rb") as f:
        return parse_mesh(f.read())
