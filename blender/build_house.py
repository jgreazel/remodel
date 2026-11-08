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
LABEL_LIFT = 6.0  # plan labels float above treads and furniture-height geometry, below the level's ceiling


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


def build_rooms():
    for r in M["rooms"]:
        x0, y0, x1, y1 = r["rect"]
        z = LEVELS[r["level"]]["floor_z"]
        i = INT_T / 2
        lift = 0.005 if r.get("finished") is False else 0.02
        col = (0.9, 0.9, 0.88, 1) if r.get("finished") is False else pastel(r["id"])
        box(f"room.{r['id']}", x0 + i, y0 + i, z, x1 - i, y1 - i, z + lift, col, [r["level"]])
        conf = "" if r.get("conf") in (None, "high") else f" ({r['conf']})"
        body = f"{r['id']}{conf}\n{fmt_ft(x1 - x0)} x {fmt_ft(y1 - y0)}"
        size = max(0.45, min(0.85, (x1 - x0) / 11))
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


def build_site():
    g = M["site"]["grade_z"]
    box("ground", -60, -50, g - 0.5, 90, 110, g, (0.62, 0.7, 0.55, 1), ["ground"])
    for ft in M["site"]["features"]:
        x0, y0, x1, y1 = ft["rect"]
        if ft["kind"] == "deck":
            box(f"feature.{ft['id']}", x0, y0, g, x1, y1, -0.6, SITE, ["site", "main"])
        else:
            box(f"feature.{ft['id']}", x0, y0, g, x1, y1, g + 0.33, SITE, ["site", "main"])
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
    build_stairs()
    build_roofs()
    build_site()
    bx0, by0, bx1, by1 = bounds()
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    north_arrow(bx1 + 1, by1 - 2, LEVEL_ORDER)
    for name in LEVEL_ORDER:
        text(f"title.{name}", f"{name.upper()} LEVEL   floor {fmt_ft(LEVELS[name]['floor_z'])}   cycle 1: +/-1 ft footprint, rooms +/-2 ft",
             cx, by1 + 4, LEVELS[name]["floor_z"] + 0.1, 1.0, INK, [f"label:{name}"])

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
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "house.blend"), compress=True)
    log(f"objects={len(bpy.data.objects)}")
    log("DONE")


main()
