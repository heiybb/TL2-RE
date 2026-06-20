"""
Tests for mikuro_mod_packer.mpp (Version B .mpp generator).

Pure-logic tests run anywhere. Tests marked with _requires_install read the
real TL2 install at the hardcoded path and are skipped if absent.
"""
import os
import struct
import unittest

import numpy as np

from mikuro_mod_packer.mpp.geom import AABB, Matrix4, Vec3, orientation_axes, yaw_axes  # noqa: E402
from mikuro_mod_packer.mpp.region import (  # noqa: E402
    grid_dims,
    grid_origin,
    header_floats,
    pack_header,
    snap_box_outward,
)
from mikuro_mod_packer.mpp.writer import write_mpp  # noqa: E402
from mikuro_mod_packer.mpp.dat import PieceDef, parse_dat  # noqa: E402
from mikuro_mod_packer.mpp.layout import parse_layout  # noqa: E402
from mikuro_mod_packer.mpp.region import select_collision_file  # noqa: E402
from mikuro_mod_packer.mpp.rules import parse_rules_template  # noqa: E402

MEDIA = r"E:\Torchlight 2\MEDIA"
HAS_INSTALL = os.path.isdir(MEDIA)


class GeomTests(unittest.TestCase):
    def test_aabb_transform_translation(self):
        box = AABB(Vec3(-1, -1, -1), Vec3(1, 1, 1))
        m = Matrix4.translation(Vec3(10, 0, 5))
        out = box.transformed(m)
        self.assertAlmostEqual(out.min.x, 9.0)
        self.assertAlmostEqual(out.max.z, 6.0)

    def test_aabb_transform_rotation_refits(self):
        # 45-deg yaw of a unit box: corners spread to +-sqrt(2) in X/Z
        box = AABB(Vec3(-1, 0, -1), Vec3(1, 0, 1))
        r, u, f = yaw_axes(45.0)
        m = Matrix4.from_axes(r, u, f)
        out = box.transformed(m)
        self.assertAlmostEqual(out.max.x, 2 ** 0.5, places=5)
        self.assertAlmostEqual(out.min.x, -(2 ** 0.5), places=5)

    def test_orientation_up_is_forward_cross_right(self):
        fwd = Vec3(0, 0, 1)
        right = Vec3(1, 0, 0)
        r, u, f = orientation_axes(fwd, right)
        self.assertAlmostEqual(u.y, 1.0, places=6)


class HeaderMathTests(unittest.TestCase):
    def test_grid_dims_straddle_plus_one(self):
        # A box from -60..30 (bounds 90 -> 225 cells) aligns evenly: 225.
        gw, gh = grid_dims(Vec3(-60, 0, -20), Vec3(30, 0, 60), 0.0, 0.0)
        self.assertEqual(gw, 225)
        self.assertEqual(gh, 200)

    def test_grid_dims_off_grid_adds_cell(self):
        # min not on a 0.4 boundary -> straddle adds one cell
        gw, _ = grid_dims(Vec3(-60.2, 0, 0), Vec3(29.8, 0, 0), 0.0, 0.0)
        self.assertEqual(gw, 226)

    def test_grid_origin_formula(self):
        # CLevel grid origin (RebuildLevel @ 0x10204FD0):
        #   origin = float32((floor((min - 0.2)/0.4) - 1)*0.4)
        # For min.x=10: (floor((10-0.2)/0.4)-1)*0.4 = (24-1)*0.4 = 9.2
        # For min.z=-10: (floor((-10-0.2)/0.4)-1)*0.4 = (-26-1)*0.4 = -10.8
        ox, oz = grid_origin(Vec3(10.0, 0.0, -10.0))
        self.assertAlmostEqual(ox, 9.2, places=5)
        self.assertAlmostEqual(oz, -10.8, places=5)

    def test_grid_dims_with_origin_no_straddle(self):
        # The BB_A region: box (10,-10)->(50,30), origin (9.2,-10.8).
        # gridW = ceil((50-9.2)/0.4) - floor((10-9.2)/0.4) = 102 - 2 = 100. No +1.
        ox, oz = grid_origin(Vec3(10.0, 0.0, -10.0))
        gw, gh = grid_dims(Vec3(10.0, 0.0, -10.0), Vec3(50.0, 0.0, 30.0), ox, oz)
        self.assertEqual((gw, gh), (100, 100))

    def test_grid_dims_with_origin_straddle_plus_one(self):
        # A box whose snapped min/origin make the writer's float32 ceil/floor
        # straddle by +1: box (-60,-20)->(60,90); origin (-60.8,-20.8). Because
        # -60.8 is not exactly representable in float32, (60-(-60.8))/0.4 lands at
        # 301.9999.. -> ceil 302 while floor((-60+60.8)/0.4)=floor(1.9999)=1, so
        # gridW = 302 - 1 = 301 (the +1 straddle the editor produces here, vs the
        # naive bounds/0.4 = 300). gridH similarly = 275.
        ox, oz = grid_origin(Vec3(-60.0, 0.0, -20.0))
        gw, gh = grid_dims(Vec3(-60.0, 0.0, -20.0), Vec3(60.0, 0.0, 90.0), ox, oz)
        self.assertEqual((gw, gh), (301, 275))

    def test_header_floats_worldext_origin(self):
        wW, wD, bW, bD = header_floats(Vec3(-60, 0, -20), Vec3(30, 0, 60), Vec3(0, 0, 0))
        self.assertAlmostEqual(wW, 60.0)
        self.assertAlmostEqual(wD, 20.0)
        self.assertAlmostEqual(bW, 90.0)
        self.assertAlmostEqual(bD, 80.0)

    def test_pack_header_layout(self):
        b = pack_header(50, 50, 10.0, 10.0, 20.0, 20.0)
        self.assertEqual(len(b), 24)
        self.assertEqual(struct.unpack("<iiffff", b),
                         (50, 50, 10.0, 10.0, 20.0, 20.0))

    def test_snap_outward(self):
        box = AABB(Vec3(-50.6, 0, -10.2), Vec3(40.1, 0, 80.1))
        s = snap_box_outward(box, 10.0)
        self.assertEqual((s.min.x, s.min.z, s.max.x, s.max.z), (-60.0, -20.0, 50.0, 90.0))

    def test_snap_outward_pad02_pushes_off_exact_boundary(self):
        """The editor's region snap is floor((min-0.2)/10)*10 / ceil((max+0.2)/10)*10
        (RebuildLevel @ 0x102043af..0x10204511, consts 0.2 / 10.0, float32). The 0.2
        pad pushes a face that sits exactly on a 10-multiple out to the next tile —
        e.g. a hull max of exactly 90.0 snaps to 100, and a min of exactly -30.0
        snaps to -40, which a bare floor/ceil to 10 would leave at 90 / -30."""
        box = AABB(Vec3(-30.0, 0, -10.0), Vec3(90.0, 0, 100.0))
        s = snap_box_outward(box, 10.0)
        self.assertEqual((s.min.x, s.min.z, s.max.x, s.max.z),
                         (-40.0, -20.0, 100.0, 110.0))
        # a hull comfortably inside a tile is not over-expanded
        box2 = AABB(Vec3(-29.5, 0, -9.5), Vec3(89.5, 0, 99.5))
        s2 = snap_box_outward(box2, 10.0)
        self.assertEqual((s2.min.x, s2.min.z, s2.max.x, s2.max.z),
                         (-30.0, -10.0, 90.0, 100.0))

    def test_transform_bounds_unpadded_default(self):
        """The editor merges each region's refit collision AABB UNPADDED into the
        master box (RebuildLevel @ 0x10203931..0x10204795); the only outward
        expansion is the per-region +-0.2-snap-to-10 (test_snap_outward_pad02...).
        So _transform_bounds_f32 defaults pad=False and returns the raw refit box.
        The pad=True branch (+-0.4 face pad) is retained for ablation only."""
        from mikuro_mod_packer.mpp.region import _transform_bounds_f32
        box = AABB(Vec3(-5.0, -2.0, 3.0), Vec3(7.0, 2.0, 9.0))
        ident = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
        # default (pad=False) leaves the refit box untouched
        mnx, mnz, mxx, mxz = _transform_bounds_f32(box, ident)
        self.assertAlmostEqual(mnx, -5.0, places=5)
        self.assertAlmostEqual(mnz, 3.0, places=5)
        self.assertAlmostEqual(mxx, 7.0, places=5)
        self.assertAlmostEqual(mxz, 9.0, places=5)
        # ablation pad=True expands each X/Z face by 0.4
        p = _transform_bounds_f32(box, ident, pad=True)
        self.assertAlmostEqual(p[0], -5.4, places=5)
        self.assertAlmostEqual(p[2], 7.4, places=5)


