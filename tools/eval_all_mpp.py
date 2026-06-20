"""
eval_all_mpp.py — measure native.py's MPP grid against EVERY shipped .mpp in
E:\\Torchlight 2\\MEDIA\\LAYOUTS (the "ultimate gap").

native.build_grid tests every collision triangle per cell. Only triangles whose
XZ-AABB (expanded by the swept radius / clearance length) overlaps the cell's
(x,z) can possibly be hit by the vertical down-ray or the 0.3 clearance probes, so
an XZ bucket index gives BYTE-IDENTICAL grids far faster. fast_build_grid is
validated == native.build_grid before any corpus run.

usage:
  python tools/eval_all_mpp.py validate
  python tools/eval_all_mpp.py run <cell_cap> <out.jsonl>     # parallel corpus sweep
"""
import os, sys, struct, time, json, math
sys.path.insert(0, ".")

MEDIA = r"E:\Torchlight 2\MEDIA"
LAYOUTS = os.path.join(MEDIA, "LAYOUTS")
BUCKET = 2.0   # XZ bucket size (>> radius 0.1 and clearance 0.3)
REACH = os.environ.get("MPP_REACH") == "1"     # ground-reachability void pass (default OFF;
                                               # net corpus regression, see native.build_grid)
LINKS = os.environ.get("MPP_LINKS") == "1"     # opt-in structural Layout-Link sub-layout
                                               # collision (default OFF; see gather(assemble_links))

import mikuro_mod_packer.mpp.native as N
from mikuro_mod_packer.mpp.pipeline import Context, generate_header


def fast_build_grid(layout, ctx, box, origin_x, origin_z, gw, gh):
    """Thin wrapper over the package's bucket-culled builder (now lives in
    native.build_grid_fast), threading the eval's REACH/LINKS env opt-ins."""
    return N.build_grid_fast(layout, ctx, box, origin_x, origin_z, gw, gh,
                             reachability=REACH, assemble_links=LINKS)


def validate():
    ctx = Context(MEDIA)
    tests = [
        r"E:\Torchlight 2\MEDIA\LAYOUTS\ACT3_Z1\1X1_CONCAVE_S2W1\1X1_CONCAVE_S2W1_BB_A.LAYOUT",
        r"E:\Torchlight 2\MEDIA\LAYOUTS\ACT3_Z1\1X1_CONCAVE_S2W1\1X1_CONCAVE_S2W1_PB_A.LAYOUT",
        r"E:\Torchlight 2\MEDIA\LAYOUTS\MAINMENUS\1X1SINGLE_ROOM_TOWN3\MAINMENU_TOWN3.LAYOUT",
    ]
    ok = True
    for lp in tests:
        hdr = generate_header(lp, ctx)
        a = N.build_grid(hdr["layout"], ctx, hdr["box"], hdr["originX"], hdr["originZ"], hdr["gridW"], hdr["gridH"])[0]
        t0 = time.time()
        b = fast_build_grid(hdr["layout"], ctx, hdr["box"], hdr["originX"], hdr["originZ"], hdr["gridW"], hdr["gridH"])[0]
        same = (a == b)
        ok = ok and same
        print(f"  {os.path.basename(lp):42s} fast=={'BYTE-IDENTICAL' if same else 'DIFFERENT!!'}  ({time.time()-t0:.2f}s fast)")
    print("VALIDATION:", "PASS" if ok else "FAIL")
    return ok


# ---------- parallel corpus runner ----------
_CTX = None
def _init():
    global _CTX
    _CTX = Context(MEDIA)

