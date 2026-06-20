"""Native-DLL (GUTS editor) WARM packing benchmark, to compare against our
from-scratch packer (tools/bench_all_mods.py).

Drives the forked TL2-Mikuro-Console.exe `bench` command: InitEditor is paid ONCE,
then each mod's CreateMod (compile+RAW+pack) and EditorRegenPathingData (byte-exact
MPP) are timed separately, init amortized. Mods are staged as scratch copies under
<install>/mods/ so the source mods are never modified (cleaned up after). The first
real mod still pays cold data-load, so a throwaway warm-up mod is prepended and
discarded.

Usage:  python tools/bench_native.py <mod_name> [<mod_name> ...]
        python tools/bench_native.py --default      # a representative spread
"""
import os, sys, shutil, subprocess, time

INSTALL = r"E:\Torchlight 2"
MODS = os.path.join(INSTALL, "mods")
EXE = os.path.join(INSTALL, "TL2-Mikuro-Console.exe")
WARMUP = "COMMANDMENTS"   # tiny mod, built first and discarded (cold data-load)

DEFAULT = [
    "final_fantasy_weapons", "arkhamsarmory", "AdventurerTime", "MIKURO_FUN",
    "SYN_THROWING_WEAPONS", "挑战者大陆--实验性质", "挑战者大陆--武器自定义",
    "MIKURO_VANILLA_OVERHAUL", "挑战者大陆--佣兵系统", "挑战者大陆--POE",
]


def main():
    args = sys.argv[1:]
    names = DEFAULT if (not args or args == ["--default"]) else args
    names = [WARMUP] + [n for n in names if n != WARMUP]

    staged = {}   # scratch_name -> real_name
    for real in names:
        src = os.path.join(MODS, real)
        if not os.path.isdir(src):
            print(f"  skip (not found): {real}", flush=True); continue
        scratch = "__bn_%d" % (abs(hash(real)) % 10**8)
        dst = os.path.join(MODS, scratch)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        staged[scratch] = real

    try:
        t0 = time.time()
        p = subprocess.run([EXE, "bench"] + list(staged.keys()) + ["--clean"],
                           cwd=INSTALL, env={**os.environ, "MSYS_NO_PATHCONV": "1"},
                           capture_output=True, text=True, timeout=3600)
        wall = time.time() - t0

        init_ms = None
        results = {}   # scratch -> (build_ms, mpp_ms, ok)
        for ln in (p.stdout or "").splitlines():
            if ln.startswith("INIT_MS,"):
                init_ms = float(ln.split(",")[1])
            elif ln.startswith("BENCH,"):
                f = ln.split(",")
                results[f[1]] = (f[2], f[3], f[4] if len(f) > 4 else "")

        print("\n=== Native (GUTS) WARM packing — init amortized ===")
        print("InitEditor (one-time): %.2f s" % ((init_ms or 0) / 1000))
        print("%-30s %10s %10s  %s" % ("Mod", "Build(s)", "MPP(s)", "ok"))
        print("-" * 60)
        tb = tm = 0.0
        for scratch, real in staged.items():
            if real == WARMUP:
                continue   # discard the cold-load warm-up
            b, m, ok = results.get(scratch, ("?", "?", "MISSING"))
            try:
                bs, ms = float(b) / 1000, float(m) / 1000; tb += bs; tm += ms
                print("%-30s %10.2f %10.2f  %s" % (real[:30], bs, ms, ok))
            except ValueError:
                print("%-30s %10s %10s  %s" % (real[:30], b, m, ok))
        print("-" * 60)
        print("TOTAL warm build %.1fs + MPP %.1fs (init %.1fs once); wall %.1fs"
              % (tb, tm, (init_ms or 0) / 1000, wall))
    finally:
        for scratch in staged:
            shutil.rmtree(os.path.join(MODS, scratch), ignore_errors=True)


if __name__ == "__main__":
    main()
