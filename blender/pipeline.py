"""House-as-code pipeline: model.yaml (+ optional overlay) -> validate -> plan -> apply.

    python blender/pipeline.py validate [--overlay projects/<slug>/<option>.yaml]
    python blender/pipeline.py plan     [--overlay ...]
    python blender/pipeline.py apply    [--overlay ...] [--blender PATH]

validate  schema + provenance rules + geometry sanity + the model's own `checks:`
plan      validate, then diff the resolved resources against the last applied state
apply     validate, run Blender headless (build_house.py), write renders, .blend, verify.md, state.json

The baseline builds to blender/out/. An overlay builds to <overlay dir>/renders/<overlay name>/.
Overlays use the model's own schema; list entries merge by `id`, and `remove: true` deletes one.
Requires: Python 3.10+, PyYAML, Blender 4.2+ (found via --blender, $BLENDER, PATH or Program Files).
"""
from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_MODEL = ROOT / "house" / "model.yaml"
BUILDER = ROOT / "blender" / "build_house.py"
PROVENANCE = {"measured", "imported", "researched", "inferred"}
LIST_SECTIONS = ("rooms", "stairs", "openings", "roofs", "walls", "finishes", "fixtures", "checks")
BEARING = {"likely", "unknown", "unlikely", "no"}
FIXTURE_KINDS = {"ceiling_fan", "flush", "pendant", "lantern", "chandelier", "track", "recessed", "vanity_bar",
                 "light_bar", "panel", "shop_light", "sconce"}


# ---------- load + overlay ----------

def merge_by_id(base: list, over: list) -> list:
    out = {e["id"]: copy.deepcopy(e) for e in base}
    order = [e["id"] for e in base]
    for e in over:
        if e.get("remove"):
            out.pop(e["id"], None)
            continue
        if e["id"] in out:
            out[e["id"]].update(e)
        else:
            out[e["id"]] = copy.deepcopy(e)
            order.append(e["id"])
    return [out[i] for i in order if i in out]


def deep_merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        res = copy.deepcopy(base)
        for k, v in over.items():
            res[k] = deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return res
    if isinstance(base, list) and isinstance(over, list) and all(isinstance(e, dict) and "id" in e for e in base + over):
        return merge_by_id(base, over)
    return copy.deepcopy(over)


def load(overlay: Path | None) -> dict:
    model = yaml.safe_load(BASE_MODEL.read_text(encoding="utf-8"))
    if overlay:
        ov = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
        ov.pop("overlay", None)  # metadata block (name, description, parent) is not geometry
        model = deep_merge(model, ov)
    return model


# ---------- resolve: strip provenance wrappers into plain build inputs ----------

def val(entry):
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


def finish_of(m: dict, room_id: str) -> dict:
    return next((f for f in m.get("finishes", []) if f["id"] == room_id), {})


def resolve(m: dict) -> dict:
    site = m.get("site", {})
    return {
        "units": m["units"],
        "defaults": {k: val(v) for k, v in m.get("defaults", {}).items()},
        "levels": {
            name: {"rect": lv["footprint"]["rect"], "floor_z": val(lv["floor_z"]),
                   "ceiling_height": val(lv["ceiling_height"])}
            for name, lv in m["levels"].items()
        },
        "rooms": [{**r, "finish": finish_of(m, r["id"])} for r in m.get("rooms", [])],
        "stairs": m.get("stairs", []),
        "openings": m.get("openings", []),
        "roofs": m.get("roofs", []),
        "walls": m.get("walls", []),
        "fixtures": m.get("fixtures", []),
        "site": {
            "grade_z": val(site.get("grade_z", 0)),
            "front_bearing_deg": val(site.get("front_bearing_deg")),
            "features": site.get("features", []),
            "outbuildings": site.get("outbuildings", []),
            "landscape": site.get("landscape", []),
            "plants": site.get("plants", []),
        },
    }


