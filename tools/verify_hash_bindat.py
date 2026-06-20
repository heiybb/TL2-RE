"""Verify the production per-file-hash BINDAT compiler: (a) serial == parallel
(byte-identical, deterministic), (b) every file semantically == the old corpus
build, (c) the parallel speedup."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P
import mikuro_mod_packer.bindat as B
import importlib.util
_s = importlib.util.spec_from_file_location(
    "proto", os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto_hash_bindat.py"))
proto = importlib.util.module_from_spec(_s); _s.loader.exec_module(proto)

MODS = r"E:\Torchlight 2\mods"


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 14000
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
    media = None
    for n in os.listdir(MODS):
        md = os.path.join(MODS, n, "MEDIA")
        if not os.path.isdir(md):
            continue
        nd = sum(1 for r, _, fs in os.walk(md)
                 for f in fs if f.upper().endswith(".DAT") and ".BIN" not in f.upper())
        if lo <= nd <= hi:
            media = md; break
    print("mod DATs:", nd)
    jobs = [(os.path.join(r, f), os.path.join(r, f + ".BINDAT")) for r, _, fs in os.walk(media)
            for f in fs if f.upper().endswith(".DAT") and ".BIN" not in f.upper()]

    ovs, rs = {}, {"bindat": 0, "errors": []}
    t = time.time(); P._compile_bindat_serial(jobs, media, ovs, rs); t_ser = time.time() - t
    ovp, rp = {}, {"bindat": 0, "errors": []}
    t = time.time(); P._compile_bindat_parallel(jobs, media, ovp, rp); t_par = time.time() - t
    print("serial %.2fs  parallel %.2fs  (%.2fx)  serial==parallel bytes: %s  (errors %d/%d)"
          % (t_ser, t_par, t_ser / max(1e-9, t_par), ovs == ovp, len(rs["errors"]), len(rp["errors"])))

    # semantic equivalence vs the old corpus build (sample)
    sd = B.get_string_dict(r"E:\Torchlight 2\MEDIA")
    eq = neq = 0
    for dp, bp in jobs[:1000]:
        text = B._decode_dat_bytes(open(dp, "rb").read())
        if proto.canon(B.compile_dat(text)) == proto.canon(B.compile_dat(text, sd)):
            eq += 1
        else:
            neq += 1
    print("semantic equivalence hash-vs-corpus (sample %d): %d ok, %d diff" % (eq + neq, eq, neq))


if __name__ == "__main__":
    main()
