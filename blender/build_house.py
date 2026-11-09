"""Blender side of the pipeline. Do not run directly; use `python blender/pipeline.py apply`.

    blender --background --factory-startup --python build_house.py -- <resolved.json> <out_dir>

Pure function of the resolved model: builds the scene from scratch (1 Blender unit = 1 ft, no
materials, Workbench object colors), saves house.blend, and renders one labeled top-down plan per
level plus an exterior view. Every object carries a `levels` custom property that drives which
renders it appears in.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
M = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
OUT = Path(argv[1])

EXT_T = M["defaults"].get("exterior_wall_thickness", 0.5)
INT_T = M["defaults"].get("interior_wall_thickness", 0.375)
LEVELS = M["levels"]
LEVEL_ORDER = sorted(LEVELS, key=lambda n: LEVELS[n]["floor_z"])

WALL = (0.18, 0.18, 0.2, 1)
SLAB = (0.82, 0.82, 0.8, 1)
STAIR = (0.55, 0.5, 0.45, 1)
INK = (0.05, 0.05, 0.05, 1)
DIM = (0.75, 0.1, 0.1, 1)
ROOF = (0.45, 0.42, 0.4, 1)
SITE = (0.7, 0.75, 0.68, 1)
STAIRWELL = (0.78, 0.74, 0.7, 1)
GLASS = (0.55, 0.68, 0.78, 1)
BAY = (0.42, 0.42, 0.4, 1)
PLANT = (0.22, 0.4, 0.2, 1)
SURFACE = {
    "brick": (0.62, 0.36, 0.28, 1),
    "concrete": (0.8, 0.79, 0.76, 1),
    "mulch": (0.38, 0.27, 0.18, 1),
    "rock_mulch": (0.66, 0.62, 0.56, 1),
}
FLOOR = {  # plan color by floor finish, so "redo floors" options read at a glance
    "carpet": (0.70, 0.64, 0.56, 1),
    "laminate": (0.80, 0.60, 0.38, 1),
    "hardwood": (0.68, 0.45, 0.25, 1),
    "lvp": (0.82, 0.68, 0.50, 1),
    "tile": (0.80, 0.82, 0.84, 1),
    "concrete": (0.72, 0.72, 0.74, 1),
    "painted_concrete": (0.62, 0.66, 0.72, 1),
}
BEARING_COL = {  # interior wall color by load-bearing prior
    "likely": (0.78, 0.12, 0.1, 1),
    "unknown": (0.95, 0.55, 0.1, 1),
    "unlikely": (0.35, 0.35, 0.38, 1),
    "no": (0.55, 0.55, 0.58, 1),
}
LIGHT = (1.0, 0.82, 0.15, 1)
LABEL_LIFT = 9.0  # plan labels float above everything on their level (walls, light fixtures); hidden in the viewport


def log(msg):
    print(f"[build] {msg}", flush=True)


def fmt_ft(v):
    n = round(abs(v) * 12)
    return f"{'-' if v < 0 else ''}{n // 12}'-{n % 12}\""


def pastel(key):
    h = hashlib.md5(key.encode()).digest()
    return (0.6 + h[0] / 640, 0.6 + h[1] / 640, 0.6 + h[2] / 640, 1)


# ---------- primitives ----------

def tag(obj, name, color, levels):
    obj.color = color
    obj["levels"] = list(levels)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_obj(name, verts, faces, color, levels):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return tag(bpy.data.objects.new(name, me), name, color, levels)


def box(name, x0, y0, z0, x1, y1, z1, color, levels):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return mesh_obj(name, v, f, color, levels)


def text(name, body, x, y, z, size, color, levels, rot=0.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new(name, cu)
    ob.location = (x, y, z + LABEL_LIFT)
    ob.rotation_euler = (0, 0, rot)
    return tag(ob, name, color, levels)


# ---------- walls with openings ----------

def wall_run(name, axis, a, b, fixed0, fixed1, z0, h, openings, levels):
    """Wall along `axis` ('x' or 'y') from a to b, thickness between fixed0..fixed1; openings: (s, e, sill, head)."""
    def seg(i, s, e, zb, zt):
        if e - s < 1e-4 or zt - zb < 1e-4:
            return
        if axis == "x":
            box(f"{name}.{i}", s, fixed0, z0 + zb, e, fixed1, z0 + zt, WALL, levels)
        else:
            box(f"{name}.{i}", fixed0, s, z0 + zb, fixed1, e, z0 + zt, WALL, levels)

    cur, i = a, 0
    for s, e, sill, head in sorted(openings):
        s, e = max(s, a), min(e, b)
        seg(i, cur, s, 0, h); seg(i + 1, s, e, 0, sill); seg(i + 2, s, e, head, h)
        cur, i = e, i + 3
    seg(i, cur, b, 0, h)


def level_openings(level):
    """Declared openings plus stair pass-throughs where a stair crosses this level's side walls."""
    r = LEVELS[level]["rect"]
    ops = {"front": [], "back": [], "left": [], "right": []}
    for o in M["openings"]:
        if o["level"] == level:
            ops[o["wall"]].append((o["span"][0], o["span"][1], o["sill"], o["head"]))
    h = LEVELS[level]["ceiling_height"]
    for s in M["stairs"]:
        if level not in (s["from"], s["to"]):
            continue
        sx0, sy0, sx1, sy1 = s["rect"]
        if sx0 < r[0] + EXT_T and sx1 > r[0]:
            ops["left"].append((sy0, sy1, 0, h))
        if sx0 < r[2] and sx1 > r[2] - EXT_T:
            ops["right"].append((sy0, sy1, 0, h))
    return ops


