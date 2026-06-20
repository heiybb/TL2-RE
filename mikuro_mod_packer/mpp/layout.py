"""
layout.py — UTF-16-LE .LAYOUT reader (room-piece placements + world transforms).

A .LAYOUT is a bracketed tree:
  [Layout]
    [OBJECTS]
      [BASEOBJECT]
        [PROPERTIES] ...key:value... [/PROPERTIES]
        [CHILDREN] [BASEOBJECT]...[/BASEOBJECT] [/CHILDREN]
      [/BASEOBJECT]
    [/OBJECTS]

Each object has an ID and PARENTID (INTEGER64). Renderable Room Pieces carry
POSITIONX/Y/Z, orientation (FORWARDX/Y/Z + RIGHTX/Y/Z, or YAW), optional
per-axis scale X/Y/Z, GUID (the LEVELSETS piece), and flags (NOPATH, etc.).
Group / Logic Group / Property Node objects carry transforms too and are part
of the PARENTID chain, but have no geometry of their own.

We compose each object's WORLD transform recursively: world = parent_world @ local,
where local = translate(pos) @ rotate(axes) @ scale(s).  (Matches the repo's
get_global_transform convention; UP = FORWARD x RIGHT.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .geom import Matrix4, Vec3, orientation_axes, yaw_axes


@dataclass
class LayoutObject:
    id: str = ""
    parent_id: str = "-1"
    descriptor: str = ""
    name: str = ""
    guid: str = ""
    pos: Vec3 = field(default_factory=Vec3)
    has_pos: bool = False
    fwd: Vec3 | None = None
    right: Vec3 | None = None
    yaw: float | None = None
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    nopath: bool = False
    radius: float | None = None
    # Stored VISUAL PIECE INDEX (<STRING>VISUAL:N). A [PIECE] holds a SET of visual
    # sub-pieces; this index (default 0) selects which render/collision mesh the
    # instance uses. -1 == RANDOM (resolved by a seeded RNG at editor bake time and
    # never persisted to the shipped layouts — every shipped VISUAL is a concrete
    # non-negative index). See region.select_collision_file.
    visual: int = 0
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    # filled by composer
    _world: Matrix4 | None = None

    def local_matrix(self) -> Matrix4:
        t = Matrix4.translation(self.pos if self.has_pos else Vec3(0, 0, 0))
        if self.fwd is not None and self.right is not None:
            r, u, f = orientation_axes(self.fwd, self.right)
            rot = Matrix4.from_axes(r, u, f)
        elif self.yaw is not None:
            r, u, f = yaw_axes(self.yaw)
            rot = Matrix4.from_axes(r, u, f)
        else:
            rot = Matrix4()
        s = Matrix4.scale(self.scale.x, self.scale.y, self.scale.z)
        return t @ rot @ s


def _decode(data: bytes) -> str:
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16-le", errors="replace")
    if data[:2] == b"\xfe\xff":
        return data.decode("utf-16-be", errors="replace")
    return data.decode("latin-1", errors="replace")


_PROP_RE = re.compile(r"<([^>]+)>([A-Z0-9 _]+):(.*)")


def _fget(props, key):
    v = props.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


class _TreeParser:
    """Recursive-descent over the bracket tokens."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        self.i = 0
        self.n = len(lines)

    def parse_objects(self) -> list[LayoutObject]:
        objs = []
        while self.i < self.n:
            s = self.lines[self.i].strip()
            if s == "[BASEOBJECT]":
                objs.append(self._parse_baseobject())
            elif s == "[/OBJECTS]" or s == "[/CHILDREN]":
                self.i += 1
                break
            else:
                self.i += 1
        return objs

    def _parse_baseobject(self) -> LayoutObject:
        assert self.lines[self.i].strip() == "[BASEOBJECT]"
        self.i += 1
        props: dict[str, str] = {}
        obj = LayoutObject()
        while self.i < self.n:
            s = self.lines[self.i].strip()
            if s == "[PROPERTIES]":
                self.i += 1
                while self.i < self.n and self.lines[self.i].strip() != "[/PROPERTIES]":
                    m = _PROP_RE.match(self.lines[self.i].strip())
                    if m:
                        k = m.group(2).strip()
                        v = m.group(3).strip()
                        props[k] = v  # last wins for singletons
                    self.i += 1
                self.i += 1  # consume [/PROPERTIES]
            elif s == "[CHILDREN]":
                self.i += 1
                obj.children = self.parse_objects()
            elif s == "[/BASEOBJECT]":
                self.i += 1
                break
            else:
                self.i += 1
        obj.props = props
        obj.descriptor = props.get("DESCRIPTOR", "")
        obj.name = props.get("NAME", "")
        obj.id = props.get("ID", "")
        obj.parent_id = props.get("PARENTID", "-1")
        obj.guid = props.get("GUID", "")
        px, py, pz = _fget(props, "POSITIONX"), _fget(props, "POSITIONY"), _fget(props, "POSITIONZ")
        if px is not None or py is not None or pz is not None:
            obj.pos = Vec3(px or 0.0, py or 0.0, pz or 0.0)
            obj.has_pos = True
        fx, fy, fz = _fget(props, "FORWARDX"), _fget(props, "FORWARDY"), _fget(props, "FORWARDZ")
        rx, ry, rz = _fget(props, "RIGHTX"), _fget(props, "RIGHTY"), _fget(props, "RIGHTZ")
        if None not in (fx, fy, fz) and None not in (rx, ry, rz):
            obj.fwd = Vec3(fx, fy, fz)
            obj.right = Vec3(rx, ry, rz)
        yaw = _fget(props, "YAW")
        if yaw is not None and obj.fwd is None:
            obj.yaw = yaw
        sx = _fget(props, "X")
        sy = _fget(props, "Y")
        sz = _fget(props, "Z")
        obj.scale = Vec3(sx if sx is not None else 1.0,
                         sy if sy is not None else 1.0,
                         sz if sz is not None else 1.0)
        obj.nopath = props.get("NOPATH", "false").lower() == "true"
        obj.radius = _fget(props, "RADIUS")
        vis = props.get("VISUAL")
        if vis is not None:
            try:
                obj.visual = int(vis)
            except ValueError:
                obj.visual = 0
        return obj


