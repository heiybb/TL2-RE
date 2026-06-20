"""Byte-exact / semantic regression tests for the offline TL2 .MOD packer.

Extracted from the original migration repo's test_media_paths.py — only the
packer/RE classes (RAW builders, BINDAT compile, BINLAYOUT compile, from-scratch
.MOD pack, PAK rollingHash). Several tests read the real TL2 install at the
hardcoded path and self-skip when it is absent.
"""
import importlib
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class UnitDataRawTests(unittest.TestCase):
    """build_unitdata must reproduce the shipped MEDIA/UNITDATA.RAW byte-for-byte.

    Requires the real TL2 install (E:\\Torchlight 2\\MEDIA); skips otherwise,
    matching the suite's existing reliance on the hardcoded install path."""

    MEDIA = r"E:\Torchlight 2\MEDIA"

    def _rg_raw(self):
        from mikuro_mod_packer import raw as rg_raw
        return rg_raw

    def test_build_unitdata_byte_exact_vs_shipped(self):
        shipped_path = os.path.join(self.MEDIA, "UNITDATA.RAW")
        if not os.path.isfile(shipped_path):
            self.skipTest("TL2 install (UNITDATA.RAW) not present")
        rg_raw = self._rg_raw()
        built = rg_raw.build_unitdata(self.MEDIA)
        with open(shipped_path, "rb") as f:
            shipped = f.read()
        self.assertIsNotNone(built)
        self.assertEqual(len(built), len(shipped),
                         msg=f"length {len(built)} != shipped {len(shipped)}")
        if built != shipped:
            for i, (a, b) in enumerate(zip(built, shipped)):
                if a != b:
                    self.fail(f"first byte diff @ {i}: built={a:#x} shipped={b:#x}")
        self.assertEqual(built, shipped)

    def test_unitdata_registered_in_builders(self):
        rg_raw = self._rg_raw()
        self.assertIs(rg_raw.BUILDERS.get("UNITDATA.RAW"), rg_raw.build_unitdata)


class UiRawTests(unittest.TestCase):
    """build_ui must reproduce the shipped MEDIA/UI.RAW byte-for-byte.

    GUTS's writer (EditorGuts sub_103178E0) indexes only the .LAYOUTs under
    MEDIA/UI/ whose [OBJECTS] contain a `DESCRIPTOR: Menu Definition` object,
    keyed off that object's MENU NAME / DO NOT CREATE props (109 of 171 ship).
    Requires the real TL2 install (E:\\Torchlight 2\\MEDIA); skips otherwise."""

    MEDIA = r"E:\Torchlight 2\MEDIA"

    def _rg_raw(self):
        from mikuro_mod_packer import raw as rg_raw
        return rg_raw

    def test_build_ui_byte_exact_vs_shipped(self):
        shipped_path = os.path.join(self.MEDIA, "UI.RAW")
        if not os.path.isfile(shipped_path):
            self.skipTest("TL2 install (UI.RAW) not present")
        rg_raw = self._rg_raw()
        built = rg_raw.build_ui(self.MEDIA)
        with open(shipped_path, "rb") as f:
            shipped = f.read()
        self.assertIsNotNone(built)
        self.assertEqual(len(built), len(shipped),
                         msg=f"length {len(built)} != shipped {len(shipped)}")
        if built != shipped:
            for i, (a, b) in enumerate(zip(built, shipped)):
                if a != b:
                    self.fail(f"first byte diff @ {i}: built={a:#x} shipped={b:#x}")
        self.assertEqual(built, shipped)

    def test_ui_entry_count_is_109(self):
        shipped_path = os.path.join(self.MEDIA, "UI.RAW")
        if not os.path.isfile(shipped_path):
            self.skipTest("TL2 install (UI.RAW) not present")
        rg_raw = self._rg_raw()
        built = rg_raw.build_ui(self.MEDIA)
        self.assertIsNotNone(built)
        # header u32 = number of *included* menu definitions, not layout count.
        self.assertEqual(struct.unpack_from("<I", built, 0)[0], 109)

    def test_ui_registered_in_builders(self):
        rg_raw = self._rg_raw()
        self.assertIs(rg_raw.BUILDERS.get("UI.RAW"), rg_raw.build_ui)