def build_level(name):
    lv = LEVELS[name]
    x0, y0, x1, y1 = lv["rect"]
    z, h, t = lv["floor_z"], lv["ceiling_height"], EXT_T
    lvls = [name]
    slab_t = 0.33 if name == LEVEL_ORDER[0] else 1.0
    box(f"{name}.slab", x0, y0, z - slab_t, x1, y1, z - 0.02, SLAB, lvls)
    ops = level_openings(name)
    wall_run(f"{name}.wall.front", "x", x0, x1, y0, y0 + t, z, h, ops["front"], lvls)
    wall_run(f"{name}.wall.back", "x", x0, x1, y1 - t, y1, z, h, ops["back"], lvls)
    wall_run(f"{name}.wall.left", "y", y0 + t, y1 - t, x0, x0 + t, z, h, ops["left"], lvls)
    wall_run(f"{name}.wall.right", "y", y0 + t, y1 - t, x1 - t, x1, z, h, ops["right"], lvls)

    # exterior dimension labels (plan only)
    lab = [f"label:{name}"]
    text(f"{name}.dim.w", fmt_ft(x1 - x0), (x0 + x1) / 2, y0 - 1.6, z + 0.1, 1.1, DIM, lab)
    side_x = x0 - 1.6 if x0 <= 0 else x1 + 1.6
    text(f"{name}.dim.d", fmt_ft(y1 - y0), side_x, (y0 + y1) / 2, z + 0.1, 1.1, DIM, lab, rot=math.pi / 2)


def room_parts(r):
    return r.get("parts") or [r["rect"]]


