#!/usr/bin/env python3
"""Faithful .MOD disassembler (per rgmod/rgman). Prints header + manifest tree
so we know exactly what a from-scratch packer must reproduce."""
import os, sys, struct, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class R:
    def __init__(s, b, p=0): s.b = b; s.p = p
    def w(s): v = struct.unpack_from('<H', s.b, s.p)[0]; s.p += 2; return v
    def d(s): v = struct.unpack_from('<I', s.b, s.p)[0]; s.p += 4; return v
    def b8(s): v = s.b[s.p]; s.p += 1; return v
    def q(s): v = struct.unpack_from('<Q', s.b, s.p)[0]; s.p += 8; return v
    def ss(s): n = s.w(); v = s.b[s.p:s.p+n*2].decode('utf-16-le', 'replace'); s.p += n*2; return v


def main():
    tdata = open(sys.argv[1], 'rb').read()
    r = R(tdata)
    ver = r.w(); modver = r.w(); gamever = r.q()
    offData = r.d(); offMan = r.d()
    title = r.ss(); author = r.ss(); descr = r.ss(); web = r.ss(); dl = r.ss()
    modid = r.q(); flags = r.d()
    print(f'HEADER: ver={ver} modver={modver} gamever={gamever:#x} offData={offData} offMan={offMan}')
    print(f'  title={title!r} author={author!r} modid={modid} flags={flags:#x} header_parsed_to={r.p}')

    # manifest
    m = R(tdata, offMan)
    mver = m.w(); mhash = m.d() if mver >= 2 else 0; root = m.ss()
    fc = m.d(); dc = m.d()
    print(f'MANIFEST: ver={mver} hash={mhash:#x} root={root!r} FileCount={fc} DirCount={dc}')
    total_files = 0
    for di in range(dc):
        dname = m.ss(); cnt = m.d()
        files = []
        for fi in range(cnt):
            crc = m.d(); typ = m.b8(); name = m.ss(); off = m.d(); size = m.d(); ft = m.q()
            files.append((name, typ, off, size, crc, ft))
            total_files += 1
        if di < 4 or di == dc-1:
            print(f'  DIR[{di}] name={dname!r} count={cnt}')
            for (name, typ, off, size, crc, ft) in files[:4]:
                print(f'      type={typ:#04x} name={name!r} off={off} size={size} crc={crc:08x} ft={ft:#x}')
    print(f'manifest consumed to {m.p}/{len(tdata)} ; files listed={total_files}')


if __name__ == '__main__':
    main()