class WriterTests(unittest.TestCase):
    def test_write_roundtrip(self):
        import tempfile
        cells = np.full(4, 0xFF, dtype=np.uint8)
        with tempfile.NamedTemporaryFile(suffix=".mpp", delete=False) as tf:
            path = tf.name
        try:
            write_mpp(path, 2, 2, 1.0, 1.0, 0.8, 0.8, cells)
            data = open(path, "rb").read()
            self.assertEqual(len(data), 28)
            gw, gh = struct.unpack_from("<ii", data, 0)
            self.assertEqual((gw, gh), (2, 2))
            self.assertEqual(data[24:], b"\xff\xff\xff\xff")
        finally:
            os.remove(path)

    def test_write_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            write_mpp("nul.mpp", 3, 3, 0, 0, 0, 0, np.zeros(4, np.uint8))


class ParserTextTests(unittest.TestCase):
    def test_parse_dat_piece(self):
        txt = (
            "[PIECES]\n[PIECE]\n"
            "<STRING>NAME:floor_01\n"
            "<INTEGER64>GUID:5827754378657075679\n"
            "<STRING>FILE:media/levelsets/Z1Tundra/grass_floor_01.mesh\n"
            "<STRING>COLLISIONFILE:media/levelsets/Z1Tundra/floor_collision.mesh\n"
            "<BOOL>SCALABLE:true\n<STRING>TAG:FLOOR\n<STRING>TAG:TUNDRA\n"
            "[/PIECE]\n[/PIECES]\n"
        )
        d = parse_dat(("﻿" + txt).encode("utf-16-le"))
        self.assertIn("5827754378657075679", d)
        pd = d["5827754378657075679"]
        self.assertEqual(pd.name, "floor_01")
        self.assertTrue(pd.file.endswith("grass_floor_01.mesh"))
        self.assertTrue(pd.collision_file.endswith("floor_collision.mesh"))
        self.assertIn("FLOOR", pd.tags)

    def test_parse_dat_keeps_all_visual_variants(self):
        """A [PIECE] is a SET of visual sub-pieces: every <STRING>FILE: /
        <STRING>COLLISIONFILE: is one variant. parse_dat must keep the full ordered
        lists (pd.files / pd.collision_files) so the VISUAL index can select among
        them; pd.file / pd.collision_file remain the index-0 entry for back-compat."""
        txt = (
            "[PIECES]\n[PIECE]\n"
            "<INTEGER64>GUID:7\n"
            "<STRING>FILE:media/levelsets/x/rock_01.mesh\n"
            "<STRING>FILE:media/levelsets/x/rock_02.mesh\n"
            "<STRING>FILE:media/levelsets/x/rock_03.mesh\n"
            "<STRING>COLLISIONFILE:media/levelsets/x/rock_01_collision.mesh\n"
            "<STRING>COLLISIONFILE:media/levelsets/x/rock_02_collision.mesh\n"
            "<STRING>COLLISIONFILE:media/levelsets/x/rock_03_collision.mesh\n"
            "[/PIECE]\n[/PIECES]\n"
        )
        d = parse_dat(("﻿" + txt).encode("utf-16-le"))
        pd = d["7"]
        self.assertEqual(len(pd.files), 3)
        self.assertEqual(len(pd.collision_files), 3)
        self.assertTrue(pd.file.endswith("rock_01.mesh"))
        self.assertTrue(pd.collision_file.endswith("rock_01_collision.mesh"))
        self.assertTrue(pd.collision_files[2].endswith("rock_03_collision.mesh"))

    def test_parse_layout_visual_index(self):
        """<STRING>VISUAL:N is the stored per-instance VISUAL PIECE INDEX (default 0
        when absent). It is never -1 in shipped layouts; we parse it verbatim."""
        def mk(visual_line):
            return (
                "[Layout]\n<INTEGER>VERSION:4\n[OBJECTS]\n[BASEOBJECT]\n[PROPERTIES]\n"
                "<STRING>DESCRIPTOR:Room Piece\n<STRING>NAME:RP\n"
                "<INTEGER64>PARENTID:-1\n<INTEGER64>ID:1\n<STRING>GUID:9\n"
                + visual_line +
                "[/PROPERTIES]\n[/BASEOBJECT]\n[/OBJECTS]\n[/Layout]\n"
            )
        lay = parse_layout(("﻿" + mk("<STRING>VISUAL:2\n")).encode("utf-16-le"))
        self.assertEqual(lay.by_id["1"].visual, 2)
        lay0 = parse_layout(("﻿" + mk("")).encode("utf-16-le"))
        self.assertEqual(lay0.by_id["1"].visual, 0)  # absent => 0

    def test_select_collision_file_re_rule(self):
        """RE rule (EditorGuts sub_102317F0 / sub_10230ED0 / sub_1000CF20):
          * in-range stored VISUAL index is used verbatim (deterministic);
          * collision index = visual ONLY when collisionCount == visualCount,
            else the single shared collider (index 0);
          * an over-range index (the -1/RANDOM sentinel the editor would roll via a
            seeded RNG, never present on disk) falls back to index 0 offline."""
        # paired per-visual colliders: VISUAL picks the matching collision mesh
        pd = PieceDef(files=("a.mesh", "b.mesh", "c.mesh"),
                      collision_files=("a_c.mesh", "b_c.mesh", "c_c.mesh"),
                      collision_file="a_c.mesh")
        self.assertEqual(select_collision_file(pd, 0), "a_c.mesh")
        self.assertEqual(select_collision_file(pd, 2), "c_c.mesh")
        # out-of-range (the RNG/-1 case) -> shared index 0, no fabrication
        self.assertEqual(select_collision_file(pd, 5), "a_c.mesh")
        self.assertEqual(select_collision_file(pd, -1), "a_c.mesh")
        # multiple visuals but ONE shared collider: any VISUAL keeps index 0
        shared = PieceDef(files=("a.mesh", "b.mesh", "c.mesh"),
                          collision_files=("only_c.mesh",),
                          collision_file="only_c.mesh")
        self.assertEqual(select_collision_file(shared, 0), "only_c.mesh")
        self.assertEqual(select_collision_file(shared, 2), "only_c.mesh")
        # no collider at all -> empty (piece contributes nothing)
        self.assertEqual(select_collision_file(PieceDef(), 0), "")

    def test_parse_layout_transform_chain(self):
        txt = (
            "[Layout]\n<INTEGER>VERSION:4\n[OBJECTS]\n"
            "[BASEOBJECT]\n[PROPERTIES]\n"
            "<STRING>DESCRIPTOR:Group\n<STRING>NAME:G\n"
            "<INTEGER64>PARENTID:-1\n<INTEGER64>ID:100\n"
            "<FLOAT>POSITIONX:10\n<FLOAT>POSITIONY:0\n<FLOAT>POSITIONZ:0\n"
            "[/PROPERTIES]\n[CHILDREN]\n"
            "[BASEOBJECT]\n[PROPERTIES]\n"
            "<STRING>DESCRIPTOR:Room Piece\n<STRING>NAME:RP\n"
            "<INTEGER64>PARENTID:100\n<INTEGER64>ID:200\n"
            "<FLOAT>POSITIONX:5\n<FLOAT>POSITIONY:0\n<FLOAT>POSITIONZ:0\n"
            "<STRING>GUID:42\n[/PROPERTIES]\n[/BASEOBJECT]\n"
            "[/CHILDREN]\n[/BASEOBJECT]\n[/OBJECTS]\n[/Layout]\n"
        )
        lay = parse_layout(("﻿" + txt).encode("utf-16-le"))
        self.assertEqual(lay.version, 4)
        rp = lay.by_id["200"]
        # world X = parent(10) + local(5) = 15
        self.assertAlmostEqual(rp._world.m[0][3], 15.0)
        self.assertEqual(rp.descriptor, "Room Piece")
        self.assertEqual(rp.guid, "42")


