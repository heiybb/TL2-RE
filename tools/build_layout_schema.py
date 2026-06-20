#!/usr/bin/env python3
"""Offline schema builder: learn the per-descriptor BINLAYOUT property schema
(code, value encoder, canonical order) from the shipped LAYOUT/BINLAYOUT pairs
in the TL2 install, and emit it as a static JSON consumed by the compiler.

This reads the shipped binaries ONLY here (offline, to LEARN the schema). The
compiler itself (layout2binlayout.py) reads NO binary at compile time -- it
serializes purely from the .LAYOUT text + this baked schema.
"""
import os, struct, re, collections, json, sys

MEDIA = sys.argv[1] if len(sys.argv) > 1 else r"E:/Torchlight 2/MEDIA"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "mikuro_mod_packer", "data", "binlayout_schema.json")

PROP_RE = re.compile(r'<([^>]+)>([^:]+):(.*)')


def read_text(p):
    raw = open(p, 'rb').read()
    if raw[:2] == b'\xff\xfe':
        raw = raw[2:]
    return raw.decode('utf-16-le', 'replace')


def parse_objects(txt):
    lines = [l.rstrip('\r').lstrip('\t ') for l in txt.split('\n')]
    pos = [0]

    def baseobjs(end):
        objs = []
        while pos[0] < len(lines):
            l = lines[pos[0]]
            if l == end:
                return objs
            if l == '[BASEOBJECT]':
                pos[0] += 1
                obj = {'props': [], 'children': []}
                while pos[0] < len(lines):
                    l = lines[pos[0]]
                    if l == '[/BASEOBJECT]':
                        pos[0] += 1
                        break
                    if l == '[PROPERTIES]':
                        pos[0] += 1
                        while lines[pos[0]] != '[/PROPERTIES]':
                            m = PROP_RE.match(lines[pos[0]])
                            if m:
                                obj['props'].append((m.group(1).strip(), m.group(2).strip(), m.group(3)))
                            pos[0] += 1
                        pos[0] += 1
                    elif l == '[CHILDREN]':
                        pos[0] += 1
                        obj['children'] = baseobjs('[/CHILDREN]')
                        pos[0] += 1
                    else:
                        pos[0] += 1
                objs.append(obj)
            else:
                pos[0] += 1
        return objs

    while pos[0] < len(lines) and lines[pos[0]] != '[OBJECTS]':
        pos[0] += 1
    pos[0] += 1
    return baseobjs('[/OBJECTS]')


def decode_bin(d):
    cnt = struct.unpack_from('<H', d, 6)[0]
    res = []

    def rd(q):
        blk = struct.unpack_from('<I', d, q)[0]
        s = q + 4
        desc = d[s]; s += 1
        s += 8  # id
        nl = struct.unpack_from('<H', d, s)[0]; s += 2
        s += nl * 2
        pc = d[s]; s += 1
        props = []
        for _ in range(pc):
            pm = struct.unpack_from('<H', d, s)[0]; s += 2
            pdesc = d[s]
            val = d[s + 1:s + pm]; s += pm
            props.append((pdesc, val))
        adp = struct.unpack_from('<I', d, s)[0]; s += 4
        s += adp
        nch = struct.unpack_from('<H', d, s)[0]; s += 2
        ch = []
        for _ in range(nch):
            o, s = rd(s)
            ch.append(o)
        return {'desc': desc, 'props': props, 'children': ch}, q + blk

    q = 8
    for _ in range(cnt):
        o, q = rd(q)
        res.append(o)
    return res


def flat(objs):
    for o in objs:
        yield o
        yield from flat(o['children'])


def f32(x):
    return struct.pack('<f', float(x))


def enc_float(v):
    return f32(v[0])


def _parse_int(s):
    s = s.strip()
    if s.lower().startswith('0x'):
        return int(s, 16)
    return int(float(s)) if ('.' in s or 'e' in s.lower()) else int(s)


