"""
mpp_survey.py — ground-truth survey of TL2 .MPP pathing files.

Purpose (byte-exact reproduction baseline):
  Parse every real .MPP under the TL2 install, decode the 24-byte header
  (verified against EditorGuts.dll writer sub_10200920), verify the size
  invariant, map each .mpp to its sibling .layout, and tabulate the EXACT
  relationships we must reproduce:
    - gridW/gridH vs boundsX/Z / 0.4   (rounding rule: round? ceil? floor?)
    - worldExt (f0/f1) vs bounds (f2/f3) ratio  (half? equal? varies?)
    - per-file & aggregate cell histograms (0=walkable, 1=blocked, 0xFF=oob)

Header layout (little-endian):
    int32  gridW       +0x00   cells in X
    int32  gridH       +0x04   cells in Z
    float  worldExtX   +0x08   = worldExt.x - boxMin.x
    float  worldExtZ   +0x0C   = worldExt.z - boxMin.z
    float  boundsX     +0x10   = boxMax.x - boxMin.x  (== gridW*0.4)
    float  boundsZ     +0x14   = boxMax.z - boxMin.z  (== gridH*0.4)
    uint8  cells[gridW*gridH]  +0x18

Usage:
    python tools/mpp_survey.py                 # scan default TL2 install, print report
    python tools/mpp_survey.py --json out.json # also dump full per-file records
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from collections import Counter
from pathlib import Path

CELL = 0.4  # world units per grid cell (EditorGuts.dll constant 0.4f)

# Hardcoded TL2 install (mirrors parse_layout.py TL2_MEDIA_DIR).
TL2_MEDIA_DIR = Path(r"E:\Torchlight 2\MEDIA")

HEADER_FMT = "<iiffff"
HEADER_SIZE = 24


class MppRecord:
    __slots__ = (
        "path", "size", "gridW", "gridH",
        "worldExtX", "worldExtZ", "boundsX", "boundsZ",
        "size_ok", "layout_path", "cell_counts",
    )

    def __init__(self, path: Path):
        self.path = path
        self.size = path.stat().st_size
        data = path.read_bytes()
        (self.gridW, self.gridH,
         self.worldExtX, self.worldExtZ,
         self.boundsX, self.boundsZ) = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
        body = data[HEADER_SIZE:]
        self.size_ok = (self.size == HEADER_SIZE + self.gridW * self.gridH)
        # cell histogram (only the 3 known values + 'other')
        c = Counter(body)
        self.cell_counts = {
            "walkable_0": c.get(0, 0),
            "blocked_1": c.get(1, 0),
            "oob_255": c.get(255, 0),
            "other": len(body) - c.get(0, 0) - c.get(1, 0) - c.get(255, 0),
        }
        self.layout_path = self._find_layout()

    def _find_layout(self) -> str | None:
        stem = self.path.with_suffix("")  # drop .mpp
        for ext in (".LAYOUT", ".layout", ".LAYOUT.BINLAYOUT", ".layout.binlayout"):
            cand = Path(str(stem) + ext)
            if cand.exists():
                return str(cand)
        return None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size": self.size,
            "size_ok": self.size_ok,
            "gridW": self.gridW,
            "gridH": self.gridH,
            "worldExtX": self.worldExtX,
            "worldExtZ": self.worldExtZ,
            "boundsX": self.boundsX,
            "boundsZ": self.boundsZ,
            "layout_path": self.layout_path,
            "cells": self.cell_counts,
        }


def find_mpp_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".mpp"):
                out.append(Path(dirpath) / fn)
    return out


def classify_rounding(grid: int, ext: float) -> str:
    """How does gridW relate to boundsX/0.4 ? round / ceil / floor / off-by."""
    import math
    q = ext / CELL
    if grid == round(q):
        return "round"
    if grid == math.ceil(q - 1e-6):
        return "ceil"
    if grid == math.floor(q + 1e-6):
        return "floor"
    return f"off{grid - q:+.3f}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Survey TL2 .MPP pathing files")
    ap.add_argument("--root", default=str(TL2_MEDIA_DIR), help="MEDIA root to scan")
    ap.add_argument("--json", default=None, help="dump full per-file records to this JSON")
    ap.add_argument("--show", type=int, default=12, help="how many example rows to print")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"[!] MEDIA root not found: {root}", file=sys.stderr)
        return 2

    files = find_mpp_files(root)
    print(f"Scanning {root} ... found {len(files)} .mpp files\n")

    recs: list[MppRecord] = []
    bad_size = []
    for p in files:
        try:
            r = MppRecord(p)
        except Exception as e:  # noqa: BLE001
            print(f"[!] failed to parse {p}: {e}", file=sys.stderr)
            continue
        recs.append(r)
        if not r.size_ok:
            bad_size.append(r)

    # ---- aggregate stats -------------------------------------------------
    n = len(recs)
    n_layout = sum(1 for r in recs if r.layout_path)
    round_rule_w = Counter(classify_rounding(r.gridW, r.boundsX) for r in recs)
    round_rule_h = Counter(classify_rounding(r.gridH, r.boundsZ) for r in recs)

    # boundsX vs gridW*0.4 exactness (float32)
    import numpy as np
    exact_bx = 0
    exact_bz = 0
    ext_ratio_x = Counter()
    for r in recs:
        bx32 = np.float32(r.gridW) * np.float32(CELL)
        bz32 = np.float32(r.gridH) * np.float32(CELL)
        if abs(float(bx32) - r.boundsX) < 1e-4:
            exact_bx += 1
        if abs(float(bz32) - r.boundsZ) < 1e-4:
            exact_bz += 1
        # worldExt vs bounds ratio (rounded to 0.05 buckets)
        if r.boundsX > 1e-6:
            ext_ratio_x[round(r.worldExtX / r.boundsX, 2)] += 1

    only_oob = sum(1 for r in recs if r.cell_counts["blocked_1"] == 0
                   and r.cell_counts["walkable_0"] == 0)
    has_blocked = sum(1 for r in recs if r.cell_counts["blocked_1"] > 0)
    has_walk = sum(1 for r in recs if r.cell_counts["walkable_0"] > 0)
    has_other = sum(1 for r in recs if r.cell_counts["other"] > 0)

    tot_cells = Counter()
    for r in recs:
        for k, v in r.cell_counts.items():
            tot_cells[k] += v

    dims = [(r.gridW, r.gridH) for r in recs]
    minw = min(d[0] for d in dims); maxw = max(d[0] for d in dims)
    minh = min(d[1] for d in dims); maxh = max(d[1] for d in dims)

    print("=" * 70)
    print(f"  files parsed        : {n}")
    print(f"  size invariant ok   : {n - len(bad_size)}/{n}"
          + ("" if not bad_size else f"   BAD: {len(bad_size)}"))
    print(f"  have sibling .layout: {n_layout}/{n}")
    print(f"  grid dims range     : W {minw}..{maxw}   H {minh}..{maxh}")
    print("-" * 70)
    print(f"  gridW vs boundsX/0.4 rounding : {dict(round_rule_w)}")
    print(f"  gridH vs boundsZ/0.4 rounding : {dict(round_rule_h)}")
    print(f"  boundsX == f32(gridW*0.4)     : {exact_bx}/{n}")
    print(f"  boundsZ == f32(gridH*0.4)     : {exact_bz}/{n}")
    print(f"  worldExtX/boundsX ratio buckets (top): "
          f"{dict(ext_ratio_x.most_common(8))}")
    print("-" * 70)
    print(f"  cell totals         : {dict(tot_cells)}")
    print(f"  files all-oob       : {only_oob}")
    print(f"  files w/ walkable(0): {has_walk}")
    print(f"  files w/ blocked(1) : {has_blocked}")
    print(f"  files w/ other vals : {has_other}")
    print("=" * 70)

    if bad_size:
        print("\n[!] size-invariant FAILURES (header lies / format variance):")
        for r in bad_size[:20]:
            print(f"    {r.path.name}: size={r.size} hdr={r.gridW}x{r.gridH} "
                  f"=> expect {24 + r.gridW*r.gridH}")

    print(f"\nExamples (first {args.show}):")
    print(f"  {'name':<34} {'W':>5} {'H':>5} {'wExtX':>8} {'wExtZ':>8} "
          f"{'bndX':>8} {'bndZ':>8}  {'cells(0/1/255)'}")
    for r in recs[:args.show]:
        cc = r.cell_counts
        print(f"  {r.path.name:<34} {r.gridW:>5} {r.gridH:>5} "
              f"{r.worldExtX:>8.2f} {r.worldExtZ:>8.2f} "
              f"{r.boundsX:>8.2f} {r.boundsZ:>8.2f}  "
              f"{cc['walkable_0']}/{cc['blocked_1']}/{cc['oob_255']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps([r.to_dict() for r in recs], indent=2), encoding="utf-8")
        print(f"\nWrote {n} records to {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
