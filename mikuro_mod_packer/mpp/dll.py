"""
dll.py — BYTE-EXACT .mpp backend: drive the REAL EditorGuts.dll.

Thin wrapper around the PROVEN headless-regen recipe (tools/mpp_drive_dll —
README.md + regen_mpp.sh): build the mod through TL2's own console host
`TL2-Mikuro-Console.exe`, which runs

    EditorSetWorkingMod(modDir)
    CreateMod(modDir + "\\MOD.DAT", true)   # pass 1: writes .BINLAYOUT (+ stub .mpp)
    EditorSetWorkingMod(modDir)
    CreateMod(modDir + "\\MOD.DAT", true)   # pass 2 (--twice): writes the real .mpp

i.e. the console's `build <modName> --clean --twice` invocation. Because the
real DLL assembles the collision world and raycasts each cell, the output is
byte-identical to the shipped game .mpp BY CONSTRUCTION (for plain leaf
templates; cliff/overhang tiles carry a handful of intrinsically nondeterministic
wall-boundary cells — see the README ROOT CAUSE section).

This module does NOT reimplement the editor — it only shells out to the existing
console host. It is ENV-GATED: if the install / console exe is missing it raises
RuntimeError describing exactly what is needed and where.

Constraints baked into the recipe:
  * cwd MUST be the install dir (so the 32-bit DLL finds OgreMain.dll, the PAKs,
    Plugins.cfg, MEDIA, and a D3D9 device).
  * CreateMod only accepts projects under the game's `mods/` folder, so the mod
    must live (or be staged) under <install>/mods/<name>.
  * A working GPU / D3D9 device is required (the build runs the real renderer).
"""
from __future__ import annotations

import os
import shutil
import subprocess

# install dir resolution: explicit arg -> env TL2_INSTALL_DIR -> parent of
# TL2_MEDIA_DIR -> the hardcoded default. The console exe lives at <install>/.
_DEFAULT_INSTALL = r"E:\Torchlight 2"
_CONSOLE_EXE = "TL2-Mikuro-Console.exe"


def _resolve_install(install_dir):
    if install_dir:
        return install_dir
    env_install = os.environ.get("TL2_INSTALL_DIR")
    if env_install:
        return env_install
    env_media = os.environ.get("TL2_MEDIA_DIR")
    if env_media:
        # MEDIA sits directly under the install dir.
        return os.path.dirname(env_media.rstrip("\\/"))
    return _DEFAULT_INSTALL


def _read_mod_name(mod_dir):
    """Best-effort MOD_FILE_NAME / NAME from MOD.DAT, else the dir basename."""
    mod_dat = os.path.join(mod_dir, "MOD.DAT")
    name = os.path.basename(os.path.normpath(mod_dir))
    if not os.path.isfile(mod_dat):
        return name
    try:
        import re
        text = open(mod_dat, "r", encoding="utf-16-le").read()
        for key in ("MOD_FILE_NAME", "NAME"):
            m = re.search(rf"<STRING>{key}:([^\r\n]+)", text)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return name