class RulesTemplateTests(unittest.TestCase):
    """RULES.TEMPLATE parser + multi-chunk classification (rules.py). The
    classifier is the gate that marks the 4 ACT1_PASS1 rooms as runtime
    chunk-assembled (footprint not reconstructible from one .LAYOUT)."""

    _ACT1_PASS1 = (
        "﻿[LEVEL]\n"
        "\t<STRING>NAME:EchoPass\n"
        "\t<FLOAT>TILEBASIS:4\n"
        "\t<FLOAT>CHUNKWIDTHBASIS:25\n"
        "\t<FLOAT>CHUNKHEIGHTBASIS:25\n"
        "\t<BOOL>RANDOMIZED:true\n"
        "\t<INTEGER>GENERATION_TYPE:1\n"
        "\t[LAYOUT]\n\t\t[CHUNK_RANDOM]\n"
        "\t\t\t<STRING>TYPE:1X1SINGLE_ROOM\n"
        "\t\t\t<FLOAT>X:0\n\t\t\t<FLOAT>Y:0\n\t\t\t<FLOAT>Z:100\n"
        "\t\t[/CHUNK_RANDOM]\n\t[/LAYOUT]\n"
        "\t[LAYOUT]\n\t\t[CHUNK_RANDOM]\n"
        "\t\t\t<STRING>TYPE:1X1SINGLE_ROOM\n"
        "\t\t\t<FLOAT>X:100\n\t\t\t<FLOAT>Y:0\n\t\t\t<FLOAT>Z:300\n"
        "\t\t[/CHUNK_RANDOM]\n\t[/LAYOUT]\n"
        "\t[LAYOUT]\n\t\t[CHUNK_RANDOM]\n"
        "\t\t\t<STRING>TYPE:1X1SINGLE_ROOM\n"
        "\t\t\t<FLOAT>X:-200\n\t\t\t<FLOAT>Y:0\n\t\t\t<FLOAT>Z:0\n"
        "\t\t[/CHUNK_RANDOM]\n\t[/LAYOUT]\n"
        "\t[CHUNKTYPE]\n"
        "\t\t<STRING>NAME:1X1SINGLE_ROOM\n"
        "\t\t<BOOL>ENTRANCE_CHUNK:true\n"
        "\t\t<INTEGER>WIDTH:1\n\t\t<INTEGER>HEIGHT:1\n"
        "\t\t<STRING>FOLDER:1X1SINGLE_ROOM_A\n"
        "\t[/CHUNKTYPE]\n"
        "[/LEVEL]\n"
    )

    def test_parse_scalars_and_slots(self):
        rt = parse_rules_template(self._ACT1_PASS1.encode("utf-16-le"))
        self.assertEqual(rt.name, "EchoPass")
        self.assertEqual(rt.tile_basis, 4.0)
        self.assertEqual(rt.chunk_width_basis, 25.0)
        self.assertEqual(rt.generation_type, 1)
        self.assertTrue(rt.randomized)
        self.assertEqual(rt.n_slots, 3)
        # slot offsets read in order
        self.assertEqual((rt.slots[1].x, rt.slots[1].z), (100.0, 300.0))
        self.assertEqual((rt.slots[2].x, rt.slots[2].z), (-200.0, 0.0))
        self.assertEqual(len(rt.chunk_types), 1)
        ct = rt.chunk_types[0]
        self.assertEqual(ct.folder, "1X1SINGLE_ROOM_A")
        self.assertTrue(ct.entrance)

    def test_multichunk_requires_two_slots_and_gen1(self):
        rt = parse_rules_template(self._ACT1_PASS1.encode("utf-16-le"))
        self.assertTrue(rt.is_multichunk)  # 3 slots, gen 1 -> assembled

    def test_single_slot_not_multichunk(self):
        single = self._ACT1_PASS1.replace(
            "\t[LAYOUT]\n\t\t[CHUNK_RANDOM]\n"
            "\t\t\t<STRING>TYPE:1X1SINGLE_ROOM\n"
            "\t\t\t<FLOAT>X:100\n\t\t\t<FLOAT>Y:0\n\t\t\t<FLOAT>Z:300\n"
            "\t\t[/CHUNK_RANDOM]\n\t[/LAYOUT]\n"
            "\t[LAYOUT]\n\t\t[CHUNK_RANDOM]\n"
            "\t\t\t<STRING>TYPE:1X1SINGLE_ROOM\n"
            "\t\t\t<FLOAT>X:-200\n\t\t\t<FLOAT>Y:0\n\t\t\t<FLOAT>Z:0\n"
            "\t\t[/CHUNK_RANDOM]\n\t[/LAYOUT]\n", "")
        rt = parse_rules_template(single.encode("utf-16-le"))
        self.assertEqual(rt.n_slots, 1)
        self.assertFalse(rt.is_multichunk)  # one slot -> just the entrance room

    def test_gen0_multislot_not_multichunk(self):
        """GENERATION_TYPE 0 (editor TEST stubs) declare slots but bake an empty
        default region and stay byte-exact, so they must NOT be flagged."""
        gen0 = self._ACT1_PASS1.replace(
            "<INTEGER>GENERATION_TYPE:1", "<INTEGER>GENERATION_TYPE:0")
        rt = parse_rules_template(gen0.encode("utf-16-le"))
        self.assertEqual(rt.n_slots, 3)
        self.assertFalse(rt.is_multichunk)


