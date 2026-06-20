#!/usr/bin/env python3
"""Prove the .MOD header+manifest WRITER is byte-exact: disassemble a GUTS .MOD
into fields, re-emit header + manifest from those fields, copy the data section
raw, and compare byte-for-byte to the original. Validates all offset/manifest/
header write logic (compression already proven separately)."""
import os, sys, struct

# ---- stream writer primitives (mirror RGStream) ----
def w_w(v): return struct.pack('<H', v & 0xFFFF)
def w_d(v): return struct.pack('<I', v & 0xFFFFFFFF)
def w_b(v): return struct.pack('<B', v & 0xFF)
def w_q(v): return struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF)
def w_ss(s): return w_w(len(s)) + s.encode('utf-16-le')


class R:
    def __init__(s, b, p=0): s.b = b; s.p = p
    def w(s): v = struct.unpack_from('<H', s.b, s.p)[0]; s.p += 2; return v
    def d(s): v = struct.unpack_from('<I', s.b, s.p)[0]; s.p += 4; return v
    def b8(s): v = s.b[s.p]; s.p += 1; return v
    def q(s): v = struct.unpack_from('<Q', s.b, s.p)[0]; s.p += 8; return v
    def ss(s): n = s.w(); v = s.b[s.p:s.p+n*2].decode('utf-16-le'); s.p += n*2; return v


def disasm(tdata):
    r = R(tdata)
    h = dict(ver=r.w(), modver=r.w(), gamever=r.q(), offData=r.d(), offMan=r.d(),
             title=r.ss(), author=r.ss(), descr=r.ss(), website=r.ss(), download=r.ss(),
             modid=r.q(), flags=r.d(), reqHash=r.q())
    nreq = r.w(); h['reqs'] = [(r.ss(), r.q(), r.w()) for _ in range(nreq)]
    ndel = r.w(); h['dels'] = [r.ss() for _ in range(ndel)]
    h['header_len'] = r.p
    m = R(tdata, h['offMan'])
    mver = m.w(); mhash = m.d() if mver >= 2 else 0; root = m.ss()
    fc = m.d(); dc = m.d()
    dirs = []
    for _ in range(dc):
        dname = m.ss(); cnt = m.d()
        recs = [(m.d(), m.b8(), m.ss(), m.d(), m.d(), m.q()) for _ in range(cnt)]
        dirs.append((dname, recs))
    man = dict(ver=mver, hash=mhash, root=root, fc=fc, dc=dc, dirs=dirs, man_end=m.p)
    return h, man


def write_header(h):
    out = w_w(h['ver']) + w_w(h['modver']) + w_q(h['gamever']) + w_d(h['offData']) + w_d(h['offMan'])
    out += w_ss(h['title']) + w_ss(h['author']) + w_ss(h['descr']) + w_ss(h['website']) + w_ss(h['download'])
    out += w_q(h['modid']) + w_d(h['flags']) + w_q(h['reqHash'])
    out += w_w(len(h['reqs']))
    for (n, i, v) in h['reqs']:
        out += w_ss(n) + w_q(i) + w_w(v)
    out += w_w(len(h['dels']))
    for d in h['dels']:
        out += w_ss(d)
    return out


def write_manifest(m):
    out = w_w(m['ver']) + (w_d(m['hash']) if m['ver'] >= 2 else b'') + w_ss(m['root'])
    out += w_d(m['fc']) + w_d(m['dc'])
    for (dname, recs) in m['dirs']:
        out += w_ss(dname) + w_d(len(recs))
        for (crc, typ, name, off, size, ft) in recs:
            out += w_d(crc) + w_b(typ) + w_ss(name) + w_d(off) + w_d(size) + w_q(ft)
    return out


def main():
    tdata = open(sys.argv[1], 'rb').read()
    h, m = disasm(tdata)
    new_header = write_header(h)
    new_man = write_manifest(m)
    data_section = tdata[h['offData']:h['offMan']]
    rebuilt = new_header + data_section + new_man
    print(f'header: re-emit {len(new_header)} vs offData {h["offData"]}  match={new_header==tdata[:h["offData"]]}')
    print(f'manifest: re-emit {len(new_man)} vs orig {len(tdata)-h["offMan"]}  match={new_man==tdata[h["offMan"]:]}')
    print(f'FULL .MOD byte-exact rebuild: {rebuilt == tdata}  ({len(rebuilt)} vs {len(tdata)})')
    if rebuilt != tdata:
        n = min(len(rebuilt), len(tdata))
        first = next((i for i in range(n) if rebuilt[i] != tdata[i]), n)
        print('  first diff @', first)


if __name__ == '__main__':
    main()