def build_rooms():
    for r in M["rooms"]:
        parts = room_parts(r)
        z = LEVELS[r["level"]]["floor_z"]
        i = INT_T / 2
        lift = 0.005 if r.get("finished") is False else (0.04 if r.get("closet_of") else 0.02)
        parent = next((p for p in M["rooms"] if p["id"] == r.get("closet_of")), None)
        mat = ((r.get("finish") or {}).get("floor") or {}).get("material") or \
              (((parent or {}).get("finish") or {}).get("floor") or {}).get("material")
        col = FLOOR.get(mat) or ((0.9, 0.9, 0.88, 1) if r.get("finished") is False else pastel(r["id"]))
        for k, (px0, py0, px1, py1) in enumerate(parts):
            # parts that touch share an edge: don't inset there, so an L reads as one floor
            ins = [i, i, i, i]
            for q in parts:
                if q is parts[k]:
                    continue
                if abs(q[2] - px0) < 1e-6: ins[0] = 0
                if abs(q[3] - py0) < 1e-6: ins[1] = 0
                if abs(q[0] - px1) < 1e-6: ins[2] = 0
                if abs(q[1] - py1) < 1e-6: ins[3] = 0
            box(f"room.{r['id']}.{k}", px0 + ins[0], py0 + ins[1], z, px1 - ins[2], py1 - ins[3], z + lift, col, [r["level"]])
        x0, y0, x1, y1 = max(parts, key=lambda p: (p[2] - p[0]) * (p[3] - p[1]))
        conf = "" if r.get("conf") in (None, "high") else f" ({r['conf']})"
        dims = " + ".join(f"{fmt_ft(p[2] - p[0])} x {fmt_ft(p[3] - p[1])}" for p in parts)
        body = f"{r['id']}{conf}\n{dims}" + (f"\n{mat}" if mat else "")
        size = max(0.4, min(0.85, (x1 - x0) / 11))
        if r.get("closet_of"):
            body, size = "CL", 0.45
        if r.get("finished") is False:
            body = f"{r['id']} ({r.get('conf', '')})\n{r.get('note', '')}"
            text(f"label.{r['id']}", body, (x0 + x1) / 2, y0 + 3.0, z + 0.1, 0.55, INK, [f"label:{r['level']}"])
        else:
            text(f"label.{r['id']}", body, (x0 + x1) / 2, (y0 + y1) / 2, z + 0.1, size, INK, [f"label:{r['level']}"])


def build_stairs():
    for s in M["stairs"]:
        x0, y0, x1, y1 = s["rect"]
        za, zb = LEVELS[s["from"]]["floor_z"], LEVELS[s["to"]]["floor_z"]
        n = max(2, round(abs(zb - za) / 0.62))
        run = (x1 - x0) / n
        lv = [s["from"], s["to"]]
        for k in range(n):
            ztop = za + (k + 1) * (zb - za) / n
            if s["dir"] == "+x":
                a, b = x0 + k * run, x0 + (k + 1) * run
            else:
                a, b = x1 - (k + 1) * run, x1 - k * run
            box(f"stair.{s['id']}.{k}", a, y0, ztop - 0.15, b, y1, ztop, STAIR, lv)
        up = zb > za
        if not up:  # a down-flight sits below its own floor: mark the stairwell on the plan
            box(f"stairwell.{s['id']}", x0, y0, za + 0.03, x1, y1, za + 0.04, STAIRWELL, [f"label:{s['from']}"])
        for L in lv:
            word = ("UP" if up else "DN") if L == s["from"] else ("DN" if up else "UP")
            other = s["to"] if L == s["from"] else s["from"]
            text(f"label.stair.{s['id']}.{L}", f"{word} to {other}", (x0 + x1) / 2, (y0 + y1) / 2,
                 LEVELS[L]["floor_z"], 0.5, INK, [f"label:{L}"])


def build_walls():
    """Interior partitions: first-class, colored by bearing prior, with door openings cut through."""
    for w in M.get("walls", []):
        (ax, ay), (bx, by) = w["from"], w["to"]
        lv = LEVELS[w["level"]]
        z = lv["floor_z"]
        h = w.get("height", lv["ceiling_height"])
        t = w.get("thickness", INT_T) / 2
        col = BEARING_COL.get(w["bearing"], WALL)
        # cycle 1: no header over interior doors, so the opening reads in top-down plans
        ops = [(d["span"][0], d["span"][1], 0, h) for d in w.get("doors", [])]
        name = f"wall.{w['id']}"
        if ay == by:
            wall_run(name, "x", min(ax, bx), max(ax, bx), ay - t, ay + t, z, h, ops, [w["level"]])
        else:
            wall_run(name, "y", min(ay, by), max(ay, by), ax - t, ax + t, z, h, ops, [w["level"]])
        for ob in bpy.data.objects:
            if ob.name.startswith(name + "."):
                ob.color = col


