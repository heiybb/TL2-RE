"""Verify pooled RAW == serial RAW (byte-identical) and time the win on a big mod.
Real .py file (Windows spawn needs an importable __main__)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P
from mikuro_mod_packer import raw as rg
from concurrent.futures import ProcessPoolExecutor

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
    print("mod:", name.encode("ascii", "replace").decode(), " DATs:", nd)

    # serial reference
    t = time.time(); su = rg.build_unitdata(media); t_su = time.time() - t
    t = time.time(); sa = rg.build_affixes(media);  t_sa = time.time() - t
    t = time.time(); ss = rg.build_skills(media);    t_ss = time.time() - t

    # pooled
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1),
                             initializer=rg._raw_pool_init, initargs=(media,)) as ex:
        t = time.time(); pu = rg.build_unitdata_parallel(media, ex); t_pu = time.time() - t
        t = time.time(); pa = rg.build_affixes_parallel(media, ex);  t_pa = time.time() - t
        t = time.time(); ps = rg.build_skills_parallel(media, ex);    t_ps = time.time() - t

    print("  UNITDATA : identical=%s  serial %.2fs -> pooled %.2fs (%.2fx)" % (su == pu, t_su, t_pu, t_su / max(1e-9, t_pu)))
    print("  AFFIXES  : identical=%s  serial %.2fs -> pooled %.2fs (%.2fx)" % (sa == pa, t_sa, t_pa, t_sa / max(1e-9, t_pa)))
    print("  SKILLS   : identical=%s  serial %.2fs -> pooled %.2fs (%.2fx)" % (ss == ps, t_ss, t_ps, t_ss / max(1e-9, t_ps)))

    # end-to-end generate_raw_files (auto-parallel) vs forced serial
    ovp = {}; t = time.time(); P.generate_raw_files(media, overrides=ovp); t_auto = time.time() - t
    saved = P._MP_MIN_RAW_ITEMS
    P._MP_MIN_RAW_ITEMS = 10**9   # force serial
    ovs = {}; t = time.time(); P.generate_raw_files(media, overrides=ovs); t_ser = time.time() - t
    P._MP_MIN_RAW_ITEMS = saved
    print("  generate_raw_files: serial %.2fs -> auto-pool %.2fs (%.2fx)  outputs-equal=%s"
          % (t_ser, t_auto, t_ser / max(1e-9, t_auto), ovp == ovs))


if __name__ == "__main__":
    main()