@dataclass
class Layout:
    version: int
    roots: list[LayoutObject]
    by_id: dict[str, LayoutObject]
    all_objects: list[LayoutObject]


def parse_layout(data: bytes) -> Layout:
    txt = _decode(data)
    lines = txt.splitlines()
    # find [OBJECTS]
    start = None
    version = 0
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("<INTEGER>VERSION:"):
            try:
                version = int(s.split(":", 1)[1])
            except ValueError:
                pass
        if s == "[OBJECTS]":
            start = idx + 1
            break
    if start is None:
        return Layout(version, [], {}, [])
    tp = _TreeParser(lines[start:])
    roots = tp.parse_objects()

    by_id: dict[str, LayoutObject] = {}
    all_objs: list[LayoutObject] = []

    def index(o: LayoutObject):
        if o.id:
            by_id[o.id] = o
        all_objs.append(o)
        for c in o.children:
            index(c)

    for r in roots:
        index(r)

    # compose world transforms via parent chains (memoized)
    def world(o: LayoutObject) -> Matrix4:
        if o._world is not None:
            return o._world
        local = o.local_matrix()
        p = by_id.get(o.parent_id)
        if p is not None and p is not o:
            w = world(p) @ local
        else:
            w = local
        o._world = w
        return w

    for o in all_objs:
        world(o)

    return Layout(version, roots, by_id, all_objs)


def load_layout_file(path: str) -> Layout:
    with open(path, "rb") as f:
        return parse_layout(f.read())


def iter_room_pieces(layout: Layout):
    """Yield room-piece objects (DESCRIPTOR == 'Room Piece')."""
    for o in layout.all_objects:
        if o.descriptor == "Room Piece":
            yield o