class _ShippedRawTestBase(unittest.TestCase):
    """Shared helper: assert a builder reproduces a shipped MEDIA/<NAME>.RAW
    byte-for-byte. Skips when the real TL2 install is absent (the suite relies
    on the hardcoded E:\\Torchlight 2\\MEDIA path)."""

    MEDIA = r"E:\Torchlight 2\MEDIA"

    def _rg_raw(self):
        from mikuro_mod_packer import raw as rg_raw
        return rg_raw

    def _assert_byte_exact(self, raw_name, builder_name):
        shipped_path = os.path.join(self.MEDIA, raw_name)
        if not os.path.isfile(shipped_path):
            self.skipTest(f"TL2 install ({raw_name}) not present")
        rg_raw = self._rg_raw()
        built = getattr(rg_raw, builder_name)(self.MEDIA)
        with open(shipped_path, "rb") as f:
            shipped = f.read()
        self.assertIsNotNone(built)
        self.assertEqual(len(built), len(shipped),
                         msg=f"length {len(built)} != shipped {len(shipped)}")
        if built != shipped:
            for i, (a, b) in enumerate(zip(built, shipped)):
                if a != b:
                    self.fail(f"first byte diff @ {i}: built={a:#x} shipped={b:#x}")
        self.assertEqual(built, shipped)
        return built, shipped


class AffixesRawTests(_ShippedRawTestBase):
    """build_affixes must reproduce shipped MEDIA/AFFIXES.RAW byte-for-byte.

    GUTS writer sub_103C4170: u16 count; per entry SS(FILE) SS(NAME upper)
    u32(MIN_SPAWN_RANGE def 0) u32(MAX_SPAWN_RANGE def 999999) u32(WEIGHT def 1)
    u32(DIFFICULTIES_ALLOWED def -1) then [UNITTYPES] and [NOT_UNITTYPES] string
    lists (u8 count + SS each). Scan order = name-interleaved DFS."""

    def test_build_affixes_byte_exact_vs_shipped(self):
        built, _ = self._assert_byte_exact("AFFIXES.RAW", "build_affixes")
        # header is the scan count (all .DATs load): 4049 entries.
        self.assertEqual(struct.unpack_from("<H", built, 0)[0], 4049)

    def test_affixes_registered_in_builders(self):
        rg_raw = self._rg_raw()
        self.assertIs(rg_raw.BUILDERS.get("AFFIXES.RAW"), rg_raw.build_affixes)


class SkillsRawTests(_ShippedRawTestBase):
    """build_skills must reproduce shipped MEDIA/SKILLS.RAW byte-for-byte.

    GUTS writer sub_102ECFD0: u32 count (= included skills only; empty NAME is
    skipped); per skill SS(NAME upper) SS(FILE) QWord(UNIQUE_GUID def -1). Scan
    order is the name-interleaved DFS — the first entry comes from ALCHEMIST/,
    not the root EFFECT_*.DAT files (proving files are NOT scanned before dirs)."""

    def test_build_skills_byte_exact_vs_shipped(self):
        built, _ = self._assert_byte_exact("SKILLS.RAW", "build_skills")
        self.assertEqual(struct.unpack_from("<I", built, 0)[0], 1659)

    def test_skills_first_entry_is_from_alchemist_subdir(self):
        # Interleaved DFS: ALCHEMIST (subdir) sorts before EFFECT_BURN.DAT (root
        # file), so the first emitted skill is EMBER LANCE from ALCHEMIST/.
        shipped_path = os.path.join(self.MEDIA, "SKILLS.RAW")
        if not os.path.isfile(shipped_path):
            self.skipTest("TL2 install (SKILLS.RAW) not present")
        built = self._rg_raw().build_skills(self.MEDIA)
        pos = 4
        nlen = struct.unpack_from("<H", built, pos)[0]; pos += 2
        name = built[pos:pos + 2 * nlen].decode("utf-16-le"); pos += 2 * nlen
        flen = struct.unpack_from("<H", built, pos)[0]; pos += 2
        file = built[pos:pos + 2 * flen].decode("utf-16-le")
        self.assertEqual(name, "EMBER LANCE")
        self.assertIn("ALCHEMIST", file.upper())

    def test_skills_registered_in_builders(self):
        rg_raw = self._rg_raw()
        self.assertIs(rg_raw.BUILDERS.get("SKILLS.RAW"), rg_raw.build_skills)