def _work(args):
    lp, mp, sgw, sgh = args
    t0 = time.time()
    rel = lp.split("LAYOUTS" + os.sep, 1)[-1]
    try:
        shipped = open(mp, "rb").read()
        hdr = generate_header(lp, _CTX)
        g, gw, gh = fast_build_grid(hdr["layout"], _CTX, hdr["box"], hdr["originX"], hdr["originZ"], hdr["gridW"], hdr["gridH"])
        import numpy as np
        gs = np.frombuffer(shipped[24:], np.uint8)
        go = np.frombuffer(g, np.uint8)
        dims_match = (gw == sgw and gh == sgh and gs.size == go.size)
        # full-byte exact (header + body)
        header = struct.pack("<ii4f", gw, gh,
                             hdr["box"].max.x - hdr["box"].min.x, hdr["box"].max.z - hdr["box"].min.z,
                             hdr["box"].max.x - hdr["box"].min.x, hdr["box"].max.z - hdr["box"].min.z)
        byte_exact = (header + g == shipped)
        out = {"rel": rel, "cells": sgw * sgh, "sec": round(time.time() - t0, 2),
               "dims_match": dims_match, "byte_exact": byte_exact}
        if dims_match:
            diff = int((go != gs).sum())
            out["diff"] = diff
            out["status"] = "ok"
            # full shipped->native transition counts (codes 0=walk 1=wall 255=void)
            def cnt(sv, ov): return int(((gs == sv) & (go == ov)).sum())
            out["w2W"] = cnt(0, 1)      # over-block  (walkable -> wall)   PATHING
            out["W2w"] = cnt(1, 0)      # under-block (wall -> walkable)   PATHING
            out["w2V"] = cnt(0, 255)    # walkable -> void                PATHING (footprint)
            out["V2w"] = cnt(255, 0)    # void -> walkable                PATHING (footprint)
            out["W2V"] = cnt(1, 255)    # wall -> void                    cosmetic
            out["V2W"] = cnt(255, 1)    # void -> wall                    cosmetic
            out["over"] = out["w2W"]; out["under"] = out["W2w"]
        else:
            out["status"] = "dim-mismatch"; out["dims"] = [gw, gh, sgw, sgh]
        return out
    except Exception as ex:
        return {"rel": rel, "status": "error", "err": repr(ex)[:180], "sec": round(time.time() - t0, 2)}


def run(cell_cap, outpath):
    from multiprocessing import Pool, cpu_count
    rows = []
    for dp, dn, fn in os.walk(LAYOUTS):
        have = {f.upper(): f for f in fn}
        for up, real in have.items():
            if up.endswith(".LAYOUT") and up[:-7] + ".MPP" in have:
                lp = os.path.join(dp, real); mp = os.path.join(dp, have[up[:-7] + ".MPP"])
                try:
                    gw, gh = struct.unpack("<ii", open(mp, "rb").read(8))
                    rows.append((gw * gh, lp, mp, gw, gh))
                except Exception:
                    pass
    rows.sort()
    todo = [(lp, mp, gw, gh) for (c, lp, mp, gw, gh) in rows if c <= cell_cap]
    skipped = [(c, lp) for (c, lp, mp, gw, gh) in rows if c > cell_cap]
    print(f"total={len(rows)} running={len(todo)} skipped_large(>{cell_cap})={len(skipped)}", flush=True)
    nproc = max(1, cpu_count() - 2)
    done = 0; t0 = time.time()
    with open(outpath, "w") as out, Pool(nproc, initializer=_init) as pool:
        for res in pool.imap_unordered(_work, todo, chunksize=1):
            out.write(json.dumps(res) + "\n"); out.flush()
            done += 1
            if done % 25 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"  {done}/{len(todo)}  ({el:.0f}s, {el/done:.1f}s/ea, eta {el/done*(len(todo)-done)/60:.0f}min)", flush=True)
    # write the skipped list too
    with open(outpath, "a") as out:
        for c, lp in skipped:
            out.write(json.dumps({"rel": lp.split("LAYOUTS" + os.sep, 1)[-1], "status": "skip-large", "cells": c}) + "\n")
    print("DONE", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "validate":
        validate()
    elif sys.argv[1] == "run":
        run(int(sys.argv[2]), sys.argv[3])