def build_fixtures():
    """Light fixtures as markers hung just under the ceiling (wall mounts sit at 6.5 ft)."""
    size = {"ceiling_fan": 1.1, "chandelier": 0.8, "panel": 0.9}
    for f in M.get("fixtures", []):
        room = next(r for r in M["rooms"] if r["id"] == f["room"])
        lv = LEVELS[room["level"]]
        ztop = lv["floor_z"] + (6.5 if f.get("mount") == "wall" else lv["ceiling_height"] - 0.2)
        x, y = f["at"]
        if f.get("length"):  # linear fixtures (track, light bar, shop light) run along x unless axis: y
            hl = f["length"] / 2
            dx, dy = (hl, 0.25) if f.get("axis", "x") == "x" else (0.25, hl)
            box(f"fixture.{f['id']}", x - dx, y - dy, ztop - 0.25, x + dx, y + dy, ztop, LIGHT, [room["level"]])
            continue
        me = bpy.data.meshes.new(f["id"])
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = tag(bpy.data.objects.new(f"fixture.{f['id']}", me), f["id"], LIGHT, [room["level"]])
        r = size.get(f["kind"], 0.4)
        ob.location = (x, y, ztop - 0.15)
        ob.scale = (r, r, 0.15)


def build_roofs():
    for r in M["roofs"]:
        lv = LEVELS[r["over"]]
        x0, y0, x1, y1 = lv["rect"]
        o = r.get("overhang", 0)
        x0, y0, x1, y1 = x0 - o, y0 - o, x1 + o, y1 + o
        rise, run = (float(p) for p in r["pitch"].split("/"))
        ze = lv["floor_z"] + lv["ceiling_height"] + 0.75
        if r["ridge_axis"] == "x":
            zr = ze + (y1 - y0) / 2 * rise / run
            ym = (y0 + y1) / 2
            v = [(x0, y0, ze), (x1, y0, ze), (x1, y1, ze), (x0, y1, ze), (x0, ym, zr), (x1, ym, zr)]
            f = [(0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
        else:
            zr = ze + (x1 - x0) / 2 * rise / run
            xm = (x0 + x1) / 2
            v = [(x0, y0, ze), (x1, y0, ze), (x1, y1, ze), (x0, y1, ze), (xm, y0, zr), (xm, y1, zr)]
            f = [(0, 4, 5, 3), (1, 2, 5, 4), (0, 1, 4), (2, 3, 5), (0, 3, 2, 1)]
        mesh_obj(f"roof.{r['id']}", v, f, ROOF, ["roof"])


def prism(name, poly, z0, z1, color, levels):
    n = len(poly)
    v = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    f += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return mesh_obj(name, v, f, color, levels)


def build_openings():
    """Glass panes in window openings, and box bump-outs (bays) with a shed roof where declared."""
    for o in M["openings"]:
        if o["kind"] != "window":
            continue
        lv = LEVELS[o["level"]]
        x0, y0, x1, y1 = lv["rect"]
        z = lv["floor_z"]
        s, e = o["span"]
        zs, zh = z + o["sill"], z + o["head"]
        bay = o.get("bay")
        if bay and o["wall"] in ("front", "back"):
            d = bay["depth"]
            wall_y, out = (y0, -1) if o["wall"] == "front" else (y1, 1)
            face = wall_y + out * d
            ya, yb = sorted((wall_y, face))
            box(f"bay.{o['id']}.body", s - 0.4, ya, zs - 0.6, e + 0.4, yb, zh + 0.35, BAY, [o["level"]])
            pa, pb = sorted((face, face + out * 0.04))
            box(f"bay.{o['id']}.glass", s, pa, zs, e, pb, zh, GLASS, [o["level"]])
            # shed roof: high at the wall, low past the face
            eave = face + out * 0.5
            zt = zh + 0.35
            v = [(s - 0.6, wall_y, zt + 0.9), (e + 0.6, wall_y, zt + 0.9), (e + 0.6, eave, zt + 0.15), (s - 0.6, eave, zt + 0.15)]
            v += [(x, y, zz - 0.2) for x, y, zz in v]
            f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
            mesh_obj(f"bay.{o['id']}.roof", v, f, ROOF, [o["level"], "roof"])
            continue
        t, m = EXT_T, 0.03
        if o["wall"] == "front":
            box(f"glass.{o['id']}", s, y0 + t / 2 - m, zs, e, y0 + t / 2 + m, zh, GLASS, [o["level"]])
        elif o["wall"] == "back":
            box(f"glass.{o['id']}", s, y1 - t / 2 - m, zs, e, y1 - t / 2 + m, zh, GLASS, [o["level"]])
        elif o["wall"] == "left":
            box(f"glass.{o['id']}", x0 + t / 2 - m, s, zs, x0 + t / 2 + m, e, zh, GLASS, [o["level"]])
        else:
            box(f"glass.{o['id']}", x1 - t / 2 - m, s, zs, x1 - t / 2 + m, e, zh, GLASS, [o["level"]])


def build_site():
    g = M["site"]["grade_z"]
    box("ground", -60, -50, g - 0.5, 90, 110, g, (0.62, 0.7, 0.55, 1), ["ground"])
    for ls in M["site"].get("landscape", []):
        poly = ls.get("poly") or [[ls["rect"][0], ls["rect"][1]], [ls["rect"][2], ls["rect"][1]],
                                  [ls["rect"][2], ls["rect"][3]], [ls["rect"][0], ls["rect"][3]]]
        hgt = {"bed": 0.12, "walk": 0.06, "driveway": 0.04}.get(ls["kind"], 0.05)
        prism(f"landscape.{ls['id']}", poly, g, g + hgt, SURFACE.get(ls.get("surface"), SITE), ["site", "main"])
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        text(f"label.{ls['id']}", ls["id"], cx, cy, 0.0, 0.45, INK, ["label:main"])
    for p in M["site"].get("plants", []):
        me = bpy.data.meshes.new(p["id"])
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = tag(bpy.data.objects.new(f"plant.{p['id']}", me), p["id"], PLANT, ["site", "main"])
        ob.location = (p["at"][0], p["at"][1], g + p["height"] / 2)
        ob.scale = (p["dia"] / 2, p["dia"] / 2, p["height"] / 2)
    for ft in M["site"]["features"]:
        x0, y0, x1, y1 = ft["rect"]
        if ft["kind"] == "deck":
            box(f"feature.{ft['id']}", x0, y0, g, x1, y1, -0.6, SITE, ["site", "main"])
        else:
            box(f"feature.{ft['id']}", x0, y0, g, x1, y1, g + 0.25, SURFACE.get(ft.get("surface"), SITE), ["site", "main"])
            if "pergola" in ft["kind"]:
                box(f"feature.{ft['id']}.pergola", x0, y0, 7.5, x1, y1, 7.9, (0.6, 0.55, 0.45, 1), ["site"])
        text(f"label.{ft['id']}", ft["id"], (x0 + x1) / 2, (y0 + y1) / 2, 0.2, 0.55, INK, ["label:main"])
    for ob in M["site"]["outbuildings"]:
        x0, y0, x1, y1 = ob["rect"]
        box(f"outbuilding.{ob['id']}", x0, y0, g, x1, y1, g + 9, (0.75, 0.73, 0.7, 1), ["site"])


def north_arrow(cx, cy, levels):
    b = M["site"].get("front_bearing_deg")
    if b is None:
        return
    # The front (-y) faces bearing b, so +y points at bearing beta = b + 180 (clockwise from north).
    # North is +y rotated counter-clockwise by beta: (-sin beta, cos beta) in model axes.
    beta = math.radians((b + 180) % 360)
    nx, ny = -math.sin(beta), math.cos(beta)
    tip = Vector((cx + 2.2 * nx, cy + 2.2 * ny, 0))
    for L in levels:
        z = LEVELS[L]["floor_z"] + 0.1
        mesh_obj(f"north.{L}", [(cx - 0.5 * ny, cy + 0.5 * nx, z), (tip.x, tip.y, z), (cx + 0.5 * ny, cy - 0.5 * nx, z)],
                 [(0, 1, 2)], INK, [f"label:{L}"])
        text(f"north.txt.{L}", "N", cx + 3.2 * nx, cy + 3.2 * ny, z, 1.0, INK, [f"label:{L}"])


# ---------- render ----------

def setup_render():
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_WORKBENCH"
    except TypeError as e:
        log(f"engine error {e}")
        raise
    sc.unit_settings.system = "IMPERIAL"
    sc.unit_settings.scale_length = 0.3048
    sc.display.shading.color_type = "OBJECT"
    sc.display.shading.show_object_outline = True
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("World")
    w.color = (1, 1, 1)
    sc.world = w
    sc.render.resolution_x = sc.render.resolution_y = 1600
    sc.render.image_settings.file_format = "PNG"
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def show_only(pred):
    for ob in bpy.data.objects:
        if ob.type == "CAMERA":
            continue
        ob.hide_render = not pred(list(ob.get("levels", [])))


def bounds():
    xs = [v for lv in LEVELS.values() for v in (lv["rect"][0], lv["rect"][2])]
    ys = [v for lv in LEVELS.values() for v in (lv["rect"][1], lv["rect"][3])]
    for ft in M["site"]["features"]:
        xs += [ft["rect"][0], ft["rect"][2]]
        ys += [ft["rect"][1], ft["rect"][3]]
    return min(xs), min(ys), max(xs), max(ys)


def organize_for_viewing(sc):
    """Group objects into one collection per level (plus roof/site/ground/labels) so the saved
    .blend can be explored level by level in the Outliner. Plan labels start hidden: they float
    at eye height and only make sense in the top-down renders."""
    root = sc.collection
    labels = bpy.data.collections.new("labels (plan renders)")
    root.children.link(labels)
    cols = {}
    for name in [*LEVEL_ORDER[::-1], "roof", "site", "ground"]:
        cols[name] = bpy.data.collections.new(name)
        root.children.link(cols[name])
    for ob in list(root.objects):
        lv = list(ob.get("levels", []))
        if not lv:
            continue
        key = lv[0]
        if key.startswith("label:"):
            sub = cols.get(key)
            if sub is None:
                sub = cols[key] = bpy.data.collections.new(f"labels {key[6:]}")
                labels.children.link(sub)
            sub.objects.link(ob)
        else:
            cols[key].objects.link(ob)
        root.objects.unlink(ob)
    sc.view_layers[0].layer_collection.children[labels.name].hide_viewport = True
    for scr in bpy.data.screens:
        for area in scr.areas:
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "SOLID"
                    space.shading.color_type = "OBJECT"
                    space.clip_end = 1000


def render(sc, path):
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    log(f"render {path.name}")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log(f"blender={bpy.app.version_string}")
    for name in LEVEL_ORDER:
        build_level(name)
    build_rooms()
    build_walls()
    build_fixtures()
    build_stairs()
    build_openings()
    build_roofs()
    build_site()
    bx0, by0, bx1, by1 = bounds()
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    north_arrow(bx1 + 1, by1 - 2, LEVEL_ORDER)
    for name in LEVEL_ORDER:
        text(f"title.{name}", f"{name.upper()} LEVEL   floor {fmt_ft(LEVELS[name]['floor_z'])}   cycle 1: +/-1 ft footprint, rooms +/-2 ft",
             cx, by1 + 4, LEVELS[name]["floor_z"] + 0.1, 1.0, INK, [f"label:{name}"])
        text(f"legend.{name}", "walls: red = likely load-bearing, orange = unknown, gray = unlikely/no (all need licensed review)"
             "\nfloor color = finish; yellow = light fixture",
             cx, by0 - 4, LEVELS[name]["floor_z"] + 0.1, 0.6, INK, [f"label:{name}"])

    sc, cam = setup_render()
    span = max(bx1 - bx0, by1 - by0) + 14
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span
    cam.data.clip_end = 1000
    cam.location = (cx, cy + 1.5, 200)
    cam.rotation_euler = (0, 0, 0)
    sc.display.shading.light = "FLAT"
    for i, name in enumerate(LEVEL_ORDER[::-1]):
        show_only(lambda lv, n=name: n in lv or f"label:{n}" in lv)
        render(sc, OUT / f"plan-{len(LEVEL_ORDER) - i}-{name}.png")

    sc.display.shading.light = "STUDIO"
    sc.render.resolution_y = 1100
    cam.data.type = "PERSP"
    cam.data.lens = 35
    target = Vector((cx, cy - 4, 2))
    cam.location = target + Vector((-48, -62, 38))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    show_only(lambda lv: not any(l.startswith("label:") for l in lv))
    render(sc, OUT / "exterior-front-left.png")

    show_only(lambda lv: True)
    organize_for_viewing(sc)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "house.blend"), compress=True)
    log(f"objects={len(bpy.data.objects)}")
    log("DONE")


main()
