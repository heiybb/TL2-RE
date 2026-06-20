"""
mikuro_mod_packer.mpp — Version B: a clean, from-scratch reimplementation of
TL2's .MPP pathing-grid generator, grounded ENTIRELY in the reverse-engineering
of EditorGuts.dll (CLevel_BuildWritePathingGrid_MPP @ 0x10200920 and
CLevel_RebuildLevel_GenPathing @ 0x10203710).

NO dependency on parse_layout.py. All parsers are independent and lossless
for the data the pathing pipeline needs.

Submodules:
  ogre_mesh  -- Ogre .mesh reader (M_MESH_BOUNDS + triangle geometry)
  layout     -- UTF-16-LE .LAYOUT reader (room-piece placements, transforms)
  dat        -- LEVELSETS .DAT reader ([PIECE] GUID->FILE/COLLISIONFILE)
  rules      -- RULES.TEMPLATE reader + multi-chunk procedural-assembly classifier
  geom       -- Vec3 / Transform / AABB helpers (Ogre-compatible math)
  region     -- region-AABB computation + grid dims + 4 header floats
  writer     -- .mpp byte writer (24-byte header + grid)
  native     -- faithful per-cell classifier (down-ray + clearance + enclosure);
                build_grid (reference) / build_grid_fast (bucket-culled production)
  dll        -- byte-exact backend: drives the real EditorGuts.dll (env-gated)

Two backends produce .mpp data:
  * `compile_mpp` (this module)   — the OFFLINE Version-B reimplementation here.
  * `dll.regen_mpp_via_dll`       — drives the REAL EditorGuts.dll (byte-exact).
"""
import os

# base install (NOT the mod): room-piece collision geometry is read from the
# base game's LEVELSETS, so the offline Context points at the install, mirroring
# how the packer's BINDAT string dict / parse_layout's .material parse the base.
_DEFAULT_MEDIA = os.environ.get("TL2_MEDIA_DIR", r"E:\Torchlight 2\MEDIA")


def compile_mpp(layout_path, media_dir=None, snap=10.0, ctx=None) -> bytes:
    """Compile a single .LAYOUT to its .mpp content (24-byte header + grid body)
    and return it as bytes, using the OFFLINE Version-B reimplementation.

    This is the APPROXIMATE offline backend (grid body = the faithful DLL-port
    classifier native.build_grid_fast). Accuracy floor (a known, accepted ceiling
    — do not try to "fix" it): ~99.56% of cells / 99.71% de-floated and ~91% of
    headers are byte-exact across the 1293 shipped .mpp files. PLAIN CONCAVE leaf
    templates ARE byte-exact; some files are intrinsically non-reproducible offline
    (runtime RNG / editor float-nondeterminism / multi-chunk procedural assembly /
    selectively-baked nocollide cave walls).

    For BYTE-EXACT .mpp output, use the DLL backend instead
    (`mikuro_mod_packer.mpp.dll.regen_mpp_via_dll`, which drives the real
    EditorGuts.dll). See the dev memory `mpp-pathing-file-format` /
    `mpp-headless-regen-via-editorguts` and tools/mpp_drive_dll/README.md.

    `media_dir` defaults to the BASE install (env TL2_MEDIA_DIR, else
    r"E:\\Torchlight 2\\MEDIA") — room-piece collision meshes live there, so the
    Context points at the install, never at the mod being packed.
    """
    from .pipeline import Context, generate_mpp_bytes

    # Reuse a prebuilt `ctx` to amortize the install-LEVELSETS load across many
    # layouts of the same mod (the Context is identical for every one of them).
    if ctx is None:
        ctx = Context(media_dir or _DEFAULT_MEDIA)
    return generate_mpp_bytes(layout_path, ctx, snap=snap)