def enc_u32int(v):
    return struct.pack('<i', _parse_int(v[0]))


def enc_u32bool(v):
    s = v[0].strip().lower()
    return struct.pack('<I', 0 if s in ('false', '0', 'f', '') else 1)


def enc_short_string(s):
    return struct.pack('<H', len(s)) + s.encode('utf-16-le')


def enc_string(v):
    return enc_short_string(v[0])


def enc_g2(v):
    return f32(v[0]) + f32(v[1])


def enc_g3(v):
    return f32(v[0]) + f32(v[1]) + f32(v[2])


def enc_g4(v):
    return f32(v[0]) + f32(v[1]) + f32(v[2]) + f32(v[3])


def enc_curve(v):
    parts = v[0].split(',') if v[0] != '' else []
    out = struct.pack('<H', len(parts))
    for p in parts:
        out += f32(p)
    return out


ENCODERS = [('float', enc_float), ('u32int', enc_u32int), ('u32bool', enc_u32bool),
            ('string', enc_string), ('g2', enc_g2), ('g3', enc_g3), ('g4', enc_g4),
            ('curve', enc_curve)]
ENCMAP = dict(ENCODERS)

# Manually-curated property codes that the corpus-voting heuristic cannot learn
# because they occur in too few (or structurally-skipped) files. Each entry was
# read directly out of the shipped BINLAYOUT for the one layout that uses it.
#   (descriptor, prop) -> (code, encoder)
# 'START TYPE' (code 106, string) appears only in GHOST_BOAT.LAYOUT.
MANUAL_PROPS = {
    ('Timeline', 'START TYPE'): (106, 'string'),
    ('Timeline', 'DEFAULT INTERPOLATION TYPE'): (102, 'string'),
    ('Timeline', 'TYPE'): (104, 'string'),
    ('Timeline', 'PAUSE ON UNLOAD'): (108, 'u32bool'),
}


def grouped_seq(tprops):
    seq = []
    i = 0
    seen_name = False
    seen_choice = False
    seen_gamemode = False
    while i < len(tprops):
        t, k, v = tprops[i]
        # DESCRIPTOR/PARENTID/ID and the FIRST NAME are meta (object identity).
        # A SECOND <STRING>NAME is a genuine property (e.g. Timeline's NAME,
        # code 21) and must be kept. CHOICE / GAME MODE behave the same: the 1st
        # feeds the datagroup, the 2nd is a real Group property (code 101 / 118).
        if k in ('DESCRIPTOR', 'PARENTID', 'ID') or (k == 'NAME' and not seen_name) \
                or (k == 'CHOICE' and not seen_choice) \
                or (k == 'GAME MODE' and not seen_gamemode):
            if k == 'NAME':
                seen_name = True
            if k == 'CHOICE':
                seen_choice = True
            if k == 'GAME MODE':
                seen_gamemode = True
            i += 1
            continue
        base = k[:-1]
        if k.endswith('X') and base and not base.endswith(' ') and i + 1 < len(tprops) and tprops[i + 1][1] == base + 'Y':
            if i + 2 < len(tprops) and tprops[i + 2][1] == base + 'Z':
                if i + 3 < len(tprops) and tprops[i + 3][1] == base + 'W':
                    seq.append((base, t, [v, tprops[i + 1][2], tprops[i + 2][2], tprops[i + 3][2]]))
                    i += 4
                else:
                    seq.append((base, t, [v, tprops[i + 1][2], tprops[i + 2][2]]))
                    i += 3
            else:
                # X/Y-only group (e.g. PADDINGX/PADDINGY -> one 8-byte "PADDING").
                seq.append((base, t, [v, tprops[i + 1][2]]))
                i += 2
        else:
            seq.append((k, t, [v]))
            i += 1
    return seq