def resources(m: dict) -> dict[str, dict]:
    """Flat id -> definition map, the unit that plan diffs (like Terraform resource addresses)."""
    res = {f"level.{k}": v for k, v in m["levels"].items()}
    for sec in ("rooms", "stairs", "openings", "roofs", "walls", "fixtures"):
        res.update({f"{sec[:-1]}.{e['id']}": e for e in m.get(sec, [])})
    res.update({f"finish.{e['id']}": e for e in m.get("finishes", [])})
    site = m.get("site", {})
    res.update({f"feature.{e['id']}": e for e in site.get("features", [])})
    res.update({f"outbuilding.{e['id']}": e for e in site.get("outbuildings", [])})
    res.update({f"landscape.{e['id']}": e for e in site.get("landscape", [])})
    res.update({f"plant.{e['id']}": e for e in site.get("plants", [])})
    for k in ("grade_z", "front_bearing_deg", "driveway_side"):
        if k in site:
            res[f"site.{k}"] = site[k]
    res.update({f"default.{k}": v for k, v in m.get("defaults", {}).items()})
    return res


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


# ---------- validate ----------

def rect_ok(r) -> bool:
    return isinstance(r, list) and len(r) == 4 and r[0] < r[2] and r[1] < r[3]


def inside(inner, outer, eps=1e-6) -> bool:
    return inner[0] >= outer[0] - eps and inner[1] >= outer[1] - eps and inner[2] <= outer[2] + eps and inner[3] <= outer[3] + eps