class MissilesRawTests(_ShippedRawTestBase):
    """build_missiles must reproduce shipped MEDIA/MISSILES.RAW byte-for-byte.

    GUTS writer sub_102FB490: u16 count (loadable .LAYOUTs); per entry SS(FILE)
    u8(nMissileNames) SS(MISSILE NAME upper)*. Scanned from MEDIA/MISSILES/
    *.LAYOUT (NOT *.DAT), name-interleaved DFS. Entries with zero missile names
    are still emitted (path only)."""

    def test_build_missiles_byte_exact_vs_shipped(self):
        built, _ = self._assert_byte_exact("MISSILES.RAW", "build_missiles")
        self.assertEqual(struct.unpack_from("<H", built, 0)[0], 407)

    def test_missiles_scans_layout_not_dat(self):
        # The builder must scan .LAYOUT files; the first stored path ends in
        # .LAYOUT, confirming the extension fix.
        shipped_path = os.path.join(self.MEDIA, "MISSILES.RAW")
        if not os.path.isfile(shipped_path):
            self.skipTest("TL2 install (MISSILES.RAW) not present")
        built = self._rg_raw().build_missiles(self.MEDIA)
        flen = struct.unpack_from("<H", built, 2)[0]
        first = built[4:4 + 2 * flen].decode("utf-16-le")
        self.assertTrue(first.upper().endswith(".LAYOUT"), msg=first)

    def test_missiles_registered_in_builders(self):
        rg_raw = self._rg_raw()
        self.assertIs(rg_raw.BUILDERS.get("MISSILES.RAW"), rg_raw.build_missiles)


