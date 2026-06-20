#!/usr/bin/env python3
"""Offline builder: learn the global TAG-string -> tag-id map used by the
BINLAYOUT datagroup section (the @92 field of each CLayoutBinaryGroup node).

The id is assigned by the game's runtime tag registry (EditorGuts.dll
sub_10253630 -> sub_100CBAA0 lookup returning *(node+44)); it is a small,
stable, GLOBAL integer per tag string and is NOT computable from the string
alone. We recover the registry's string->id assignment by correlating, across
every shipped datagroup BINLAYOUT, each Group's source <STRING>TAG against the
@92 value the editor wrote. The map is verified to be unambiguous (one id per
tag) over the whole corpus.

Like layout_schema.json, this reads the shipped binaries ONLY here (offline) to
LEARN the table; the compiler then writes datagroups from the .LAYOUT text plus
this baked map, reading no per-file binary.
"""
import os, struct, re, json, sys

MEDIA = sys.argv[1] if len(sys.argv) > 1 else r"E:/Torchlight 2/MEDIA"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "mikuro_mod_packer", "data", "binlayout_datagroup_tags.json")

PROP_RE = re.compile(r'<([^>]+)>([^:]+):(.*)')


def read_text(p):
    raw = open(p, "rb").read()
    raw = raw[2:] if raw[:2] == b"\xff\xfe" else raw
    return raw.decode("utf-16-le", "replace")


def parse_groups(txt):
    """id -> props dict for every Group object."""
    lines = [l.rstrip("\r").lstrip("\t ") for l in txt.split("\n")]
    res = {}
    cur = None
    inprops = False
    for l in lines:
        if l == "[PROPERTIES]":
            cur = {}
            inprops = True
        elif l == "[/PROPERTIES]":
            if cur is not None and cur.get("DESCRIPTOR") == "Group":
                try:
                    res[int(cur.get("ID", "0"))] = cur
                except Exception:
                    pass
            cur = None
            inprops = False
        elif inprops:
            m = PROP_RE.match(l)
            if m:
                cur[m.group(2).strip()] = m.group(3)
    return res


def decode_tags(d):
    """(group id, @92 tag value) for every non-root datagroup node."""
    dg_off = struct.unpack_from("<I", d, 2)[0]
    out = []

    def node(p):
        s64 = struct.unpack_from("<q", d, p)[0]; p += 8
        p += 1 + 4 + 1 + 4          # @16 @20 @24 @28
        tag = struct.unpack_from("<I", d, p)[0]; p += 4   # @92
        p += 3                      # @25 @26 @27
        ac = struct.unpack_from("<I", d, p)[0]; p += 4 + 8 * ac
        dc = struct.unpack_from("<I", d, p)[0]; p += 4 + 8 * dc
        cn = struct.unpack_from("<H", d, p)[0]; p += 2
        out.append((s64, tag))
        for c in range(cn):
            p = node(p)
        return p

    node(dg_off)
    return out


def main():
    tagmap = {}
    n = 0
    for root, _, files in os.walk(MEDIA):
        for f in files:
            if not f.endswith(".LAYOUT.BINLAYOUT"):
                continue
            bp = os.path.join(root, f)
            lp = bp[:-len(".BINLAYOUT")]
            d = open(bp, "rb").read()
            if not (len(d) >= 6 and struct.unpack_from("<I", d, 2)[0] != 0):
                continue
            if not os.path.exists(lp):
                continue
            try:
                nodes = decode_tags(d)
                groups = parse_groups(read_text(lp))
            except Exception:
                continue
            n += 1
            for (nid, tag) in nodes:
                if nid == -1 or tag == 0xFFFFFFFF:
                    continue
                t = (groups.get(nid, {}).get("TAG") or "").strip().upper()
                if t:
                    tagmap.setdefault(t, set()).add(tag)

    final = {}
    ambiguous = 0
    for k, v in tagmap.items():
        if len(v) > 1:
            ambiguous += 1
        final[k] = sorted(v)[0]
    json.dump(final, open(OUT, "w"), indent=0, sort_keys=True)
    print("datagroup files:", n, "tags:", len(final), "ambiguous:", ambiguous)
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
