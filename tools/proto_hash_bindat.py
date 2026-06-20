"""Prototype + offline-verify the per-file HASH string-id scheme for BINDAT.

Idea (user's): since the game resolves a BINDAT's string ids via THAT file's own
table, drop the global intern counter and assign id = hash(string) per file (with
intra-file collision probing for uniqueness). That removes all shared state -> the
compiler becomes embarrassingly parallel AND deterministic.

This verifies OFFLINE that the hash scheme yields per-file-valid, semantically
IDENTICAL BINDAT (disassemble each via its own table; compare the resolved tree to
the corpus-dict build). It does NOT prove the game resolves per-file (model A) vs a
global merged table (model B) — that needs an in-game test. But equality here is a
necessary condition and confirms the scheme is internally sound.
"""
import os, sys, struct, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer.bindat as B

EMPTY = 0xFFFFFFFF


class HashStringDict:
    """Per-file string->id via hash with linear-probe for intra-file uniqueness.
    Deterministic: ids depend only on the file's string SET (sorted), not order."""
    EMPTY_ID = EMPTY

    def __init__(self, strings):
        self.s2id = {}
        used = set()
        for s in sorted(strings):                 # fixed order -> deterministic probe
            i = B.rg_hash(s) & 0xFFFFFFFF
            if i == EMPTY:
                i = 0
            while i in used:
                i = (i + 1) & 0xFFFFFFFF
                if i == EMPTY:
                    i = 0
            used.add(i)
            self.s2id[s] = i

    def get(self, s):
        return EMPTY if s == '' else self.s2id[s]


def compile_hashed(text):
    roots = B.parse_dat_text(text)
    if not roots:
        return None
    ss = {}
    for r in roots:
        B._collect_strings(r, ss)
    return B.compile_tree(roots, HashStringDict(ss.keys()))


# --- disassembler: resolve body vids via the file's OWN table -> canonical tree ---
STRING_TYPES = set(B.STRING_TYPES)


def _read_table(data):
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


def _read_node(data, off, id2s):
    nh, nprop = struct.unpack_from('<II', data, off); off += 8
    props = []
    for _ in range(nprop):
        kh, tc = struct.unpack_from('<II', data, off); off += 8
        if tc == 7:
            v = struct.unpack_from('<Q', data, off)[0]; off += 8
            props.append((kh, tc, ('i64', v)))
        else:
            raw = struct.unpack_from('<I', data, off)[0]; off += 4
            if tc in STRING_TYPES:
                props.append((kh, tc, ('s', '' if raw == EMPTY else id2s.get(raw, f'<MISS:{raw}>'))))
            else:
                props.append((kh, tc, ('n', raw)))
    nchild = struct.unpack_from('<I', data, off)[0]; off += 4
    kids = []
    for _ in range(nchild):
        c, off = _read_node(data, off, id2s)
        kids.append(c)
    return (nh, tuple(props), tuple(kids)), off


def canon(data):
    id2s, off = _read_table(data)
    tree, _ = _read_node(data, off, id2s)
    return tree


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else r"E:\Torchlight 2\mods\MIKURO_CLASS_QLJX_EN\MEDIA"
    sdict = B.get_string_dict(os.environ.get('TL2_MEDIA_DIR', r"E:\Torchlight 2\MEDIA"))
    dats = [p for p in glob.glob(os.path.join(src, '**', '*.DAT'), recursive=True)
            if not p.upper().endswith('.BINDAT')]
    eq = neq = err = 0
    max_probe_files = 0
    for p in dats:
        try:
            with open(p, 'rb') as fh:
                text = B._decode_dat_bytes(fh.read())
            b_corpus = B.compile_dat(text, sdict)
            b_hash = compile_hashed(text)
            if b_hash is None:
                continue
            # collision check: did probing move any id? (table scount == distinct strings)
            if canon(b_corpus) == canon(b_hash):
                eq += 1
            else:
                neq += 1
                if neq <= 5:
                    print("  DIFF:", os.path.relpath(p, src))
        except Exception as e:
            err += 1
            if err <= 5:
                print("  ERR ", os.path.relpath(p, src), repr(e)[:70])
    print(f"\nHASH BINDAT over {len(dats)} DATs of {os.path.basename(src.rstrip(os.sep))}:")
    print(f"  semantically identical to corpus-dict build : {eq}")
    print(f"  DIFFERENT                                    : {neq}")
    print(f"  error                                        : {err}")


if __name__ == "__main__":
    main()