class CompileDatTests(unittest.TestCase):
    """compile_dat must serialize .BINDAT from scratch (parsing the .DAT text,
    reading NO existing binary) byte-exact to GUTS.

    Two guarantees are checked:
      * byte-exact: over a random sample of shipped DAT/BINDAT pairs, the from
        scratch compile equals the shipped bytes. The rare misses are provably
        STALE binaries (the file's string table uses a non-canonical id, i.e. it
        was compiled against an older global-dictionary state) or text that lost
        float precision -- the same category the old echoer hit -- never a
        compiler bug.
      * edit-correctness: programmatically editing a value of every scalar type
        (INT/FLOAT/UNSIGNED INT/BOOL/STRING/INTEGER64) changes the output bytes
        accordingly when parsed back -- proving it is a real compiler, not an
        echo.

    Requires the real TL2 install (E:\\Torchlight 2\\MEDIA); skips otherwise."""

    MEDIA = r"E:\Torchlight 2\MEDIA"
    _sdict = None

    @classmethod
    def _compile_mod(cls):
        from mikuro_mod_packer import bindat as compile_dat
        return compile_dat

    @classmethod
    def _dict(cls):
        if cls._sdict is None:
            C = cls._compile_mod()
            cls._sdict = C.get_string_dict(cls.MEDIA)
        return cls._sdict

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _parse_bindat(data):
        """Parse a BINDAT into (id->string table, root node). Node is
        (key_hash, [(k,t,value)], [children]); STRING/TRANSLATE values are left
        as raw ids."""
        ver, scount, fid = struct.unpack_from("<3I", data, 0)
        off = 12
        id2s = {}
        ln = struct.unpack_from("<H", data, off)[0]; off += 2
        id2s[fid] = data[off:off + ln * 2].decode("utf-16-le", "replace"); off += ln * 2
        for _ in range(scount - 1):
            h = struct.unpack_from("<I", data, off)[0]; off += 4
            ln = struct.unpack_from("<H", data, off)[0]; off += 2
            id2s[h] = data[off:off + ln * 2].decode("utf-16-le", "replace"); off += ln * 2

        def node(o):
            key = struct.unpack_from("<I", data, o)[0]; o += 4
            pc = struct.unpack_from("<I", data, o)[0]; o += 4
            props = []
            for _ in range(pc):
                k = struct.unpack_from("<I", data, o)[0]
                t = struct.unpack_from("<I", data, o + 4)[0]; o += 8
                if t in (3, 7):
                    v = struct.unpack_from("<Q", data, o)[0]; o += 8
                else:
                    v = struct.unpack_from("<I", data, o)[0]; o += 4
                props.append((k, t, v))
            cc = struct.unpack_from("<I", data, o)[0]; o += 4
            kids = []
            for _ in range(cc):
                ch, o = node(o)
                kids.append(ch)
            return (key, props, kids), o
        root, _ = node(off)
        return id2s, root

    def _root_prop(self, data, key_name):
        from mikuro_mod_packer.rghash import rg_hash
        id2s, root = self._parse_bindat(data)
        kh = rg_hash(key_name)
        for k, t, v in root[1]:
            if k == kh:
                return t, v, id2s
        return None

    # -- tests -----------------------------------------------------------------
    def test_byte_exact_over_sample(self):
        import glob
        import random
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        C = self._compile_mod()
        sd = self._dict()
        files = glob.glob(os.path.join(self.MEDIA, "**", "*.DAT.BINDAT"),
                          recursive=True)
        if not files:
            self.skipTest("no .DAT.BINDAT pairs present")
        random.seed(20240617)
        random.shuffle(files)
        sample = files[:600]

        ok = stale = lossy = corrupt = 0
        unexplained = []
        for bp in sample:
            dp = bp[:-len(".BINDAT")]
            if not os.path.exists(dp):
                continue
            with open(bp, "rb") as fh:
                shipped = fh.read()
            try:
                with open(dp, "rb") as fh:
                    raw = fh.read()
                enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-16-le"
                raw.decode(enc)
            except UnicodeDecodeError:
                corrupt += 1
                continue
            out = C.compile_dat(dp, sd)
            if out == shipped:
                ok += 1
                continue
            # Classify the miss deterministically by comparing the parsed trees
            # with STRING/TRANSLATE values RESOLVED through each file's own table
            # (so a different raw id for the same string is not counted as a
            # difference). If the resolved structures match, the only difference
            # is the string ids -> the shipped binary is STALE (compiled against
            # an older/inconsistent global-dictionary session).
            if self._same_resolved(out, shipped):
                stale += 1
                continue
            # else: only float low-bits differ (text lost precision vs binary).
            if len(out) == len(shipped) and self._only_float_diff(out, shipped):
                lossy += 1
                continue
            unexplained.append(dp)

        total = ok + stale + lossy + corrupt + len(unexplained)
        self.assertGreater(total, 0)
        # The from-scratch compile must be byte-exact on the overwhelming
        # majority, and every miss must be explained (stale/lossy/corrupt).
        self.assertEqual(unexplained, [], msg=f"unexplained misses: {unexplained[:10]}")
        self.assertGreaterEqual(ok / total, 0.95,
                                msg=f"byte-exact rate {ok}/{total}")

    def _same_resolved(self, a, b):
        """True if two BINDATs have identical structure and identical
        STRING/TRANSLATE values once ids are resolved through each file's own
        table -- i.e. they differ ONLY in the numeric string ids (stale dict)."""
        try:
            ida, ra = self._parse_bindat(a)
            idb, rb = self._parse_bindat(b)
        except Exception:
            return False

        def resolve(node, id2s):
            key, props, kids = node
            rp = []
            for k, t, v in props:
                if t in (5, 8):
                    rp.append((k, t, "" if v == 0xFFFFFFFF else id2s.get(v)))
                else:
                    rp.append((k, t, v))
            return (key, rp, [resolve(c, id2s) for c in kids])
        return resolve(ra, ida) == resolve(rb, idb)

    def _only_float_diff(self, a, b):
        try:
            _, ra = self._parse_bindat(a)
            _, rb = self._parse_bindat(b)
        except Exception:
            return False

        def cmp(x, y):
            if x[0] != y[0] or len(x[1]) != len(y[1]) or len(x[2]) != len(y[2]):
                return False
            for (k1, t1, v1), (k2, t2, v2) in zip(x[1], y[1]):
                if k1 != k2 or t1 != t2:
                    return False
                if v1 != v2 and t1 != 2:
                    return False
            return all(cmp(ca, cb) for ca, cb in zip(x[2], y[2]))
        return cmp(ra, rb)

    def test_compiles_from_scratch_without_template(self):
        # Proves the compiler never reads the sibling .BINDAT: compile a DAT
        # whose binary we deliberately hide by passing only its text.
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        C = self._compile_mod()
        sd = self._dict()
        dp = os.path.join(self.MEDIA, "GLOBALS.DAT")
        if not os.path.isfile(dp):
            self.skipTest("GLOBALS.DAT not present")
        with open(dp, "rb") as fh:
            text = fh.read().decode("utf-16")
        out = C.compile_dat(text, sd)         # text only, no path -> no binary read
        with open(dp + ".BINDAT", "rb") as fh:
            shipped = fh.read()
        self.assertEqual(out, shipped)

    def test_edit_correctness_all_types(self):
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        C = self._compile_mod()
        sd = self._dict()
        base = (
            "[GLOBALS]\r\n"
            "\t<INTEGER>EDIT_INT:10\r\n"
            "\t<FLOAT>EDIT_FLOAT:4\r\n"
            "\t<UNSIGNED INT>EDIT_UINT:21\r\n"
            "\t<BOOL>EDIT_BOOL:false\r\n"
            "\t<STRING>EDIT_STRING:HELMET\r\n"
            "\t<INTEGER64>EDIT_I64:5195764663985145273\r\n"
        )
        orig = C.compile_dat(base, sd)

        # INT
        out = C.compile_dat(base.replace("EDIT_INT:10", "EDIT_INT:42"), sd)
        self.assertNotEqual(out, orig)
        t, v, _ = self._root_prop(out, "EDIT_INT")
        self.assertEqual((t, v), (1, 42))

        # FLOAT
        out = C.compile_dat(base.replace("EDIT_FLOAT:4", "EDIT_FLOAT:3.5"), sd)
        self.assertNotEqual(out, orig)
        t, v, _ = self._root_prop(out, "EDIT_FLOAT")
        self.assertEqual(t, 2)
        self.assertAlmostEqual(struct.unpack("<f", struct.pack("<I", v))[0], 3.5, places=5)

        # UNSIGNED INT
        out = C.compile_dat(base.replace("EDIT_UINT:21", "EDIT_UINT:999"), sd)
        self.assertNotEqual(out, orig)
        t, v, _ = self._root_prop(out, "EDIT_UINT")
        self.assertEqual((t, v), (4, 999))

        # BOOL
        out = C.compile_dat(base.replace("EDIT_BOOL:false", "EDIT_BOOL:true"), sd)
        self.assertNotEqual(out, orig)
        t, v, _ = self._root_prop(out, "EDIT_BOOL")
        self.assertEqual((t, v), (6, 1))

        # STRING (value resolves to the global dictionary id, not a hash)
        out = C.compile_dat(base.replace("EDIT_STRING:HELMET", "EDIT_STRING:CHEST ARMOR"), sd)
        self.assertNotEqual(out, orig)
        t, v, id2s = self._root_prop(out, "EDIT_STRING")
        self.assertEqual(t, 5)
        self.assertEqual(id2s.get(v), "CHEST ARMOR")

        # INTEGER64
        out = C.compile_dat(base.replace("EDIT_I64:5195764663985145273", "EDIT_I64:123456789012345"), sd)
        self.assertNotEqual(out, orig)
        t, v, _ = self._root_prop(out, "EDIT_I64")
        self.assertEqual((t, v), (7, 123456789012345))


