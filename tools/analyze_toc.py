#!/usr/bin/env python3
"""Deep-dump a GUTS .MOD container: header, block chain, and the tail TOC tree.
Usage: python tools/analyze_toc.py <mod_dir>
"""
import os, sys, zlib, struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer as P


def walk(tdata):
    zoffs = P.find_zlib_offsets(tdata)
    pos = zoffs[0] - 8
    header_end = pos
    blocks = []
    while pos + 8 <= len(tdata):
        dsz, csz = struct.unpack_from('<II', tdata, pos)
        if csz == 0:
            if dsz <= 0 or pos + 8 + dsz > len(tdata):
                break
            data = tdata[pos + 8:pos + 8 + dsz]; adv = 8 + dsz
        else:
            if csz > len(tdata) - (pos + 8):
                break
            st = tdata[pos + 8:pos + 8 + csz]
            if st[:1] != b'\x78':
                break
            try:
                data = zlib.decompress(st)
            except Exception:
                break
            if len(data) != dsz:
                break
            adv = 8 + csz
        blocks.append((pos, dsz, csz, data)); pos += adv
    return header_end, blocks, pos


def hexd(b, label=''):
    print(f'{label} ({len(b)}B):')
    for i in range(0, min(len(b), 256), 16):
        chunk = b[i:i+16]
        h = ' '.join(f'{x:02x}' for x in chunk)
        a = ''.join(chr(x) if 32 <= x < 127 else '.' for x in chunk)
        print(f'  {i:4d}  {h:<48}  {a}')


def main():
    mod_dir = sys.argv[1]
    mods = [f for f in os.listdir(mod_dir) if f.lower().endswith('.mod')]
    tdata = open(os.path.join(mod_dir, mods[0]), 'rb').read()
    he, blocks, toc_off = walk(tdata)
    print(f'file {len(tdata)}B  header_end={he}  blocks={len(blocks)}  toc_off={toc_off}  toc_len={len(tdata)-toc_off}')
    hexd(tdata[:he], 'HEADER')
    print('\nBLOCKS (first decompressed bytes):')
    for i, (off, dsz, csz, data) in enumerate(blocks):
        crc = zlib.crc32(data) & 0xffffffff
        print(f'  [{i:2d}] off={off} dsz={dsz} csz={csz} crc={crc:08x} head={data[:12].hex()}')
    print()
    hexd(tdata[toc_off:], 'TOC')


if __name__ == '__main__':
    main()
