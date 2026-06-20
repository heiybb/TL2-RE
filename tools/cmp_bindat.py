"""Real BINDAT disassembler + semantic compare of native vs our compiled .DAT.

Decodes the embedded string table, walks the node-tree body resolving every
STRING/TRANSLATE prop's vid through THAT file's own table, and emits a canonical
structure (name_hash, props, children) where string props carry the RESOLVED
string (not the raw id). If native and ours produce the same canonical tree, our
BINDAT is semantically identical despite different id numbering -> not the bug.
"""
import os, sys, io, zlib, struct, contextlib, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.packer as P
import mikuro_mod_packer.bindat as B

STRING_TYPES = set(B.STRING_TYPES)   # (5, 8)
EMPTY = B.StringDict.EMPTY_ID


def read_table(data):
    """id -> string from the BINDAT header. Returns (id2s, body_offset)."""
    ver, scount, first_id = struct.unpack_from('<3I', data, 0)
    off = 12
    id2s = {}
    if scount:
        ln = struct.unpack_from('<H', data, off)[0]; off += 2
        id2s[first_id] = data[off:off + ln * 2].decode('utf-16-le', 'surrogatepass'); off += ln * 2
        for _ in range(scount - 1):
            i = struct.unpack_from('<I', data, off)[0]
            ln = struct.unpack_from('<H', data, off + 4)[0]; off += 6
            id2s[i] = data[off:off + ln * 2].decode('utf-16-le', 'surrogatepass'); off += ln * 2
    return id2s, off


def read_node(data, off, id2s):
    name_hash, nprop = struct.unpack_from('<II', data, off); off += 8
    props = []
    for _ in range(nprop):
        kh, tc = struct.unpack_from('<II', data, off); off += 8
        if tc == 7:
            v = struct.unpack_from('<Q', data, off)[0]; off += 8
            props.append((kh, tc, ('i64', v)))
        else:
            raw = struct.unpack_from('<I', data, off)[0]; off += 4
            if tc in STRING_TYPES:
                props.append((kh, tc, ('s', '' if raw == EMPTY else id2s.get(raw, f'<MISSING:{raw}>'))))
            else:
                props.append((kh, tc, ('n', raw)))
    nchild = struct.unpack_from('<I', data, off)[0]; off += 4
    children = []
    for _ in range(nchild):
        c, off = read_node(data, off, id2s)
        children.append(c)
    return (name_hash, tuple(props), tuple(children)), off


def canon(data):
    id2s, off = read_table(data)
    tree, _ = read_node(data, off, id2s)
    return tree


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

    def payloads(raw):
        h, dirs = P._disasm_mod(raw); base = h['offData']; out = {}
        for dname, recs in dirs:
            for (crc, typ, name, o, size, ft) in recs:
                if typ == P._TYPE_DIR or typ != 0:   # type 0 == BINDAT
                    continue
                a = base + o
                decsz, csz = struct.unpack_from('<II', raw, a)
                blob = raw[a + 8: a + 8 + (csz if csz else decsz)]
                out[(dname + name).upper()] = blob if csz == 0 else zlib.decompress(blob)
        return out

    pn, po = payloads(nat), payloads(our)
    common = sorted(set(pn) & set(po))
    eq = neq = err = 0
    examples = []
    for f in common:
        try:
            cn, co = canon(pn[f]), canon(po[f])
        except Exception as e:
            err += 1
            if len(examples) < 5:
                examples.append((f, "ERR " + repr(e)[:60]))
            continue
        if cn == co:
            eq += 1
        else:
            neq += 1
            if len(examples) < 12:
                examples.append((f, "DIFF"))
    print(f"BINDAT semantic compare over {len(common)} type-0 files:")
    print(f"  semantically identical : {eq}")
    print(f"  DIFFERENT              : {neq}")
    print(f"  decode error           : {err}")
    for f, tag in examples:
        print("   ", tag, f)

    # Deep-dump the first DIFF so we see WHAT differs.
    for f in common:
        try:
            cn, co = canon(pn[f]), canon(po[f])
        except Exception:
            continue
        if cn != co:
            print("\n=== FIRST DIFF:", f, "===")
            diff_tree(cn, co, [])
            break


def diff_tree(a, b, path):
    pa = ".".join(path) or "(root)"
    if a[0] != b[0]:
        print(f"  {pa}: name_hash {a[0]} vs {b[0]}")
    na, nb = {(p[0], p[1]): p[2] for p in a[1]}, {(p[0], p[1]): p[2] for p in b[1]}
    for k in set(na) | set(nb):
        if na.get(k) != nb.get(k):
            print(f"  {pa} prop keyhash={k[0]} type={k[1]}: native={na.get(k)} ours={nb.get(k)}")
    if len(a[2]) != len(b[2]):
        print(f"  {pa}: child count {len(a[2])} vs {len(b[2])}")
    for i in range(min(len(a[2]), len(b[2]))):
        diff_tree(a[2][i], b[2][i], path + [f"child[{i}]"])


if __name__ == "__main__":
    main()
