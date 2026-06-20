#!/usr/bin/env python3
"""GUTS / Runic Games string hash (RGHash), ported from TL2Lib (rgglobal.pas).

This is the hash GUTS uses for DAT/LAYOUT property keys and the .MOD container
TOC node/path entries. Reference (Pascal):

    function RGHash(instr:PWideChar; alen:integer=0):dword;
    begin
      if alen=0 then alen:=Length(instr);
      result:=alen;                              # init = number of UTF-16 code units
      for i:=0 to alen-1 do
        result:=(result SHR 27) xor (result SHL 5) xor ORD(instr[i]);
    end;
    # RGHashUp is identical but applies FastUpCase (uppercase) to each char.

Verified against TL2Lib/dictionary.txt: A=97, B=98, '0'=16, AI=105.

Real function in EditorGuts.dll — CONFIRMED byte-identical to this port:
    sub_100CA9A0  (entry 0x100CA9A0; the `shr ecx, 1Bh` @ 0x100ca9ce is the
    distinctive shift-by-27 giveaway). Decompiled:

        unsigned int RGHash(std::wstring *s) {
            unsigned int h = s->length();             // init = UTF-16 code units
            for (i = 0; i < s->length(); ++i)
                h = s[i] ^ (32 * h) ^ (h >> 27);      // 32*h == (h << 5)
            return h;
        }

    Matches this implementation line-for-line. Spot-checked against shipped
    BINDAT key hashes (UNITTHEMES/MAGICICE.DAT): THEME=0x0F651DE5,
    NAME=0x00660DE5, GUID=0x0062DD64 — all exact. A sibling RGHashUp variant
    applies FastUpCase per char; since DAT/LAYOUT keys are already uppercase,
    RGHash == RGHashUp for them.
"""

import functools

_M = 0xFFFFFFFF


@functools.lru_cache(maxsize=None)
def rg_hash(s, upper=False):
    """RGHash (upper=True -> RGHashUp). `s` is a Python str; chars are treated as
    UTF-16 code units (ord of each char, BMP).

    Memoized: callers (bindat key/name hashing) feed a small, heavily-repeated set
    of property keys / section names, so the hit rate is ~1 and inputs are bounded
    (a few hundred distinct), so maxsize=None never grows large."""
    h = len(s)
    for c in s:
        cc = ord(c.upper()) if upper else ord(c)
        h = ((h >> 27) ^ ((h << 5) & _M) ^ cc) & _M
    return h


def rg_hash_up(s):
    return rg_hash(s, upper=True)


# Self-test against known dictionary.txt entries.
assert rg_hash('A', True) == 97
assert rg_hash('B', True) == 98
assert rg_hash('0', True) == 16
assert rg_hash('AI', True) == 105


if __name__ == '__main__':
    import sys
    for arg in sys.argv[1:]:
        print(f'{arg!r}: RGHash={rg_hash(arg):#010x}  RGHashUp={rg_hash_up(arg):#010x}')