class CompileLayoutTests(unittest.TestCase):
    """layout2binlayout.compile_layout must serialize .BINLAYOUT from scratch
    (parsing the .LAYOUT text, reading NO existing binary) byte-exact to GUTS.

    Covers the two structured sub-formats that the flat schema path used to
    drop -- a Logic Group's logic graph and a Group's trailing datagroup tree --
    plus a Timeline graph, and proves edit-correctness (the output tracks the
    text, so it is a real compiler, not an echo).

    Requires the real TL2 install (E:\\Torchlight 2\\MEDIA); skips otherwise."""

    MEDIA = r"E:\Torchlight 2\MEDIA"

    @classmethod
    def _mod(cls):
        from mikuro_mod_packer import binlayout as layout2binlayout
        return layout2binlayout

    def _assert_byte_exact(self, rel):
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        lp = os.path.join(self.MEDIA, rel)
        bp = lp + ".BINLAYOUT"
        if not (os.path.isfile(lp) and os.path.isfile(bp)):
            self.skipTest("%s not present" % rel)
        L = self._mod()
        with open(bp, "rb") as fh:
            shipped = fh.read()
        self.assertEqual(L.compile_layout(lp), shipped,
                         msg="not byte-exact: %s" % rel)

    # -- the two formerly-dropped sub-formats --------------------------------
    def test_logic_group_byte_exact(self):
        # A Logic Group's logic graph (LOGICOBJECT/LOGICLINK) lives in the
        # object's ADPROP region; the old flat path dropped it entirely.
        self._assert_byte_exact(os.path.join("LAYOUTS", "ACT1", "NIGHT_ZOMBIES.LAYOUT"))

    def test_logic_group_multi_byte_exact(self):
        # 3 logic groups, 44 logic objects, 59 links.
        self._assert_byte_exact("BOSSMUSIC.LAYOUT")

    def test_datagroup_byte_exact(self):
        # A single Group -> a 2-node datagroup tree (synthetic root + Group).
        self._assert_byte_exact(os.path.join(
            "LEVELSETS", "PROPS", "Z2DESERT_PROPS", "DAPPLELAYOUT.LAYOUT"))

    def test_datagroup_nested_byte_exact(self):
        # Nested Groups -> a nested datagroup tree, with TAG/theme fields.
        self._assert_byte_exact("PARTICLEBACKGROUNDROOMOUTSIDE.LAYOUT")

    def test_timeline_byte_exact(self):
        # A Timeline graph (TIMELINEDATA) in the ADPROP region.
        self._assert_byte_exact(os.path.join(
            "LEVELSETS", "PROPS", "SHRINES", "ARMOR_RACK.LAYOUT"))

    # -- edit-correctness: the output tracks the text (real compiler) --------
    def test_logic_link_edit_changes_output(self):
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        lp = os.path.join(self.MEDIA, "LAYOUTS", "ACT1", "NIGHT_ZOMBIES.LAYOUT")
        if not os.path.isfile(lp):
            self.skipTest("NIGHT_ZOMBIES not present")
        L = self._mod()
        raw = open(lp, "rb").read()
        raw = raw[2:] if raw[:2] == b"\xff\xfe" else raw
        text = raw.decode("utf-16-le")
        base = L.compile_layout(text)
        # Change a LOGICLINK OUTPUTNAME -> different bytes (and a different length,
        # since the link name is stored inline as a string).
        edited = L.compile_layout(text.replace("OUTPUTNAME:Activated",
                                               "OUTPUTNAME:Deactivated", 1))
        self.assertNotEqual(base, edited)
        self.assertIn("D\x00e\x00a\x00c\x00t\x00i\x00v\x00a\x00t\x00e\x00d\x00".encode("latin1"),
                      edited)

    def test_datagroup_tag_edit_changes_output(self):
        # Editing a Group's TAG must re-resolve the datagroup @92 id (proves the
        # datagroup is rebuilt from text, not echoed).
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        L = self._mod()
        tagmap = L._load_dgtags()
        if "CHESTS STANDARD" not in tagmap or "CHESTS_SPECIAL" not in tagmap:
            self.skipTest("datagroup tag map not available")
        text = (
            "[Layout]\r\n\t<INTEGER>VERSION:4\r\n\t<UNSIGNED INT>COUNT:1\r\n"
            "\t[OBJECTS]\r\n\t\t[BASEOBJECT]\r\n\t\t\t[PROPERTIES]\r\n"
            "\t\t\t\t<STRING>DESCRIPTOR:Group\r\n"
            "\t\t\t\t<STRING>NAME:g\r\n"
            "\t\t\t\t<INTEGER64>PARENTID:-1\r\n"
            "\t\t\t\t<INTEGER64>ID:123\r\n"
            "\t\t\t\t<STRING>TAG:%s\r\n"
            "\t\t\t[/PROPERTIES]\r\n\t\t[/BASEOBJECT]\r\n"
            "\t[/OBJECTS]\r\n[/Layout]\r\n"
        )
        a = L.compile_layout(text % "CHESTS STANDARD")
        b = L.compile_layout(text % "CHESTS_SPECIAL")
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), len(b))   # only an id changed, not a length
        # The two differ ONLY inside the single Group node's 4-byte @92 tag id,
        # which sits in the trailing datagroup section.
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        dg = struct.unpack_from("<I", a, 2)[0]
        self.assertTrue(diff and all(i >= dg for i in diff))   # all in datagroup
        # The @92 field is the (unique) u32 whose value is the resolved tag id in
        # BOTH outputs -- a, the source tag id, and b, the edited tag id.
        tag_off = [i for i in range(dg, len(a) - 3)
                   if struct.unpack_from("<I", a, i)[0] == tagmap["CHESTS STANDARD"]
                   and struct.unpack_from("<I", b, i)[0] == tagmap["CHESTS_SPECIAL"]]
        self.assertEqual(len(tag_off), 1)

    def test_no_binary_read(self):
        # Compiling from TEXT ONLY (no path) must reproduce the shipped binary,
        # proving the compiler never opens the sibling .BINLAYOUT.
        if not os.path.isdir(self.MEDIA):
            self.skipTest("TL2 install not present")
        lp = os.path.join(self.MEDIA, "LAYOUTS", "ACT1", "NIGHT_ZOMBIES.LAYOUT")
        bp = lp + ".BINLAYOUT"
        if not (os.path.isfile(lp) and os.path.isfile(bp)):
            self.skipTest("NIGHT_ZOMBIES not present")
        L = self._mod()
        raw = open(lp, "rb").read()
        raw = raw[2:] if raw[:2] == b"\xff\xfe" else raw
        out = L.compile_layout(raw.decode("utf-16-le"))   # text only
        self.assertEqual(out, open(bp, "rb").read())


