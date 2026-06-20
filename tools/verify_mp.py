#!/usr/bin/env python3
"""Verify convert_all's parallel LAYOUT path == serial, byte-for-byte, + time it."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer as P

HEAVY = r'E:\Program Files (x86)\Steam\steamapps\common\Torchlight II\mods\挑战者大陆--通用素材01'


def main():
    media = os.path.join(HEAVY, 'MEDIA')

    # Parallel (default threshold; heavy mod has 177 layouts → uses pool)
    t = time.time()
    ov_par = {}
    P.convert_all(media, overrides=ov_par)
    t_par = time.time() - t

    # Force serial
    old = P._MP_MIN_LAYOUT_JOBS
    P._MP_MIN_LAYOUT_JOBS = 10**9
    t = time.time()
    ov_ser = {}
    P.convert_all(media, overrides=ov_ser)
    t_ser = time.time() - t
    P._MP_MIN_LAYOUT_JOBS = old

    keys = set(ov_par) | set(ov_ser)
    mism = [k for k in keys if ov_par.get(k) != ov_ser.get(k)]
    print(f'\noverrides: parallel={len(ov_par)} serial={len(ov_ser)}  mismatches={len(mism)}')
    print(f'convert_all: parallel={t_par:.2f}s  serial={t_ser:.2f}s  speedup={t_ser/t_par:.2f}x')


if __name__ == '__main__':
    main()
