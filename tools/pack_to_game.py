"""Pack every real mod under E:\\Torchlight 2\\mods FROM SCRATCH (compile + RAW +
offline numba MPP + container) and drop the .MOD into the game's mod folder for an
in-game test. Non-mutating to the source mods (in-memory overrides)."""
import os, sys, io, contextlib, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODS = r"E:\Torchlight 2\mods"
TARGET = r"C:\Users\root\OneDrive\Documents\My Games\Runic Games\Torchlight 2\mods"


def main():
    import mikuro_mod_packer.packer as P
    os.makedirs(TARGET, exist_ok=True)
    ok = err = 0
    for name in sorted(os.listdir(MODS)):
        if name.startswith("__"):           # skip scratch copies
            continue
        d = os.path.join(MODS, name)
        media = os.path.join(d, "MEDIA")
        if not os.path.isdir(media) or not os.path.exists(os.path.join(d, "MOD.DAT")):
            continue
        try:
            mname = P.read_mod_metadata(d)["name"]
            out = os.path.join(TARGET, mname + ".MOD")
            with contextlib.redirect_stdout(io.StringIO()):
                ov = {}
                P.convert_all(media, overrides=ov, mpp="re", raw="auto")
                sz = P.pack_mod(media, out, mname, original_mod_dir=d, overrides=ov)
            ok += 1
            print("OK   %-34s -> %s.MOD  (%.1f MB)" % (name[:34], mname, sz / 1e6), flush=True)
        except Exception as e:
            err += 1
            print("ERR  %-34s : %r" % (name[:34], repr(e)[:80]), flush=True)
    print("--- done: %d packed, %d errors -> %s ---" % (ok, err, TARGET), flush=True)


if __name__ == "__main__":
    main()