def main():
    pairs = []
    for root, _, files in os.walk(MEDIA):
        for f in files:
            if f.endswith('.LAYOUT.BINLAYOUT'):
                bp = os.path.join(root, f)
                lp = bp[:-len('.BINLAYOUT')]
                if os.path.exists(lp):
                    pairs.append((lp, bp))
    print('pairs', len(pairs))

    code_vote = collections.defaultdict(collections.Counter)
    enc_vote = collections.defaultdict(collections.Counter)
    desc_code = collections.defaultdict(collections.Counter)
    after = collections.defaultdict(collections.Counter)
    present = collections.defaultdict(set)

    struct_ok = 0
    for lp, bp in pairs:
        try:
            d = open(bp, 'rb').read()
            bobjs = decode_bin(d)
            tobjs = parse_objects(read_text(lp))
            bl = list(flat(bobjs))
            tl = list(flat(tobjs))
            if len(bl) != len(tl):
                continue
            struct_ok += 1
            for to, bo in zip(tl, bl):
                tprops = to['props']
                desc = None
                for (t, k, v) in tprops:
                    if k == 'DESCRIPTOR':
                        desc = v
                if desc is None:
                    continue
                desc_code[desc][bo['desc']] += 1
                present.setdefault(desc, set())  # register descriptor even w/o props
                seq = grouped_seq(tprops)
                if len(seq) != len(bo['props']):
                    continue
                names = [s[0] for s in seq]
                for a in range(len(names)):
                    present[desc].add(names[a])
                    for b in range(a + 1, len(names)):
                        after[desc][(names[a], names[b])] += 1
                for (nm, ttag, vals), (pdesc, vb) in zip(seq, bo['props']):
                    code_vote[(desc, nm)][pdesc] += 1
                    for ename, efn in ENCODERS:
                        try:
                            if efn(vals) == vb:
                                enc_vote[(desc, nm)][ename] += 1
                        except Exception:
                            pass
        except Exception:
            pass

    schema = {'descriptors': {}}
    for desc in present:
        nodes = set(present[desc])
        net = collections.Counter({n: 0 for n in nodes})
        seen = set()
        for (a, b), c in after[desc].items():
            if (a, b) in seen or (b, a) in seen:
                continue
            seen.add((a, b))
            rev = after[desc].get((b, a), 0)
            if c >= rev:
                net[a] += 1; net[b] -= 1
            else:
                net[b] += 1; net[a] -= 1
        order = sorted(nodes, key=lambda n: (-net[n], n))
        props = {}
        for nm in nodes:
            cv = code_vote.get((desc, nm))
            if not cv:
                continue
            ev = enc_vote.get((desc, nm))
            props[nm] = {
                'code': cv.most_common(1)[0][0],
                'enc': ev.most_common(1)[0][0] if ev else 'string',
                'rank': order.index(nm),
            }
        # Overlay manually-curated props the voting heuristic missed.
        for (mdesc, mname), (mcode, menc) in MANUAL_PROPS.items():
            if mdesc == desc and mname not in props:
                props[mname] = {'code': mcode, 'enc': menc,
                                'rank': len(order) + 1}
        dc = desc_code.get(desc)
        schema['descriptors'][desc] = {
            'code': dc.most_common(1)[0][0] if dc else None,
            'props': props,
        }

    json.dump(schema, open(OUT, 'w'), separators=(',', ':'), sort_keys=True)
    ed = collections.Counter()
    noenc = 0
    for desc, info in schema['descriptors'].items():
        for nm, pi in info['props'].items():
            ed[pi['enc']] += 1
    for (desc, nm), ev in enc_vote.items():
        if not ev:
            noenc += 1
    print('struct_ok', struct_ok, 'descriptors', len(schema['descriptors']))
    print('encoder dist', dict(ed))
    print('props with zero-encoder-match (fell back to string):', noenc, 'of', len(code_vote))
    print('wrote', os.path.abspath(OUT))


if __name__ == '__main__':
    main()
