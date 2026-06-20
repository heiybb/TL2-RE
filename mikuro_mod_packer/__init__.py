"""mikuro_mod_packer — Torchlight 2 .MOD builder.

Compiles MEDIA sources to binary and packs them into a .MOD container, mirroring
EditorGuts' CreateMod. See packer.py for the pipeline and the dev-log report
(开发日志/2026-06-17_MOD打包管线_*) for the reverse-engineered formats.

Submodules:
    bindat     DAT    -> BINDAT    (real from-scratch compiler)
    binlayout  LAYOUT -> BINLAYOUT (real from-scratch compiler)
    raw        the 7 RAW index builders
    rghash     Runic-Games hash (used by bindat; == EditorGuts sub_100CA9A0)
    packer     .MOD container writer + orchestration (convert_all / pack_mod)
    mpp        .MPP pathing grids: compile_mpp (offline, approximate) + dll.py
               (byte-exact via the real EditorGuts.dll, env-gated)
    data/      baked resources (string dict, binlayout schema + tag map)

CLI: python -m mikuro_mod_packer <mod_directory>
"""
# Public API is exposed LAZILY: attribute access is forwarded to .packer on first
# use. This keeps `import mikuro_mod_packer as P; P.pack_mod(...)` working WITHOUT
# importing packer (and numpy / the mpp subpackage) at package-import time. It
# also means `python -m mikuro_mod_packer.<submodule>` does not pre-import that
# submodule via the package __init__, so there's no runpy "found in sys.modules"
# warning when running bindat / binlayout / raw / mpp directly.
import importlib

__all__ = [
    "pack_mod", "build_header", "build_manifest_dirs", "read_gamever",
    "convert_all", "generate_raw_files", "generate_mpp_files",
    "read_mod_metadata", "find_zlib_offsets", "main",
]

_SUBMODULES = frozenset({"packer", "bindat", "binlayout", "raw", "rghash", "mpp"})


def __getattr__(name):
    # import_module (not `from . import`) so this doesn't re-enter __getattr__.
    if name in _SUBMODULES:
        return importlib.import_module(f".{name}", __name__)
    packer = importlib.import_module(".packer", __name__)
    try:
        return getattr(packer, name)
    except AttributeError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}") from None
