"""
CLI: generate a Version-B .mpp from a .layout.

    python -m mikuro_mod_packer.mpp <LAYOUT> <OUT.mpp> [--snap 10]
"""
from __future__ import annotations

import argparse
import sys

from .pipeline import Context, generate_mpp

MEDIA = r"E:\Torchlight 2\MEDIA"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("out")
    ap.add_argument("--media", default=MEDIA)
    ap.add_argument("--snap", type=float, default=10.0,
                    help="quantize the region box outward to this tile size (0 = off)")
    args = ap.parse_args(argv)

    ctx = Context(args.media)
    hdr = generate_mpp(args.layout, args.out, ctx, snap=args.snap)
    print(f"wrote {args.out}: grid {hdr['gridW']}x{hdr['gridH']} "
          f"bounds {hdr['boundsX']:.1f}x{hdr['boundsZ']:.1f} "
          f"worldExt {hdr['worldExtX']:.1f}x{hdr['worldExtZ']:.1f} "
          f"origin {hdr['originX']:.2f}x{hdr['originZ']:.2f} "
          f"(pieces used={hdr['region'].n_pieces_used}, missing={hdr['region'].n_pieces_missing})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