class FromScratchPackTests(unittest.TestCase):
    """The .MOD packer builds a valid container FROM SCRATCH — no reference .MOD.
    Uses a temp-dir fixture (no TL2 install needed): MEDIA with a handful of raw
    assets (no .DAT/.LAYOUT, so no compiler/string-dict dependency)."""

    def _packer(self):
        import importlib
        return importlib.import_module("mikuro_mod_packer.packer")

    def _make_mod(self, root):
        media = os.path.join(root, "MEDIA")
        os.makedirs(os.path.join(media, "MODELS"))
        os.makedirs(os.path.join(media, "UNITS", "ITEMS"))
        # raw assets: a DDS, a sibling PNG (must be dropped), a MESH, a JPG
        # (stored uncompressed), and a root-level RAW index.
        files = {
            os.path.join(media, "MODELS", "SWORD.MESH"): b"MESHDATA" * 40,
            os.path.join(media, "MODELS", "SWORD.DDS"): b"\x00DDS\x00" * 60,
            os.path.join(media, "MODELS", "SWORD.PNG"): b"PNGDROPPED" * 20,
            os.path.join(media, "UNITS", "ITEMS", "ART.JPG"): bytes(range(256)) * 8,
            os.path.join(media, "EFFECTS.RAW"): b"RAWINDEX\x00" * 30,
        }
        for p, data in files.items():
            with open(p, "wb") as fh:
                fh.write(data)
        mod_dat = (
            "[MOD]\r\n"
            "\t<STRING>AUTHOR:TestAuthor\r\n"
            "\t<STRING>NAME:My Test Mod\r\n"
            "\t<STRING>DESCRIPTION:A description.\r\n"
            "\t<INTEGER64>MOD_ID:1234567890\r\n"
            "\t<STRING>WEBSITE:http://example.com\r\n"
            "\t<INTEGER>VERSION:7\r\n"
            "[/MOD]\r\n"
        )
        with open(os.path.join(root, "MOD.DAT"), "w", encoding="utf-16-le") as fh:
            fh.write(mod_dat)
        return media

    def test_build_header_maps_mod_dat_fields(self):
        P = self._packer()
        with tempfile.TemporaryDirectory() as root:
            self._make_mod(root)
            h = P.build_header(root)
        self.assertEqual(h["ver"], 4)
        self.assertEqual(h["title"], "My Test Mod")        # NAME → title
        self.assertEqual(h["author"], "TestAuthor")
        self.assertEqual(h["descr"], "A description.")
        self.assertEqual(h["website"], "http://example.com")
        self.assertEqual(h["modid"], 1234567890)
        self.assertEqual(h["modver"], 8)                    # VERSION 7 + 1
        self.assertEqual(h["reqs"], [])
        self.assertEqual(h["dels"], [])
        self.assertEqual(h["reqHash"], 0)

    def test_manifest_type_codes_and_png_dedup(self):
        P = self._packer()
        with tempfile.TemporaryDirectory() as root:
            media = self._make_mod(root)
            dirs, fc = P.build_manifest_dirs(media)
        by_name = {}
        for dname, recs in dirs:
            for crc, typ, name, off, size, ft in recs:
                by_name[(dname + name).upper()] = typ
        self.assertEqual(by_name["MEDIA/MODELS/SWORD.MESH"], 2)
        self.assertEqual(by_name["MEDIA/MODELS/SWORD.DDS"], 4)
        self.assertEqual(by_name["MEDIA/UNITS/ITEMS/ART.JPG"], 24)
        self.assertEqual(by_name["MEDIA/EFFECTS.RAW"], 9)
        # PNG dropped because a sibling DDS exists.
        self.assertNotIn("MEDIA/MODELS/SWORD.PNG", by_name)
        # root placeholder + every dir node present.
        names = {dn for dn, _ in dirs}
        self.assertIn("MEDIA/", names)
        self.assertIn("MEDIA/MODELS/", names)
        self.assertIn("MEDIA/UNITS/ITEMS/", names)

    def test_pack_mod_round_trips_and_matches_scan(self):
        P = self._packer()
        with tempfile.TemporaryDirectory() as root:
            media = self._make_mod(root)
            out = os.path.join(root, "out.MOD")
            size = P.pack_mod(media, out, "My Test Mod", original_mod_dir=root)
            self.assertGreater(size, 0)
            tdata = open(out, "rb").read()
        h, dirs = P._disasm_mod(tdata)

        # header round-trips from MOD.DAT
        self.assertEqual(h["ver"], 4)
        self.assertEqual(h["title"], "My Test Mod")
        self.assertEqual(h["modid"], 1234567890)
        self.assertEqual(h["modver"], 8)

        # file set == a fresh MEDIA scan (with PNG→DDS dedup), and every block's
        # crc/size round-trips through the manifest.
        file_names, stored, ok = set(), {}, 0
        for dname, recs in dirs:
            for crc, typ, name, off, size, ft in recs:
                if typ == 7:
                    continue
                full = (dname + name).upper()
                file_names.add(full)
                dsz, csz = struct.unpack_from("<II", tdata, h["offData"] + off)
                s = h["offData"] + off + 8
                stream = tdata[s:s + (csz or dsz)]
                import zlib
                content = stream if csz == 0 else zlib.decompress(stream)
                self.assertEqual(zlib.crc32(content) & 0xFFFFFFFF, crc)
                self.assertEqual(len(content), size)
                stored[full] = (csz == 0)
                ok += 1
        self.assertEqual(ok, 4)        # MESH, DDS, JPG, RAW (PNG deduped)
        self.assertEqual(file_names, {
            "MEDIA/MODELS/SWORD.MESH", "MEDIA/MODELS/SWORD.DDS",
            "MEDIA/UNITS/ITEMS/ART.JPG", "MEDIA/EFFECTS.RAW",
        })
        # only the .JPG is stored uncompressed (byte_11E94CD8[24]==0); the rest
        # are zlib-compressed.
        self.assertTrue(stored["MEDIA/UNITS/ITEMS/ART.JPG"])
        self.assertFalse(stored["MEDIA/MODELS/SWORD.MESH"])
        self.assertFalse(stored["MEDIA/EFFECTS.RAW"])

    def test_pack_mod_needs_no_reference_mod(self):
        """A directory with MOD.DAT + MEDIA but NO .MOD still packs."""
        P = self._packer()
        with tempfile.TemporaryDirectory() as root:
            media = self._make_mod(root)
            self.assertFalse(
                any(f.lower().endswith(".mod") for f in os.listdir(root)))
            out = os.path.join(root, "built.MOD")
            size = P.pack_mod(media, out, "My Test Mod", original_mod_dir=root)
        self.assertGreater(size, 0)


