"""Test the user's idea: Compile/RAW/MPP are independent (read sources, write
disjoint override keys) -> run them CONCURRENTLY (3 threads, shared overrides),
then Pack. Measures wall-clock vs sequential AND verifies the resulting overrides
are byte-identical (so Pack's output would be unchanged). The open question is
oversubscription: each stage already saturates the cores with its own pool."""
import os, sys, io, contextlib, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P

MODS = r"E:\Torchlight 2\mods"


def _compile(media, ov):
    P.convert_all(media, overrides=ov, mpp="none", raw="none")


def _raw(media, ov):
    P.generate_raw_files(media, overrides=ov)


def _mpp(media, ov):
    P.generate_mpp_files(media, overrides=ov, backend="re")


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 34000
    media = name = None
    for n in sorted(os.listdir(MODS)):
        md = os.path.join(MODS, n, "MEDIA")
        if not os.path.isdir(md):
            continue
        if lo <= sum(len(fs) for _, _, fs in os.walk(md)) <= hi:
            name, media = n, md; break
    print("mod:", name.encode("ascii", "replace").decode())

    with contextlib.redirect_stdout(io.StringIO()):
        # warm caches once (numba JIT, string dict, etc.) so we measure steady state
        P.convert_all(media, overrides={}, mpp="none", raw="none")

        # sequential
        ov1 = {}
        t = time.time()
        _compile(media, ov1); _raw(media, ov1); _mpp(media, ov1)
        t_seq = time.time() - t

        # variant A: all 3 concurrent (CPU stages contend)
        ovA = {}
        t = time.time()
        ths = [threading.Thread(target=fn, args=(media, ovA))
               for fn in (_compile, _raw, _mpp)]
        for th in ths: th.start()
        for th in ths: th.join()
        t_A = time.time() - t

        # variant B: RAW (I/O) overlaps the CPU stages, which run sequentially
        ovB = {}
        t = time.time()
        raw_th = threading.Thread(target=_raw, args=(media, ovB))
        raw_th.start()
        _compile(media, ovB); _mpp(media, ovB)
        raw_th.join()
        t_B = time.time() - t

    print("  sequential            : %.2fs" % t_seq)
    print("  A) all-3 concurrent   : %.2fs   (%.2fx)   bytes==%s" % (t_A, t_seq / t_A, ovA == ov1))
    print("  B) RAW || (Comp->MPP) : %.2fs   (%.2fx)   bytes==%s" % (t_B, t_seq / t_B, ovB == ov1))


if __name__ == "__main__":
    main()
