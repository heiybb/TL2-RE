import os, sys, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mikuro_mod_packer as P

M = 0xffffffff


def rghash(s, up=False):
    h = len(s)
    for c in s:
        cc = ord(c.upper()) if up else ord(c)
        h = ((h >> 27) ^ ((h << 5) & M) ^ cc) & M
    return h


# sanity vs dictionary.txt
assert rghash('A', True) == 97 and rghash('AI', True) == 105 and rghash('0', True) == 16

mod = r'E:\Torchlight 2\mods\COMMANDMENTS'
media = os.path.join(mod, 'MEDIA')
tdata = open(os.path.join(mod, [f for f in os.listdir(mod) if f.lower().endswith('.mod')][0]), 'rb').read()
zoffs = P.find_zlib_offsets(tdata)
pos = zoffs[0] - 8
while pos + 8 <= len(tdata):
    dsz, csz = struct.unpack_from('<II', tdata, pos)
    if csz == 0:
        if dsz <= 0 or pos + 8 + dsz > len(tdata):
            break
        pos += 8 + dsz
    else:
        st = tdata[pos+8:pos+8+csz]
        if st[:1] != b'\x78':
            break
        try:
            d = zlib.decompress(st)
        except Exception:
            break
        if len(d) != dsz:
            break
        pos += 8 + csz
toc = tdata[pos:]

# collect MEDIA folder paths (relative, with trailing slash, MEDIA/ prefix)
folders = set()
for root, dirs, files in os.walk(media):
    rel = os.path.relpath(root, media).replace('\\', '/')
    p = 'MEDIA/' if rel == '.' else 'MEDIA/' + rel + '/'
    folders.add(p)

print('folder, rghash forms found in TOC:')
hit = 0
for p in sorted(folders):
    forms = {
        'as/up': rghash(p, True), 'as/no': rghash(p, False),
        'noslash/up': rghash(p.rstrip('/'), True),
        'backslash/up': rghash(p.replace('/', '\\'), True),
    }
    found = [k for k, v in forms.items() if struct.pack('<I', v) in toc]
    if found:
        hit += 1
    print(f'  {"FOUND("+",".join(found)+")" if found else "----":28} {p}')
print(f'{hit}/{len(folders)} folder paths whose RGHash appears in the TOC')
