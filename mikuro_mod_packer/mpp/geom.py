"""
geom.py — minimal Ogre-compatible 3D math for the pathing pipeline.

Coordinate system note: TL2 layouts store an orientation as a FORWARD vector
(+Z local axis) and a RIGHT vector (+X local axis). UP is derived as
FORWARD x RIGHT (this matches the convention used elsewhere in the repo:
get_global_transform composes T_parent x T_local with UP = Forward x Right).

A room-piece world transform is:  world = parent_world @ local
local = translate(pos) @ rotate(R) @ scale(s)
i.e. a column is an axis * scale; the 4th column is the position.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def cross(self, o: "Vec3") -> "Vec3":
        return Vec3(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )

    def dot(self, o: "Vec3") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vec3":
        n = self.length()
        if n < 1e-12:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / n, self.y / n, self.z / n)

    def as_tuple(self):
        return (self.x, self.y, self.z)


class Matrix4:
    """Row-major 4x4 affine transform. m[r][c]."""

    __slots__ = ("m",)

    def __init__(self, m=None):
        if m is None:
            self.m = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
        else:
            self.m = [list(row) for row in m]

    @staticmethod
    def translation(v: Vec3) -> "Matrix4":
        m = Matrix4()
        m.m[0][3] = v.x
        m.m[1][3] = v.y
        m.m[2][3] = v.z
        return m

    @staticmethod
    def scale(sx: float, sy: float, sz: float) -> "Matrix4":
        m = Matrix4()
        m.m[0][0] = sx
        m.m[1][1] = sy
        m.m[2][2] = sz
        return m

    @staticmethod
    def from_axes(right: Vec3, up: Vec3, forward: Vec3) -> "Matrix4":
        """Rotation matrix whose columns are the local X(right), Y(up), Z(forward) axes."""
        m = Matrix4()
        m.m[0][0], m.m[1][0], m.m[2][0] = right.x, right.y, right.z
        m.m[0][1], m.m[1][1], m.m[2][1] = up.x, up.y, up.z
        m.m[0][2], m.m[1][2], m.m[2][2] = forward.x, forward.y, forward.z
        return m

    def __matmul__(self, o: "Matrix4") -> "Matrix4":
        a, b = self.m, o.m
        r = Matrix4()
        for i in range(4):
            for j in range(4):
                r.m[i][j] = (
                    a[i][0] * b[0][j]
                    + a[i][1] * b[1][j]
                    + a[i][2] * b[2][j]
                    + a[i][3] * b[3][j]
                )
        return r

    def transform_point(self, v: Vec3) -> Vec3:
        m = self.m
        x = m[0][0] * v.x + m[0][1] * v.y + m[0][2] * v.z + m[0][3]
        y = m[1][0] * v.x + m[1][1] * v.y + m[1][2] * v.z + m[1][3]
        z = m[2][0] * v.x + m[2][1] * v.y + m[2][2] * v.z + m[2][3]
        return Vec3(x, y, z)


class AABB:
    """Axis-aligned bounding box. Tracks min/max; supports a null state."""

    __slots__ = ("min", "max", "null")

    def __init__(self, mn: Vec3 | None = None, mx: Vec3 | None = None):
        if mn is None or mx is None:
            self.null = True
            self.min = Vec3(0, 0, 0)
            self.max = Vec3(0, 0, 0)
        else:
            self.null = False
            self.min = mn
            self.max = mx

    def merge_point(self, p: Vec3) -> None:
        if self.null:
            self.min = p
            self.max = p
            self.null = False
        else:
            self.min = Vec3(min(self.min.x, p.x), min(self.min.y, p.y), min(self.min.z, p.z))
            self.max = Vec3(max(self.max.x, p.x), max(self.max.y, p.y), max(self.max.z, p.z))

    def merge(self, other: "AABB") -> None:
        if other.null:
            return
        self.merge_point(other.min)
        self.merge_point(other.max)

    def corners(self):
        mn, mx = self.min, self.max
        return [
            Vec3(mn.x, mn.y, mn.z),
            Vec3(mx.x, mn.y, mn.z),
            Vec3(mn.x, mx.y, mn.z),
            Vec3(mx.x, mx.y, mn.z),
            Vec3(mn.x, mn.y, mx.z),
            Vec3(mx.x, mn.y, mx.z),
            Vec3(mn.x, mx.y, mx.z),
            Vec3(mx.x, mx.y, mx.z),
        ]

    def transformed(self, mat: Matrix4) -> "AABB":
        """Ogre AxisAlignedBox::transform — re-fit an AABB around the 8 transformed corners."""
        if self.null:
            return AABB()
        out = AABB()
        for c in self.corners():
            out.merge_point(mat.transform_point(c))
        return out

    def __repr__(self):
        if self.null:
            return "AABB(null)"
        return f"AABB(min={self.min.as_tuple()}, max={self.max.as_tuple()})"


def orientation_axes(fwd: Vec3, right: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    """Given layout FORWARD and RIGHT, return (right, up, forward) orthonormal axes.

    UP = FORWARD x RIGHT (repo convention). Vectors are used as stored (already
    unit-length in TL2 layouts) but we normalize defensively.
    """
    f = fwd.normalized()
    r = right.normalized()
    up = f.cross(r).normalized()
    return r, up, f


def yaw_axes(yaw_deg: float) -> tuple[Vec3, Vec3, Vec3]:
    """Axes from a YAW (degrees) about +Y. Returns (right, up, forward)."""
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)
    # forward rotates in the XZ plane
    fwd = Vec3(sa, 0.0, ca)
    right = Vec3(ca, 0.0, -sa)
    up = Vec3(0.0, 1.0, 0.0)
    return right, up, fwd
