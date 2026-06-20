"""Isolate the Pack (zlib) cost and measure the optimization levers: thread count
and zlib level. Converts one Pack-heavy mod, builds its data blocks exactly like
pack_mod, then times compress+crc of all blocks under each config (output size
reported too — lower level / fewer threads trade size for speed)."""
import os, sys, zlib, time, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P
from concurrent.futures import ThreadPoolExecutor

MODS = r"E:\Torchlight 2\mods"


def pick(lo, hi):
    for n in os.listdir(MODS):
        md = os.path.join(MODS, n, "MEDIA")
        if not os.path.isdir(md):
            continue
        nf = sum(len(fs) for _, _, fs in os.walk(md))
        if lo <= nf <= hi:
            return n, md
    return None


def main():
    # default: 通用素材01 (~12.7k files, 264 MB out — byte-heavy, fast convert)
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 27000
    name, media = pick(lo, hi)
    print("mod files:", sum(len(fs) for _, _, fs in os.walk(media)))

    with contextlib.redirect_stdout(io.StringIO()):
        ov = {}
        P.convert_all(media, overrides=ov, mpp="none", raw="auto")

    # build the block list exactly like pack_mod Pass A
    dirs, _ = P.build_manifest_dirs(media, ov)
    blocks = []
    for dname, recs in dirs:
        for (crc, typ, name2, off, size, ft) in recs:
            if typ == P._TYPE_DIR:
                continue
            full = (dname + name2).upper()
            rel = full[6:] if full.startswith("MEDIA/") else full
            content = P._content_for(rel, media, ov)
            if content is None:
                continue
            store = typ in P._STORE_TYPES or len(content) >= 0x1900000
            if not store:
                blocks.append(content)
    raw_bytes = sum(len(b) for b in blocks)
    print("compressible blocks: %d   raw bytes: %.1f MB" % (len(blocks), raw_bytes / 1e6))

    try:
        from isal import isal_zlib
    except ImportError:
        isal_zlib = None

    def run(backend, level, threads):
        z = isal_zlib if backend == "isal" else zlib
        def job(c):
            return len(z.compress(c, level)), z.crc32(c)
        t = time.time()
        with ThreadPoolExecutor(max_workers=threads) as ex:
            outsz = sum(n for n, _ in ex.map(job, blocks, chunksize=8))
        return time.time() - t, outsz

    print("\n  %-24s %8s %10s %8s" % ("config", "time(s)", "out(MB)", "MB/s"))
    base = None
    configs = [
        ("zlib L6 x8  (orig)", "zlib", 6, 8),
        ("zlib L6 x16 (now)",  "zlib", 6, 16),
    ]
    if isal_zlib is not None:
        configs += [
            ("isal L3 x16", "isal", 3, 16),
            ("isal L2 x16", "isal", 2, 16),
            ("isal L1 x16", "isal", 1, 16),
        ]
    for label, backend, level, threads in configs:
        dt, outsz = run(backend, level, threads)
        if base is None:
            base = dt
        print("  %-24s %8.2f %10.1f %8.1f   (%.2fx vs orig)"
              % (label, dt, outsz / 1e6, raw_bytes / 1e6 / dt, base / dt))


if __name__ == "__main__":
    main()
