"""
writer.py — .mpp byte writer (24-byte header + gridW*gridH cell bytes).

Byte-exact to CLevel_BuildWritePathingGrid_MPP's 6 fwrites (0x10200920):
    [0]  int32  gridW     cells in X
    [4]  int32  gridH     cells in Z
    [8]  float  worldExtX = worldExt.x - boxMin.x
    [12] float  worldExtZ = worldExt.z - boxMin.z
    [16] float  boundsX   = boxMax.x - boxMin.x
    [20] float  boundsZ   = boxMax.z - boxMin.z
    [24] uint8  cells[gridW*gridH]   row-major: index = i + gridW*j (i=X, j=Z)
                0x00 walkable, 0x01 blocked, 0xFF out-of-bounds
"""
from __future__ import annotations

import struct

import numpy as np


def write_mpp(path, gridW, gridH, worldExtX, worldExtZ, boundsX, boundsZ, cells):
    header = struct.pack(
        "<iiffff",
        int(gridW), int(gridH),
        np.float32(worldExtX), np.float32(worldExtZ),
        np.float32(boundsX), np.float32(boundsZ),
    )
    body = np.asarray(cells, dtype=np.uint8).tobytes()
    if len(body) != gridW * gridH:
        raise ValueError(f"cell count {len(body)} != {gridW}*{gridH}")
    with open(path, "wb") as f:
        f.write(header)
        f.write(body)
    return 24 + len(body)