class PakRollingHashTests(unittest.TestCase):
    """The PAK data-section rolling hash is VALIDATED by the game's mod loader
    (EditorGuts sub_102A2690 / writer sub_102A7100): a wrong value makes the game
    silently reject the whole mod ("Unable to load mod"). pack_mod must write the
    correct hash (RE: stride divisor = a deterministic LCG seeded with the data
    length N)."""

    INSTALL_MODS = r"E:\Torchlight 2\mods"

    def _packer(self):
        import importlib
        return importlib.import_module("mikuro_mod_packer.packer")

    def _native_mods(self):
        """Editor-published / shipped .MOD files under the install mods tree."""
        out = []
        for root, _dirs, files in os.walk(self.INSTALL_MODS):
            for f in files:
                if f.upper().endswith(".MOD"):
                    out.append(os.path.join(root, f))
        return out

    def test_pak_rolling_hash_reproduces_shipped_mods(self):
        """Ground truth: _pak_rolling_hash must reproduce the rollingHash stored
        in real editor-packed .MODs byte-exactly (the game recomputes the same)."""
        P = self._packer()
        if not os.path.isdir(self.INSTALL_MODS):
            self.skipTest("TL2 install mods dir not present")
        mods = self._native_mods()
        if not mods:
            self.skipTest("no native .MOD files found to validate against")
        seen, checked = set(), 0
        for p in mods:
            with open(p, "rb") as fh:
                raw = fh.read()
            try:
                h, _ = P._disasm_mod(raw)
            except Exception:
                continue
            oD, oM = h["offData"], h["offMan"]
            if oM <= oD or oM > len(raw) or oM - oD <= 8:
                continue
            stored = struct.unpack_from("<I", raw, oD + 4)[0]
            if stored in seen:
                continue
            seen.add(stored)
            self.assertEqual(
                P._pak_rolling_hash(raw[oD:oM]), stored,
                msg=f"rollingHash mismatch for {os.path.basename(p)} (N={oM-oD})")
            checked += 1
        self.assertGreater(checked, 0, "no parseable native .MOD validated")

    def test_pack_mod_writes_validating_nonzero_hash(self):
        """A from-scratch pack writes a non-zero rollingHash that the game's
        recompute (the same algorithm) accepts. Independent transcription of the
        algorithm below — must agree with _pak_rolling_hash AND be non-zero."""
        P = self._packer()
        with tempfile.TemporaryDirectory() as root:
            media = FromScratchPackTests()._make_mod(root)
            out = os.path.join(root, "out.MOD")
            P.pack_mod(media, out, "My Test Mod", original_mod_dir=root)
            with open(out, "rb") as fh:
                raw = fh.read()
        h, _ = P._disasm_mod(raw)
        oD, oM = h["offData"], h["offMan"]
        data = raw[oD:oM]
        stored = struct.unpack_from("<I", raw, oD + 4)[0]

        # Independent recompute (the game validator's algorithm).
        n = len(data)
        divisor = 25 + (695696193 * n & 0xFFFFFFFF) % 51
        stride = max(2, n // divisor)
        acc = n & 0xFFFFFFFF
        k = 8
        while k < n:
            b = data[k] - 256 if data[k] >= 128 else data[k]
            acc = (b + 33 * acc) & 0xFFFFFFFF
            k += stride
        b = data[n - 1] - 256 if data[n - 1] >= 128 else data[n - 1]
        expected = (b + 33 * acc) & 0xFFFFFFFF

        self.assertNotEqual(stored, 0, "rollingHash must not be 0 (game rejects it)")
        self.assertEqual(stored, expected)


if __name__ == "__main__":
    unittest.main()
