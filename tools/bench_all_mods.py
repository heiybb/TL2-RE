"""Benchmark the mikuro_mod_packer over every installed Torchlight 2 mod.

Builds each mod's .MOD entirely FROM SCRATCH (no editor, no GUTS), in memory,
without modifying the source mod, and reports the wall-clock time of each
pipeline stage. Run with NO other heavy process active (CPU contention skews the
timings of the large mods).

Pipeline stages timed per mod:
  Compile : DAT -> BINDAT  +  LAYOUT -> BINLAYOUT   (from-scratch binary compilers)
  RAW     : the 7 index files (AFFIXES/SKILLS/MISSILES/TRIGGERABLES/UNITDATA/UI/
            ROOMPIECES) -- only the content types this mod actually ships
  MPP     : .MPP pathing grids, offline numba backend -- only level layouts under
            MEDIA/LAYOUTS/ (0 for mods with no levels)
  Pack    : assemble the .MOD container (zlib-compress every block + manifest tree)
"""
import os, sys, time, tempfile, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODS = r"E:\Torchlight 2\mods"


def main():
    import mikuro_mod_packer.packer as P

    print("Torchlight 2 mod packer -- from-scratch build benchmark", flush=True)
    print("(in-memory, non-mutating; single machine, 16 cores; times in seconds)\n", flush=True)
    hdr = ("%-30s %7s %8s %8s %7s %7s %7s %8s %7s"
           % ("Mod", "Files", "Out(MB)", "Compile", "RAW", "MPP", "Pack", "Total", "MB/s"))
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)

    rows = []
    for name in sorted(os.listdir(MODS)):
        d = os.path.join(MODS, name)
        media = os.path.join(d, "MEDIA")
        if not os.path.isdir(media) or not os.path.exists(os.path.join(d, "MOD.DAT")):
            continue
        nfiles = sum(len(fn) for _, _, fn in os.walk(media))
        try:
            mname = P.read_mod_metadata(d)["name"]
            ov = {}
            with contextlib.redirect_stdout(io.StringIO()):
                t = time.time()
                P.convert_all(media, overrides=ov, mpp="none", raw="none")   # Compile only
                t_compile = time.time() - t

                t = time.time()
                n_raw = P.generate_raw_files(media, overrides=ov)             # RAW indexes
                t_raw = time.time() - t

                t = time.time()
                n_mpp = P.generate_mpp_files(media, overrides=ov, backend="re")  # MPP grids
                t_mpp = time.time() - t

                out = os.path.join(tempfile.gettempdir(), "__bm_%d.MOD" % (abs(hash(name)) % 10**9))
                t = time.time()
                sz = P.pack_mod(media, out, mname, original_mod_dir=d, overrides=ov)  # Pack
                t_pack = time.time() - t
            if os.path.exists(out):
                os.remove(out)
            total = t_compile + t_raw + t_mpp + t_pack
            mbps = (sz / 1e6) / total if total else 0
            rows.append((name, nfiles, sz, t_compile, t_raw, n_raw, t_mpp, n_mpp, t_pack, total, mbps))
            print("%-30s %7d %8.1f %8.2f %7.2f %7.2f %7.2f %8.2f %7.1f"
                  % (name[:30], nfiles, sz / 1e6, t_compile, t_raw, t_mpp, t_pack, total, mbps), flush=True)
        except Exception as e:
            print("%-30s  ERROR  %s" % (name[:30], repr(e)[:64]), flush=True)

    print("-" * len(hdr), flush=True)
    if rows:
        tf = sum(r[1] for r in rows); ts = sum(r[2] for r in rows)
        tc = sum(r[3] for r in rows); tr = sum(r[4] for r in rows)
        tm = sum(r[6] for r in rows); tp = sum(r[8] for r in rows); tt = sum(r[9] for r in rows)
        print("TOTAL: %d mods, %d files, %.0f MB output" % (len(rows), tf, ts / 1e6), flush=True)
        print("       Compile %.1fs + RAW %.1fs + MPP %.1fs + Pack %.1fs = %.1fs  (%.1f MB/s overall)"
              % (tc, tr, tm, tp, tt, (ts / 1e6) / tt if tt else 0), flush=True)


if __name__ == "__main__":
    main()
