"""
dat.py — LEVELSETS .DAT reader.

A .DAT is a UTF-16-LE (BOM) or ASCII text tree of bracketed blocks. We extract
[PIECE] blocks, each describing a room-piece template:
    <STRING>NAME:floor_01
    <INTEGER64>GUID:5827754378657075679
    <STRING>FILE:media/levelsets/Z1Tundra/grass_floor_01.mesh
    <STRING>COLLISIONFILE:media/levelsets/Z1Tundra/floor_collision.mesh
    <BOOL>SCALABLE:true
    <BOOL>NEVERBAKE:false / RENDERSHADOW / ...

We build guid -> PieceDef. GUID in .DAT is typed <INTEGER64>; in .LAYOUT the same
value is typed <STRING>. Both name the same signed 64-bit integer; we key on the
decimal string so the two file types match regardless of declared type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PieceDef:
    name: str = ""
    guid: str = ""           # decimal string of the signed 64-bit value
    file: str = ""           # render mesh (relative media path) — first visual
    collision_file: str = ""  # collision mesh (relative media path), may be ""
    scalable: bool = True
    neverbake: bool = False
    # <BOOL>ALWAYSBAKECOLLISION: forces this piece TYPE into the master pathing
    # collision regardless of the instance BAKE flag — it is descriptor[+0x3E] in the
    # editor's master-collision add gate (RE'd: CLevel_RebuildLevel_GenPathing
    # 0x10203fd0 `cmp byte[descriptor+3Eh]`, set in sub_10263280 from "ALWAYSBAKECOLLISION").
    alwaysbakecollision: bool = False
    tags: tuple = ()
    # A [PIECE] is a SET of visual sub-pieces: each <STRING>FILE: is one visual
    # mesh and each <STRING>COLLISIONFILE: its (optionally) paired collision mesh.
    # The layout's per-instance <STRING>VISUAL:N picks which one. We keep the full
    # ordered lists so region.select_collision_file() can index by VISUAL exactly
    # as the editor does (sub_10231080 / sub_102317F0). `file`/`collision_file`
    # remain the index-0 entry for back-compat.
    files: tuple = ()        # all render-mesh variants, in declared order
    collision_files: tuple = ()  # all collision-mesh variants, in declared order


def _decode(data: bytes) -> str:
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16-le", errors="replace")
    if data[:2] == b"\xfe\xff":
        return data.decode("utf-16-be", errors="replace")
    return data.decode("latin-1", errors="replace")


_PROP_RE = re.compile(r"<([^>]+)>([A-Z0-9 _]+):(.*)")


def _props_of_block(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ln in lines:
        m = _PROP_RE.match(ln.strip())
        if not m:
            continue
        key = m.group(2).strip()
        val = m.group(3).strip()
        out.setdefault(key, []).append(val)
    return out


def parse_dat(data: bytes) -> dict[str, PieceDef]:
    txt = _decode(data)
    lines = txt.splitlines()
    pieces: dict[str, PieceDef] = {}
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == "[PIECE]":
            block = []
            i += 1
            depth = 0
            while i < n:
                s = lines[i].strip()
                if s == "[/PIECE]" and depth == 0:
                    i += 1
                    break
                # ignore nested bracket blocks but keep their props out of confusion
                block.append(lines[i])
                i += 1
            props = _props_of_block(block)
            files = tuple(props.get("FILE", ()))
            colls = tuple(props.get("COLLISIONFILE", ()))
            pd = PieceDef(
                name=(props.get("NAME") or [""])[0],
                guid=(props.get("GUID") or [""])[0],
                file=(files[0] if files else ""),
                collision_file=(colls[0] if colls else ""),
                scalable=(props.get("SCALABLE") or ["true"])[0].lower() == "true",
                neverbake=(props.get("NEVERBAKE") or ["false"])[0].lower() == "true",
                alwaysbakecollision=(props.get("ALWAYSBAKECOLLISION") or ["false"])[0].lower() == "true",
                tags=tuple(props.get("TAG", ())),
                files=files,
                collision_files=colls,
            )
            if pd.guid:
                pieces[pd.guid] = pd
        else:
            i += 1
    return pieces


def load_all_levelsets(levelsets_dir: str) -> dict[str, PieceDef]:
    """Scan every *.DAT (not *.BINDAT) under levelsets_dir, merge guid->PieceDef."""
    import os

    out: dict[str, PieceDef] = {}
    for dirpath, _dirs, files in os.walk(levelsets_dir):
        for fn in files:
            if fn.upper().endswith(".DAT") and not fn.upper().endswith(".BINDAT"):
                try:
                    with open(os.path.join(dirpath, fn), "rb") as f:
                        out.update(parse_dat(f.read()))
                except Exception:
                    pass
    return out