def overlap_area(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def area(r) -> float:
    return (r[2] - r[0]) * (r[3] - r[1])


def room_parts(r) -> list:
    """A room is one rect, or `parts`: a list of non-overlapping rects (L-shapes etc.)."""
    return r.get("parts") or ([r["rect"]] if "rect" in r else [])


def room_area(r) -> float:
    return sum(area(p) for p in room_parts(r))


def shared_edge(a, b) -> float:
    if abs(a[2] - b[0]) < 1e-6 or abs(b[2] - a[0]) < 1e-6:
        return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    if abs(a[3] - b[1]) < 1e-6 or abs(b[3] - a[1]) < 1e-6:
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return 0.0


def room_perimeter(r) -> float:
    ps = room_parts(r)
    per = sum(2 * (p[2] - p[0] + p[3] - p[1]) for p in ps)
    return per - 2 * sum(shared_edge(a, b) for i, a in enumerate(ps) for b in ps[i + 1:])


def wall_len(w) -> float:
    return abs(w["to"][0] - w["from"][0]) + abs(w["to"][1] - w["from"][1])


def in_rect(pt, r, eps=1e-6) -> bool:
    return r[0] - eps <= pt[0] <= r[2] + eps and r[1] - eps <= pt[1] <= r[3] + eps


def validate(m: dict) -> tuple[list[str], list[str], list[str]]:
    errors, warnings, passed = [], [], []

    def prov_rule(where, e):
        p = e.get("prov")
        if p is None:
            return
        if p not in PROVENANCE:
            errors.append(f"{where}: prov '{p}' not in {sorted(PROVENANCE)}")
        if p == "inferred" and "conf" not in e:
            errors.append(f"{where}: inferred value needs conf")

    for k in ("units", "levels"):
        if k not in m:
            errors.append(f"missing top-level '{k}'")
    if errors:
        return errors, warnings, passed
    if m["units"] != "ft":
        errors.append("units must be 'ft' (builder assumes feet)")

    levels = m["levels"]
    for name, lv in levels.items():
        for k in ("footprint", "floor_z", "ceiling_height"):
            if k not in lv:
                errors.append(f"level.{name}: missing {k}")
            else:
                prov_rule(f"level.{name}.{k}", lv[k])
        if "footprint" in lv and not rect_ok(lv["footprint"].get("rect")):
            errors.append(f"level.{name}: bad footprint rect")

    seen = set()
    for sec in ("rooms", "stairs", "openings", "roofs", "walls", "fixtures"):
        for e in m.get(sec, []):
            addr = f"{sec[:-1]}.{e.get('id')}"
            if "id" not in e:
                errors.append(f"{sec}: entry without id")
                continue
            if addr in seen:
                errors.append(f"{addr}: duplicate id")
            seen.add(addr)
            if "prov" not in e:
                errors.append(f"{addr}: missing prov")
            prov_rule(addr, e)
            for lk in ("level", "from", "to", "over"):
                if lk in e and isinstance(e[lk], str) and e[lk] not in levels:
                    errors.append(f"{addr}: unknown level '{e[lk]}'")
            if "rect" in e and not rect_ok(e["rect"]):
                errors.append(f"{addr}: bad rect {e['rect']}")

    for r in m.get("rooms", []):
        lv = levels.get(r.get("level"))
        parts = room_parts(r)
        if not parts:
            errors.append(f"room.{r['id']}: needs rect or parts")
        for p in parts:
            if not rect_ok(p):
                errors.append(f"room.{r['id']}: bad part {p}")
            elif lv and not inside(p, lv["footprint"]["rect"]):
                errors.append(f"room.{r['id']}: {p} outside {r['level']} footprint {lv['footprint']['rect']}")

    room_ids = {r["id"] for r in m.get("rooms", [])}
    for fin in m.get("finishes", []):
        addr = f"finish.{fin['id']}"
        if fin["id"] not in room_ids:
            errors.append(f"{addr}: no room with that id")
        if "floor" in fin and "material" not in fin["floor"]:
            errors.append(f"{addr}.floor: needs material")
        for k in ("floor", "ceiling", "walls", "trim"):
            f = fin.get(k)
            if isinstance(f, dict):
                if "prov" not in f:
                    errors.append(f"{addr}.{k}: missing prov")
                prov_rule(f"{addr}.{k}", f)

    rooms = m.get("rooms", [])
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a.get("level") != b.get("level") or a.get("finished") is False or b.get("finished") is False:
                continue
            ov = sum(overlap_area(p, q) for p in room_parts(a) for q in room_parts(b))
            if ov > 0.01:
                warnings.append(f"room.{a['id']} overlaps room.{b['id']} by {ov:.1f} sf")

    for w in m.get("walls", []):
        addr = f"wall.{w['id']}"
        lv = levels.get(w.get("level"))
        a, b = w.get("from"), w.get("to")
        if not (isinstance(a, list) and isinstance(b, list) and len(a) == 2 and len(b) == 2):
            errors.append(f"{addr}: needs from/to [x, y]")
            continue
        if (a[0] != b[0]) == (a[1] != b[1]):
            errors.append(f"{addr}: walls must be axis-aligned and non-zero length")
            continue
        if lv and not (in_rect(a, lv["footprint"]["rect"]) and in_rect(b, lv["footprint"]["rect"])):
            errors.append(f"{addr}: endpoint outside {w['level']} footprint")
        if w.get("bearing") not in BEARING:
            errors.append(f"{addr}: bearing must be one of {sorted(BEARING)}")
        axis = 0 if a[1] == b[1] else 1
        lo, hi = sorted((a[axis], b[axis]))
        for d in w.get("doors", []):
            s, e = d["span"]
            if not (lo <= s < e <= hi):
                errors.append(f"{addr}: door {d.get('id')} span {d['span']} not within wall ({lo}..{hi})")

    room_by_id = {r["id"]: r for r in rooms}
    for f in m.get("fixtures", []):
        addr = f"fixture.{f['id']}"
        r = room_by_id.get(f.get("room"))
        if r is None:
            errors.append(f"{addr}: unknown room '{f.get('room')}'")
        elif not any(in_rect(f.get("at", [1e9, 1e9]), p) for p in room_parts(r)):
            errors.append(f"{addr}: at {f.get('at')} not inside room.{r['id']}")
        if f.get("kind") not in FIXTURE_KINDS:
            errors.append(f"{addr}: kind '{f.get('kind')}' not in {sorted(FIXTURE_KINDS)}")

    for o in m.get("openings", []):
        lv = levels.get(o.get("level"))
        if not lv:
            continue
        r = lv["footprint"]["rect"]
        lo, hi = (r[0], r[2]) if o["wall"] in ("front", "back") else (r[1], r[3])
        s0, s1 = o["span"]
        if not (lo <= s0 < s1 <= hi):
            errors.append(f"opening.{o['id']}: span {o['span']} not on {o['level']} {o['wall']} wall ({lo}..{hi})")
        if o["head"] > val(lv["ceiling_height"]):
            errors.append(f"opening.{o['id']}: head above ceiling")

    site = m.get("site", {})
    for sec in ("features", "outbuildings", "landscape", "plants"):
        for e in site.get(sec, []):
            addr = f"site.{sec}.{e.get('id')}"
            if "prov" not in e:
                errors.append(f"{addr}: missing prov")
            prov_rule(addr, e)
            if "rect" in e and not rect_ok(e["rect"]):
                errors.append(f"{addr}: bad rect {e['rect']}")
            if "poly" in e and (len(e["poly"]) < 3 or any(len(p) != 2 for p in e["poly"])):
                errors.append(f"{addr}: poly needs 3+ [x, y] points")
            if sec in ("features", "outbuildings", "landscape") and not ("rect" in e or "poly" in e):
                errors.append(f"{addr}: needs rect or poly")
            if sec == "plants" and not ("at" in e and "dia" in e and "height" in e):
                errors.append(f"{addr}: plant needs at, dia, height")

    for o in m.get("openings", []):
        if "bay" in o and (o["wall"] not in ("front", "back") or o["bay"].get("depth", 0) <= 0):
            errors.append(f"opening.{o['id']}: bay needs front/back wall and depth > 0")

    for c in m.get("checks", []):
        if c["kind"] == "footprint_area_sum":
            got = sum(area(levels[l]["footprint"]["rect"]) for l in c["levels"])
            msg = f"check.{c['id']}: {'+'.join(c['levels'])} = {got:.0f} sf (expect {c['expect_sf']} ±{c['tol_sf']})"
            (passed if abs(got - c["expect_sf"]) <= c["tol_sf"] else errors).append(msg)
        else:
            errors.append(f"check.{c['id']}: unknown kind {c['kind']}")

    return errors, warnings, passed


# ---------- state + plan ----------

def out_dir_for(overlay: Path | None) -> Path:
    return overlay.parent / "renders" / overlay.stem if overlay else ROOT / "blender" / "out"


def read_state(out: Path) -> dict:
    p = out / "state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"resources": {}}


def plan(m: dict, out: Path) -> dict[str, list[str]]:
    old = read_state(out)["resources"]
    new = {k: digest(v) for k, v in resources(m).items()}
    return {
        "add": sorted(k for k in new if k not in old),
        "change": sorted(k for k in new if k in old and old[k] != new[k]),
        "destroy": sorted(k for k in old if k not in new),
    }


def print_plan(p: dict) -> None:
    for sym, key in (("+", "add"), ("~", "change"), ("-", "destroy")):
        for k in p[key]:
            print(f"  {sym} {k}")
    n = sum(len(v) for v in p.values())
    print(f"Plan: {len(p['add'])} to add, {len(p['change'])} to change, {len(p['destroy'])} to destroy."
          if n else "No changes. The build matches the model.")


# ---------- apply ----------

def find_blender(explicit: str | None) -> str:
    for cand in (explicit, os.environ.get("BLENDER"), shutil.which("blender")):
        if cand and Path(cand).exists():
            return cand
    hits = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"))
    if hits:
        return hits[-1]
    sys.exit("Blender not found: pass --blender PATH or set $BLENDER")


def fmt_ft(v: float) -> str:
    n = round(abs(v) * 12)
    return f"{'-' if v < 0 else ''}{n // 12}'-{n % 12}\""


def write_verify(m: dict, out: Path, errors, warnings, passed, model_hash) -> None:
    lines = [
        "# Build verification",
        "",
        f"Model hash `{model_hash}` · built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Generated by `blender/pipeline.py apply`. Compare each plan render's labels with these rows.",
        "",
        "## Checks",
        "",
        *[f"- ✅ {p}" for p in passed],
        *[f"- ⚠️ {w}" for w in warnings],
        *[f"- ❌ {e}" for e in errors],
        "",
        "## Levels",
        "",
        "| Level | Footprint (W × D) | Area | Floor z | Ceiling | Tol | Prov |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ]
    for name, lv in m["levels"].items():
        r = lv["footprint"]["rect"]
        lines.append(f"| {name} | {fmt_ft(r[2]-r[0])} × {fmt_ft(r[3]-r[1])} | {area(r):.0f} sf | "
                     f"{fmt_ft(val(lv['floor_z']))} | {fmt_ft(val(lv['ceiling_height']))} | "
                     f"±{lv['footprint'].get('tol', '?')} ft | {lv['footprint'].get('prov')} |")
    lines += ["", "## Rooms", "",
              "| Room | Level | W × D | Area | Tol | Prov / conf |",
              "| :--- | :--- | :--- | ---: | ---: | :--- |"]
    for r in m.get("rooms", []):
        ps = room_parts(r)
        dims = " + ".join(f"{fmt_ft(x[2]-x[0])} × {fmt_ft(x[3]-x[1])}" for x in ps)
        lines.append(f"| {r['id']} | {r['level']} | {dims} | {room_area(r):.0f} sf | "
                     f"±{r.get('tol', '?')} ft | {r.get('prov')}{' / ' + r['conf'] if 'conf' in r else ''} |")

    # Quantities that drive estimates: floor area per finish, and baseboard run (perimeter less door widths).
    door_w = {}
    for w in m.get("walls", []):
        for d in w.get("doors", []):
            for rid in d.get("rooms", []):
                door_w[rid] = door_w.get(rid, 0) + d["span"][1] - d["span"][0]
    lines += ["", "## Finishes and quantities", "",
              "Baseboard = room perimeter minus modeled interior doors (exterior doors and openings not yet subtracted). ±room tol.",
              "",
              "| Room | Floor | Area | Baseboard | Ceiling | Condition / notes |",
              "| :--- | :--- | ---: | ---: | :--- | :--- |"]
    for r in m.get("rooms", []):
        f = finish_of(m, r["id"])
        fl, ce, tr = f.get("floor") or {}, f.get("ceiling") or {}, f.get("trim") or {}
        base = "none" if tr.get("baseboard") == "none" else f"{max(0.0, room_perimeter(r) - door_w.get(r['id'], 0)):.0f} lf"
        lines.append(f"| {r['id']} | {fl.get('material', '?')} | {room_area(r):.0f} sf | {base} | "
                     f"{ce.get('texture', '?')} | {fl.get('condition', '')} |")

    lines += ["", "## Interior walls", "",
              "Bearing status is a planning prior, never a decision: anything but `no` **needs licensed review** before removal.",
              "",
              "| Wall | Level | Length | Bearing | Doors | Basis |",
              "| :--- | :--- | ---: | :--- | :--- | :--- |"]
    for w in m.get("walls", []):
        doors = ", ".join(f"{d['id']} ({d.get('kind', 'door')})" for d in w.get("doors", [])) or "-"
        lines.append(f"| {w['id']} | {w['level']} | {fmt_ft(wall_len(w))} | {w['bearing']} | {doors} | {w.get('bearing_basis', w.get('src', ''))} |")

    lines += ["", "## Lighting", "", "| Fixture | Room | Kind | Mount |", "| :--- | :--- | :--- | :--- |"]
    for fx in m.get("fixtures", []):
        lines.append(f"| {fx['id']} | {fx['room']} | {fx['kind']} | {fx.get('mount', 'ceiling')} |")
    (out / "verify.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply(m: dict, out: Path, overlay: Path | None, blender: str, errors, warnings, passed) -> None:
    out.mkdir(parents=True, exist_ok=True)
    resolved = resolve(m)
    model_hash = digest(m)
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "resolved.json"
        rp.write_text(json.dumps(resolved), encoding="utf-8")
        cmd = [blender, "--background", "--factory-startup", "--python", str(BUILDER), "--", str(rp), str(out)]
        print("$", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        log = [l for l in proc.stdout.splitlines() if l.startswith("[build]")]
        print("\n".join(log))
        if proc.returncode != 0 or not any("DONE" in l for l in log):
            print(proc.stdout[-4000:], proc.stderr[-4000:], sep="\n")
            sys.exit("apply failed: Blender build did not finish")
    write_verify(m, out, errors, warnings, passed, model_hash)
    state = {
        "model": str(BASE_MODEL.relative_to(ROOT)),
        "overlay": str(overlay.relative_to(ROOT)) if overlay else None,
        "model_hash": model_hash,
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "blender": next((l.split("blender=", 1)[1] for l in log if "blender=" in l), None),
        "outputs": sorted(p.name for p in out.iterdir() if p.name != "state.json"),
        "resources": {k: digest(v) for k, v in resources(m).items()},
    }
    (out / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Apply complete. Outputs in {out.relative_to(ROOT)}")


# ---------- cli ----------

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["validate", "plan", "apply"])
    ap.add_argument("--overlay", type=Path, help="project option overlay YAML")
    ap.add_argument("--blender", help="path to blender executable")
    a = ap.parse_args()
    overlay = a.overlay.resolve() if a.overlay else None

    m = load(overlay)
    errors, warnings, passed = validate(m)
    for p in passed:
        print(f"ok    {p}")
    for w in warnings:
        print(f"warn  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        sys.exit(f"validate failed: {len(errors)} error(s)")
    print(f"Validate: OK ({len(warnings)} warning(s))")
    if a.command == "validate":
        return

    out = out_dir_for(overlay)
    p = plan(m, out)
    print_plan(p)
    if a.command == "apply":
        apply(m, out, overlay, find_blender(a.blender), errors, warnings, passed)


if __name__ == "__main__":
    main()
