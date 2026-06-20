"""Break UNITDATA build into scan / own-read+parse / chain-resolve to see whether
a shared base-template cache can help (only if base reads + chain work — not the
already-parallel own-unit reads — dominate)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mikuro_mod_packer import raw as rg

MODS = r"E:\Torchlight 2\mods"


def pick(lo, hi):
    for name in os.listdir(MODS):
        media = os.path.join(MODS, name, "MEDIA")
        if not os.path.isdir(media):
            continue
        nd = sum(1 for r, _, fs in os.walk(media)
                 for f in fs if f.upper().endswith(".DAT") and ".BIN" not in f.upper())
        if lo <= nd <= hi:
            return name, media, nd
    return None


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 14000
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
    name, media, nd = pick(lo, hi)
    units_root = os.path.join(media, "UNITS")
    print("mod:", name.encode("ascii", "replace").decode(), " DATs:", nd)

    # 1. scan
    t = time.time()
    paths = []
    for cat in rg._UNIT_CATEGORIES:
        paths += list(rg._scan_interleaved(os.path.join(units_root, cat), ".DAT"))
    t_scan = time.time() - t

    # 2. own read+parse for every unit (fills cache with the unit's own attrs)
    cache = {}
    t = time.time()
    for dp in paths:
        rg._unit_attrs_for(dp, cache)
    t_fill = time.time() - t
    n_own = len(cache)

    # 3. chain resolve + field extract (adds base templates to cache on the way)
    t = time.time()
    for dp in paths:
        chain = rg._unit_chain(dp, media, cache=cache)
        rg._chain_str(chain, "UNIT_GUID", "")
        rg._chain_str(chain, "NAME", "")
        rg._chain_str(chain, "CREATEAS", "")
        rg._chain_str(chain, "SET", "")
        rg._chain_int(chain, "LEVEL", 1)
        rg._chain_int(chain, "RARITY", 1)
        rg._chain_str(chain, "UNITTYPE", "")
    t_chain = time.time() - t
    n_base = len(cache) - n_own

    print("  units            : %d" % len(paths))
    print("  scan             : %5.2fs" % t_scan)
    print("  own read+parse   : %5.2fs   (%d unit files)" % (t_fill, n_own))
    print("  chain+extract    : %5.2fs   (+%d distinct BASE templates read)" % (t_chain, n_base))
    print("  => base reads are %d files vs %d own; shared-base-cache helps only if"
          % (n_base, n_own))
    print("     chain+extract dominates and base re-reads (x workers) are the cost.")


if __name__ == "__main__":
    main()