def regen_mpp_via_dll(mod_dir, *, install_dir=None):
    """Drive the real EditorGuts.dll to produce byte-exact .mpp files for the mod
    at `mod_dir` (a directory containing MOD.DAT + a MEDIA/ tree).

    Returns a dict summarizing the run on success (mod name, mod path used, exe,
    return code, count of .mpp files produced under the mod), or the console's
    integer exit code if it is non-zero.

    Raises RuntimeError (env gate) when the TL2 install or its console host
    `TL2-Mikuro-Console.exe` cannot be found — with a message stating what is
    needed and where to put it. Does NOT write into the base MEDIA install: the
    build runs inside the mod under <install>/mods/ (staged there if needed) and
    is reversible by deleting that scratch mod.
    """
    install = _resolve_install(install_dir)
    exe = os.path.join(install, _CONSOLE_EXE)
    if not os.path.isdir(install):
        raise RuntimeError(
            f"TL2 install dir not found: {install!r}. The byte-exact DLL backend "
            f"needs the real Torchlight 2 install (set TL2_INSTALL_DIR or pass "
            f"install_dir=...).")
    if not os.path.isfile(exe):
        raise RuntimeError(
            f"console host not found: {exe!r}. The byte-exact DLL backend drives "
            f"the real EditorGuts.dll via {_CONSOLE_EXE!r}, which must sit in the "
            f"install dir {install!r} (see tools/mpp_drive_dll/README.md).")
    if not os.path.isdir(mod_dir):
        raise RuntimeError(f"mod dir not found: {mod_dir!r}")

    mods_root = os.path.join(install, "mods")
    name = _read_mod_name(mod_dir)

    # CreateMod only accepts projects under <install>/mods/. If mod_dir already
    # lives there, build it in place; otherwise stage a copy under mods/<name>
    # (non-destructive to the source mod_dir) and remove it after.
    staged = None
    real_mod = os.path.normpath(mod_dir)
    expected = os.path.normpath(os.path.join(mods_root, name))
    if real_mod.lower() != expected.lower():
        os.makedirs(mods_root, exist_ok=True)
        staged = expected
        if os.path.exists(staged):
            shutil.rmtree(staged)
        shutil.copytree(mod_dir, staged)
        build_dir = staged
    else:
        build_dir = real_mod

    try:
        # cwd MUST be the install dir; --clean --twice = cold double pass
        # (pass 1 writes .BINLAYOUT + stub .mpp, pass 2 writes the real .mpp).
        proc = subprocess.run(
            [exe, "build", name, "--clean", "--twice"],
            cwd=install,
            env={**os.environ, "MSYS_NO_PATHCONV": "1"},
            capture_output=True, text=True,
        )
        # Success is measured by OUTPUT, not the return code: the console host
        # routinely exits with a teardown crash code (e.g. 0xC0000374 heap-
        # corruption on shutdown) AFTER correctly writing every .mpp. The shell
        # driver ignores rc and checks for output — mirror that here, else the
        # harmless teardown crash would discard a perfectly good build.
        n_mpp = 0
        for root, _dirs, files in os.walk(build_dir):
            n_mpp += sum(1 for f in files if f.upper().endswith(".MPP"))
        if n_mpp == 0:
            return proc.returncode or -1   # genuinely produced no .mpp -> failed

        result = {
            "mod": name,
            "mod_dir": build_dir,
            "exe": exe,
            "returncode": proc.returncode,
            "mpp_count": n_mpp,
            "staged": staged is not None,
        }
        # If we staged a copy, hand back the generated .mpp files to the caller's
        # source mod_dir before cleanup (so the bytes are not lost with the scratch).
        if staged is not None:
            copied = 0
            for root, _dirs, files in os.walk(staged):
                for f in files:
                    if not f.upper().endswith(".MPP"):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), staged)
                    dst = os.path.join(mod_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), dst)
                    copied += 1
            result["mpp_copied_back"] = copied
        return result
    finally:
        if staged is not None and os.path.isdir(staged):
            shutil.rmtree(staged, ignore_errors=True)


def regen_mpp_via_dll_batch(mod_dirs, *, install_dir=None):
    """Byte-exact .mpp for MANY mods in ONE editor session — InitEditor (~5s) is paid
    ONCE for the whole batch instead of once per mod (vs regen_mpp_via_dll, which
    re-inits the editor every call). Drives the forked TL2-Mikuro-Console `bench`
    command (warm per-mod CreateMod + EditorRegenPathingData).

    Each mod dir (containing MOD.DAT + MEDIA/) is staged as a scratch copy under
    <install>/mods/ (the source is never modified), built warm, and the resulting
    .mpp copied back into the source mod's MEDIA. Returns {mod_dir: mpp_count}.
    Raises RuntimeError (env gate) if the install or console host is missing.
    """
    install = _resolve_install(install_dir)
    exe = os.path.join(install, _CONSOLE_EXE)
    if not os.path.isdir(install):
        raise RuntimeError(f"TL2 install dir not found: {install!r}")
    if not os.path.isfile(exe):
        raise RuntimeError(f"console host not found: {exe!r} (see tools/tl2_console_fork)")
    mods_root = os.path.join(install, "mods")
    os.makedirs(mods_root, exist_ok=True)

    staged = {}   # scratch_name -> source mod_dir
    for d in (os.path.normpath(x) for x in mod_dirs):
        if not os.path.isdir(d):
            continue
        scratch = "__batch_%08x" % (abs(hash(d)) & 0xFFFFFFFF)
        dst = os.path.join(mods_root, scratch)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(d, dst)
        staged[scratch] = d

    results = {}
    try:
        proc = subprocess.run(
            [exe, "bench"] + list(staged.keys()) + ["--clean"],
            cwd=install, env={**os.environ, "MSYS_NO_PATHCONV": "1"},
            capture_output=True, text=True,
        )
        # rc is ignored: the console exits with a harmless teardown crash AFTER writing
        # every file (same as regen_mpp_via_dll). Success is measured by harvested .mpp.
        for scratch, src in staged.items():
            sdir = os.path.join(mods_root, scratch)
            n = 0
            for root, _d, files in os.walk(sdir):
                for f in files:
                    if not f.upper().endswith(".MPP"):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), sdir)
                    dstf = os.path.join(src, rel)
                    os.makedirs(os.path.dirname(dstf), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), dstf)
                    n += 1
            results[src] = n
        return results
    finally:
        for scratch in staged:
            shutil.rmtree(os.path.join(mods_root, scratch), ignore_errors=True)
