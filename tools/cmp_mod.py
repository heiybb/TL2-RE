"""Comprehensive native-vs-ours .MOD diff (guarded). Reports:
  * header field diffs
  * dir-node name-set diff (which empty/extra dir nodes each side has)
  * per-file payload classification: byte-identical / bindat-semantically-equal /
    differ — bucketed by extension, so we see exactly what content is wrong.
"""
import os, sys, io, zlib, struct, contextlib, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P
from mikuro_mod_packer import bindat


def load(raw):
    h, dirs = P._disasm_mod(raw)
    base = h['offData']
    pay, dnodes = {}, set()
    for dname, recs in dirs:
        for (crc, typ, name, off, size, ft) in recs:
            if typ == P._TYPE_DIR:
                dnodes.add((dname + name).upper())
                continue
            a = base + off
            decsz, csz = struct.unpack_from('<II', raw, a)
            blob = raw[a + 8: a + 8 + (csz if csz else decsz)]
            pay[(dname + name).upper()] = (typ, blob if csz == 0 else zlib.decompress(blob))
    return h, dnodes, pay


def main():
    native_path, src_dir = sys.argv[1], sys.argv[2]
    media = os.path.join(src_dir, "MEDIA")
    nat = open(native_path, "rb").read()
    with contextlib.redirect_stdout(io.StringIO()):
        ov = {}
        P.convert_all(media, overrides=ov, mpp="re", raw="auto")
        tmp = os.path.join(tempfile.gettempdir(), "__cmp_ours.MOD")
        mname = P.read_mod_metadata(src_dir)["name"]
        P.pack_mod(media, tmp, mname, original_mod_dir=src_dir, overrides=ov)
    our = open(tmp, "rb").read()

    hn, ddn, pn = load(nat)
    ho, ddo, po = load(our)

    print("=== DIR NODE sets ===")
    print("  native dir-nodes:", len(ddn), " ours:", len(ddo))
    for d in sorted(ddn - ddo):
        print("   only NATIVE dir:", d)
    for d in sorted(ddo - ddn):
        print("   only OURS   dir:", d)

    print("\n=== PER-FILE PAYLOAD by extension ===")
    # buckets[ext] = [identical, sem_equal, differ, n]
    buckets = collections.defaultdict(lambda: [0, 0, 0, 0])
    differ_examples = collections.defaultdict(list)
    for f in sorted(set(pn) & set(po)):
        ext = f.rsplit(".", 1)[-1] if "." in f else "(none)"
        tn, bn = pn[f]; to, bo = po[f]
        b = buckets[ext]; b[3] += 1
        if bn == bo:
            b[0] += 1
            continue
        # try bindat semantic equality
        sem = None
        if ext == "DAT":
            try:
                sem = (bindat._decode_dat_bytes(bn) == bindat._decode_dat_bytes(bo))
            except Exception:
                sem = None
        if sem:
            b[1] += 1
        else:
            b[2] += 1
            if len(differ_examples[ext]) < 3:
                differ_examples[ext].append((f, len(bn), len(bo), sem))

    print("  %-10s %8s %8s %8s %6s" % ("ext", "identical", "sem_eq", "DIFFER", "total"))
    for ext in sorted(buckets):
        i, s, d, n = buckets[ext]
        print("  %-10s %8d %8d %8d %6d" % (ext, i, s, d, n))

    print("\n=== DIFFER examples (non-bindat-equal) ===")
    for ext, exs in sorted(differ_examples.items()):
        for (f, ln, lo, sem) in exs:
            print(f"  {ext}: {f}  native_len={ln} our_len={lo} sem={sem}")

    # Header recap
    print("\n=== HEADER recap ===")
    for k in ("fc", "mhash"):
        print(f"  {k}: native={hn[k]} ours={ho[k]}")


if __name__ == "__main__":
    main()