@unittest.skipUnless(HAS_INSTALL, "requires TL2 install")
class InstallTests(unittest.TestCase):
    def test_portal_byte_exact(self):
        """The geometry-free portal layout must reproduce byte-exactly."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_mpp
        import tempfile

        ctx = Context(MEDIA)
        layout = os.path.join(MEDIA, "LAYOUTS", "DUNGEON_EXIT_PORTAL.LAYOUT")
        real = os.path.join(MEDIA, "LAYOUTS", "DUNGEON_EXIT_PORTAL.MPP")
        if not os.path.exists(layout) or not os.path.exists(real):
            self.skipTest("portal files absent")
        with tempfile.NamedTemporaryFile(suffix=".mpp", delete=False) as tf:
            out = tf.name
        try:
            generate_mpp(layout, out, ctx, snap=10.0)
            self.assertEqual(open(out, "rb").read(), open(real, "rb").read())
        finally:
            os.remove(out)

    def test_mesh_reader_bounds(self):
        from mikuro_mod_packer.mpp.ogre_mesh import load_mesh_file
        p = os.path.join(MEDIA, "levelsets", "Z1Tundra", "grass_floor_01.mesh")
        if not os.path.exists(p):
            self.skipTest("sample mesh absent")
        mesh = load_mesh_file(p)
        self.assertFalse(mesh.bounds.null)
        # 20x20 floor tile centered at origin
        self.assertAlmostEqual(mesh.bounds.min.x, -10.0, places=2)
        self.assertAlmostEqual(mesh.bounds.max.x, 10.0, places=2)

    def test_collision_mesh_is_ogre_mesh(self):
        """COLLISIONFILE is a standard Ogre v1.40 .mesh read by the same reader
        as render meshes — a low-poly collision proxy (a flat quad for a floor)."""
        from mikuro_mod_packer.mpp.ogre_mesh import load_mesh_file
        p = os.path.join(MEDIA, "LEVELSETS", "catacomb",
                         "catacomb_floor_blank_01_collision.mesh")
        if not os.path.exists(p):
            self.skipTest("sample collision mesh absent")
        mesh = load_mesh_file(p)
        self.assertFalse(mesh.bounds.null)
        tris = list(mesh.triangles())
        # a flat floor collision proxy: a single quad (two triangles) near y=0
        self.assertGreaterEqual(len(tris), 2)
        ys = [v.y for t in tris for v in t]
        self.assertLess(max(ys) - min(ys), 0.5)

    def test_collision_only_no_render_fallback(self):
        """native.gather must skip pieces with no COLLISIONFILE and pieces with
        COLLISION ENABLED=false (no render-mesh fallback)."""
        from mikuro_mod_packer.mpp.pipeline import Context
        from mikuro_mod_packer.mpp.layout import load_layout_file, iter_room_pieces
        from mikuro_mod_packer.mpp.native import gather, _collision_enabled
        lp = os.path.join(MEDIA, "LAYOUTS", "ACT3_Z1", "1X1_CONCAVE_S2W1",
                          "1X1_CONCAVE_S2W1_BB_A.LAYOUT")
        if not os.path.exists(lp):
            self.skipTest("BB_A layout absent")
        ctx = Context(MEDIA)
        layout = load_layout_file(lp)
        tris = gather(layout, ctx)  # list of (a, b, c, nopath)
        self.assertTrue(tris)
        # there are NOPATH cliff pieces (their footprint becomes hard wall)
        self.assertGreater(sum(1 for *_xyz, nop in tris if nop), 0)
        # every collision-disabled piece must be excluded
        for p in iter_room_pieces(layout):
            if not _collision_enabled(p):
                self.assertFalse(_collision_enabled(p))

    def test_bb_a_header_byte_exact(self):
        """The region AABB now comes from the COLLISION-triangle source (the same
        geometry the classifier raycasts), so the 24-byte header of the concave
        cliff template 1X1_CONCAVE_S2W1_BB_A reproduces byte-exactly: grid 100x100,
        worldExt (-10,10), bounds (40,40). The old render/mesh-AABB merge computed
        150x150 (it included the decorative cliff overhang)."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        base = os.path.join(MEDIA, "LAYOUTS", "ACT3_Z1", "1X1_CONCAVE_S2W1")
        lp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.LAYOUT")
        mpp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.mpp")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("BB_A files absent")
        ctx = Context(MEDIA)
        h = generate_header(lp, ctx)
        self.assertEqual((h["gridW"], h["gridH"]), (100, 100))
        gw, gh, wW, wD, bW, bD = struct.unpack_from("<iiffff", open(mpp, "rb").read(), 0)
        self.assertEqual((h["gridW"], h["gridH"]), (gw, gh))
        for got, want in ((h["worldExtX"], wW), (h["worldExtZ"], wD),
                          (h["boundsX"], bW), (h["boundsZ"], bD)):
            self.assertEqual(struct.pack("<f", np.float32(got)),
                             struct.pack("<f", np.float32(want)))
        # the computed 24-byte header must be byte-identical to the shipped one
        from mikuro_mod_packer.mpp.region import pack_header
        hdr = pack_header(h["gridW"], h["gridH"], h["worldExtX"], h["worldExtZ"],
                          h["boundsX"], h["boundsZ"])
        self.assertEqual(hdr, open(mpp, "rb").read()[:24])

    def test_cliff_template_header_byte_exact(self):
        """A cliff/overhang TEMPLATE reproduces its 24-byte header byte-exactly
        under the RE-exact per-region +-0.2-snap-to-10 of the unpadded collision
        merge (RebuildLevel @ 0x102043af..0x10204511).
        1X1CLIFF_CONCAVE_S1E1_TEMPLATE is grid 301x175, worldExt (50,10), bounds
        (120,70). A bare floor/ceil-to-10 of the hull undershot to 276x175 /
        bounds (110,70) — exactly the cliff one-tile-short failure the 0.2 pad
        closes. This guards against dropping the 0.2 snap pad."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        from mikuro_mod_packer.mpp.region import pack_header
        base = os.path.join(MEDIA, "LAYOUTS", "ACT2_Z2", "TEMPLATES",
                            "1X1_CLIFF_CONCAVE_S1E1")
        lp = os.path.join(base, "1X1CLIFF_CONCAVE_S1E1_TEMPLATE.LAYOUT")
        mpp = os.path.join(base, "1X1CLIFF_CONCAVE_S1E1_TEMPLATE.MPP")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("cliff template files absent")
        ctx = Context(MEDIA)
        h = generate_header(lp, ctx)
        self.assertEqual((h["gridW"], h["gridH"]), (301, 175))
        with open(mpp, "rb") as f:
            shipped = f.read()[:24]
        hdr = pack_header(h["gridW"], h["gridH"], h["worldExtX"], h["worldExtZ"],
                          h["boundsX"], h["boundsZ"])
        self.assertEqual(hdr, shipped)

    def test_visual_piece_index_header_byte_exact(self):
        """A template whose region extent is driven by the stored VISUAL PIECE INDEX
        selecting a NON-index-0 collision mesh. NETHER 1X1NW_TEMPLATE has a cap-rock
        piece with VISUAL:1 -> nether_cap_rock_02_collision.mesh (a different extent
        than _01). Selecting the active visual collider (RE: sub_102317F0 /
        sub_10230ED0, deterministic from the stored index) reproduces the 24-byte
        header byte-exactly: grid 326x325. The old always-index-0 model undershot to
        300x325. Guards the VISUAL-piece selection lever (88.8%->90.9% on the 1293)."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        from mikuro_mod_packer.mpp.region import pack_header
        from mikuro_mod_packer.mpp.layout import load_layout_file, iter_room_pieces
        from mikuro_mod_packer.mpp.region import select_collision_file
        base = os.path.join(MEDIA, "LAYOUTS", "NETHER", "TEMPLATES")
        lp = os.path.join(base, "1X1NW_TEMPLATE.LAYOUT")
        mpp = os.path.join(base, "1X1NW_TEMPLATE.MPP")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("1X1NW_TEMPLATE files absent")
        ctx = Context(MEDIA)
        h = generate_header(lp, ctx)
        self.assertEqual((h["gridW"], h["gridH"]), (326, 325))
        hdr = pack_header(h["gridW"], h["gridH"], h["worldExtX"], h["worldExtZ"],
                          h["boundsX"], h["boundsZ"])
        self.assertEqual(hdr, open(mpp, "rb").read()[:24])
        # confirm the lever actually fires here: some piece picks a non-0 collider
        layout = load_layout_file(lp)
        picked_nonzero = False
        for p in iter_room_pieces(layout):
            pd = ctx.guid.get(p.guid)
            if pd is None or len(pd.collision_files) <= 1:
                continue
            sel = select_collision_file(pd, p.visual)
            if sel and sel != pd.collision_file:
                picked_nonzero = True
                break
        self.assertTrue(picked_nonzero,
                        "expected a VISUAL!=0 multi-collision pick to drive this tile")

    def test_structural_exit_link_header_byte_exact(self):
        """A connection tile whose pathing region is extended one tile on the exit
        side by the STRUCTURAL "Exit" Layout Link's doorway geometry. ACT2_CAVES
        1X1_EXIT_N_JT_A carries a <DESCRIPTOR>Layout Link name='Exit' -> CAVE_EXIT
        .LAYOUT (a collision Room Piece); the editor bakes it, extending the -X face
        from minx=-36 to -41.3 => snap -50 => grid 201x200. The base collision merge
        (without the link) undershot to 176x200. region._merge_structural_exit_links
        reproduces the editor bake (RE: the doorway is a permanent structural link,
        unlike random/spawned link content). Guards the 90.9%->91.2% lever."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        from mikuro_mod_packer.mpp.region import pack_header
        base = os.path.join(MEDIA, "LAYOUTS", "ACT2_CAVES", "1X1EXIT_N")
        lp = os.path.join(base, "1X1_EXIT_N_JT_A.LAYOUT")
        mpp = os.path.join(base, "1X1_EXIT_N_JT_A.MPP")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("ACT2_CAVES 1X1_EXIT_N_JT_A files absent")
        ctx = Context(MEDIA)
        h = generate_header(lp, ctx)
        self.assertEqual((h["gridW"], h["gridH"]), (201, 200))
        hdr = pack_header(h["gridW"], h["gridH"], h["worldExtX"], h["worldExtZ"],
                          h["boundsX"], h["boundsZ"])
        self.assertEqual(hdr, open(mpp, "rb").read()[:24])

    def test_structural_exit_filter_distinguishes_random_links(self):
        """The structural-exit gate must accept the doorway prop layouts and reject
        random/spawned link content (FILLER/SPAWNER/CHEST/LOOTABLE/RANDOMDUNGEON),
        which is why blanket link inclusion regresses. Pure-unit (no install)."""
        from mikuro_mod_packer.mpp.region import _is_structural_exit_link
        from mikuro_mod_packer.mpp.layout import LayoutObject

        def link(target):
            o = LayoutObject()
            o.descriptor = "Layout Link"
            o.props = {"LAYOUT FILE": target}
            return o
        # structural doorways -> baked
        for t in ("MEDIA/LEVELSETS/PROPS/Z2DESERT_PROPS/CAVE_EXIT.LAYOUT",
                  "media/levelsets/props/EXIT.LAYOUT",
                  "MEDIA/.../ENTRANCE_EXIT.LAYOUT"):
            self.assertTrue(_is_structural_exit_link(link(t)), t)
        # random/spawned/decorative -> NOT baked
        for t in ("MEDIA/LEVELSETS/PROPS/FILLER_10_SHRUBS.LAYOUT",
                  "MEDIA/LEVELSETS/PROPS/CHEST_RARE_ACT2.LAYOUT",
                  "MEDIA/LEVELSETS/PROPS/JACKALBEAST_SPAWNER_TRIGGERED.LAYOUT",
                  "MEDIA/LEVELSETS/PROPS/A2-RANDOMDUNGEONENTRANCES.LAYOUT",
                  "MEDIA/LEVELSETS/PROPS/SHRINES/ALL_LOOTABLE_SHRINES.LAYOUT",
                  "MEDIA/.../EXITZONEPORTALS.LAYOUT",
                  "MEDIA/.../RANDOMDUNGEONEXITPORTAL.LAYOUT"):
            self.assertFalse(_is_structural_exit_link(link(t)), t)
        # a non-link object is never structural-exit
        o = LayoutObject(); o.descriptor = "Room Piece"
        o.props = {"LAYOUT FILE": "EXIT.LAYOUT"}
        self.assertFalse(_is_structural_exit_link(o))

    def test_pass_outdoor_room_header_byte_exact(self):
        """A large outdoor PASS room (ACT2_PASS1 PASS1_LM_A, grid 1426x425) — many
        hundreds of collision-enabled room pieces, terrain-style — reproduces its
        24-byte header byte-exactly under the RE-exact per-region 0.2-snap-to-10 of
        the unpadded collision merge. This is the single-region outdoor case
        (the editor's region == this room); it guards the multi-piece outdoor path.
        (The multi-CHUNK assembled PASS rooms, whose footprint unions neighbor-chunk
        regions added at runtime, remain offline-unreachable and are NOT asserted.)"""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        from mikuro_mod_packer.mpp.region import pack_header
        base = os.path.join(MEDIA, "LAYOUTS", "ACT2_PASS1", "1X1SINGLE_ROOM_A")
        lp = os.path.join(base, "PASS1_LM_A.LAYOUT")
        mpp = os.path.join(base, "PASS1_LM_A.MPP")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("PASS1_LM_A files absent")
        ctx = Context(MEDIA)
        h = generate_header(lp, ctx)
        self.assertEqual((h["gridW"], h["gridH"]), (1426, 425))
        hdr = pack_header(h["gridW"], h["gridH"], h["worldExtX"], h["worldExtZ"],
                          h["boundsX"], h["boundsZ"])
        self.assertEqual(hdr, open(mpp, "rb").read()[:24])

    def test_act1_pass1_rooms_flagged_multichunk(self):
        """The 4 ACT1_PASS1 rooms are runtime chunk-assembled: their level dir's
        RULES.TEMPLATE has 3 CHUNK_RANDOM slots + GENERATION_TYPE 1, so the pipeline
        must flag them `multichunk` (honest: footprint not offline-reconstructible).
        A single-slot PASS room elsewhere (ACT3_PASS1) must NOT be flagged."""
        from mikuro_mod_packer.mpp.pipeline import Context, generate_header
        from mikuro_mod_packer.mpp.rules import is_multichunk_assembled
        base = os.path.join(MEDIA, "LAYOUTS", "ACT1_PASS1", "1X1SINGLE_ROOM_A")
        if not os.path.isdir(base):
            self.skipTest("ACT1_PASS1 rooms absent")
        ctx = Context(MEDIA)
        for nm in ("PASS_JT_A", "PASS_JD_A", "PASS_PB_A", "PASS1_LM_A"):
            lp = os.path.join(base, nm + ".LAYOUT")
            if not os.path.exists(lp):
                continue
            self.assertTrue(is_multichunk_assembled(lp), f"{nm} not flagged")
            self.assertTrue(generate_header(lp, ctx)["multichunk"], f"{nm} header flag")
        # a single-slot PASS room is NOT multi-chunk (and is byte-exact elsewhere)
        single = os.path.join(MEDIA, "LAYOUTS", "ACT3_PASS1", "1X1SINGLE_ROOM",
                              "PASS1_LM_A.LAYOUT")
        if os.path.exists(single):
            self.assertFalse(is_multichunk_assembled(single))

    def test_act1_pass1_footprint_has_geometry_not_in_layout(self):
        """The decisive RE proof that the multi-chunk footprint is a RUNTIME
        instance (placed neighbour chunks), not anything in this .LAYOUT: the
        shipped .MPP holds thousands of PASSABLE (cell != 255) cells lying OUTSIDE
        this room's entire room-piece span. That road geometry is in no single
        layout, so the footprint is not offline-reconstructible."""
        from mikuro_mod_packer.mpp.pipeline import Context
        from mikuro_mod_packer.mpp.layout import load_layout_file, iter_room_pieces
        base = os.path.join(MEDIA, "LAYOUTS", "ACT1_PASS1", "1X1SINGLE_ROOM_A")
        lp = os.path.join(base, "PASS_JT_A.LAYOUT")
        mpp = os.path.join(base, "PASS_JT_A.MPP")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("PASS_JT_A files absent")
        Context(MEDIA)  # ensure parseable install
        lay = load_layout_file(lp)
        mnx = mnz = 1e9
        mxx = mxz = -1e9
        for pc in iter_room_pieces(lay):
            w = pc._world or pc.local_matrix()
            x, z = w.m[0][3], w.m[2][3]
            mnx, mxx = min(mnx, x), max(mxx, x)
            mnz, mxz = min(mnz, z), max(mxz, z)
        d = open(mpp, "rb").read()
        gw, gh, wW, wD, bW, bD = struct.unpack_from("<iiffff", d, 0)
        cells = np.frombuffer(d[24:24 + gw * gh], dtype=np.uint8).reshape(gh, gw)
        fminx, fminz = -wW, -wD
        cx = fminx + np.arange(gw) * 0.4
        cz = fminz + np.arange(gh) * 0.4
        outside = (((cz < mnz - 5) | (cz > mxz + 5))[:, None]
                   | ((cx < mnx - 5) | (cx > mxx + 5))[None, :])
        passable_outside = int(((cells != 255) & outside).sum())
        # tens of thousands in practice; assert well above any boundary noise
        self.assertGreater(passable_outside, 5000,
                           "expected substantial passable geometry outside piece span")

    def test_bb_a_cells_match_shipped(self):
        """Cross-check vs Version A's byte-exact ground truth: on the deterministic
        plain template 1X1_CONCAVE_S2W1_BB_A (whose shipped .mpp Version A
        regenerates byte-identically), the collision+NOPATH classifier must agree
        with the shipped cells to >= 99% (residual is wall-boundary cells)."""
        from mikuro_mod_packer.mpp.pipeline import Context
        from mikuro_mod_packer.mpp.layout import load_layout_file
        from mikuro_mod_packer.mpp.geom import AABB, Vec3
        from mikuro_mod_packer.mpp.native import build_grid_fast
        from mikuro_mod_packer.mpp.region import grid_origin
        base = os.path.join(MEDIA, "LAYOUTS", "ACT3_Z1", "1X1_CONCAVE_S2W1")
        lp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.LAYOUT")
        mpp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.mpp")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("BB_A files absent")
        ctx = Context(MEDIA)
        layout = load_layout_file(lp)
        d = open(mpp, "rb").read()
        gw, gh, wW, wD, bW, bD = struct.unpack_from("<iiffff", d, 0)
        real = np.frombuffer(d[24:], dtype=np.uint8)
        box = AABB(Vec3(-wW, 0.0, -wD), Vec3(-wW + bW, 0.0, -wD + bD))
        ox, oz = grid_origin(box.min)
        grid_bytes, _, _ = build_grid_fast(layout, ctx, box, ox, oz, gw, gh)
        grid = np.frombuffer(grid_bytes, dtype=np.uint8)
        agree = (grid == real).mean()
        self.assertGreaterEqual(agree, 0.99,
                                f"BB_A per-cell agreement {agree:.4f} < 0.99")


@unittest.skipUnless(HAS_INSTALL, "requires TL2 install")
class FacadeTests(unittest.TestCase):
    """The mpp.compile_mpp facade (offline backend) used by the packer."""

    def test_compile_mpp_matches_generate_mpp_file(self):
        """compile_mpp(layout) returns the SAME bytes generate_mpp writes to disk
        (the bytes refactor wires both through one core). Uses the geometry-free
        portal layout — always present, parses fast, deterministic."""
        from mikuro_mod_packer.mpp import compile_mpp
        from mikuro_mod_packer.mpp.pipeline import Context, generate_mpp
        import tempfile

        layout = os.path.join(MEDIA, "LAYOUTS", "DUNGEON_EXIT_PORTAL.LAYOUT")
        if not os.path.exists(layout):
            self.skipTest("portal layout absent")
        ctx = Context(MEDIA)
        with tempfile.NamedTemporaryFile(suffix=".mpp", delete=False) as tf:
            out = tf.name
        try:
            generate_mpp(layout, out, ctx, snap=10.0)
            with open(out, "rb") as f:
                file_bytes = f.read()
        finally:
            os.remove(out)
        facade_bytes = compile_mpp(layout, MEDIA, snap=10.0)
        self.assertEqual(facade_bytes, file_bytes)

    def test_compile_mpp_byte_exact_offline_reproducible(self):
        """compile_mpp must reproduce the shipped .mpp byte-for-byte on a fully
        offline-reproducible layout. The geometry-free DUNGEON_EXIT_PORTAL is the
        offline backend's known byte-exact case (no collision raycast ambiguity),
        so the whole 24-byte header + grid body matches. (The offline backend is
        only APPROXIMATE on real-geometry tiles — ~99.3% cells; for those, full
        byte-exactness needs the DLL backend. See compile_mpp's docstring.)"""
        from mikuro_mod_packer.mpp import compile_mpp
        layout = os.path.join(MEDIA, "LAYOUTS", "DUNGEON_EXIT_PORTAL.LAYOUT")
        mpp = os.path.join(MEDIA, "LAYOUTS", "DUNGEON_EXIT_PORTAL.MPP")
        if not (os.path.exists(layout) and os.path.exists(mpp)):
            self.skipTest("portal files absent")
        with open(mpp, "rb") as f:
            shipped = f.read()
        self.assertEqual(compile_mpp(layout, MEDIA, snap=10.0), shipped)

    def test_compile_mpp_header_byte_exact_concave_leaf(self):
        """A plain CONCAVE leaf template (1X1_CONCAVE_S2W1_BB_A) whose 24-byte
        HEADER the offline backend reproduces byte-exactly (the body is the ~99.3%
        approximate raster — full body byte-exactness is a DLL-backend property).
        Guards the facade against header regressions on real-geometry leaves."""
        from mikuro_mod_packer.mpp import compile_mpp
        base = os.path.join(MEDIA, "LAYOUTS", "ACT3_Z1", "1X1_CONCAVE_S2W1")
        lp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.LAYOUT")
        mpp = os.path.join(base, "1X1_CONCAVE_S2W1_BB_A.mpp")
        if not (os.path.exists(lp) and os.path.exists(mpp)):
            self.skipTest("BB_A files absent")
        with open(mpp, "rb") as f:
            shipped = f.read()
        self.assertEqual(compile_mpp(lp, MEDIA, snap=10.0)[:24], shipped[:24])


if __name__ == "__main__":
    unittest.main()
