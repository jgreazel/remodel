# House as code

The house is data. `house/model.yaml` is the desired state; Blender output is a build artifact. Nothing in `blender/out/` is edited by hand.

```
house/model.yaml ──┐
                   ├─► validate ─► plan ─► apply ─► blender/out/   (baseline)
overlay.yaml ──────┘                                <overlay dir>/renders/<name>/   (project option)
```

| Command | What it does |
| :--- | :--- |
| `python blender/pipeline.py validate` | Schema, provenance rules (`prov`, `conf` on inferred), geometry sanity (rects, rooms inside footprints, overlaps, openings on real walls), and the model's own `checks:` (e.g. footprint areas vs. assessor). |
| `python blender/pipeline.py plan` | Validate, then diff every resource (`room.kitchen_dining`, `stair.main_to_upper`, …) against `state.json` from the last apply: `+` add, `~` change, `-` destroy. |
| `python blender/pipeline.py apply` | Validate + plan, then build headless in Blender (`build_house.py`), render, and write `verify.md` and `state.json`. Rebuilds from scratch every time. |

Add `--overlay projects/<slug>/<option>.yaml` to any command to run it on a renovation option instead of the baseline.

## Outputs (`blender/out/`)

- `plan-1-basement.png` … `plan-4-upper.png`: top-down plan per level, with exterior dimensions (red), room names and sizes, confidence, stair directions and a north arrow.
- `exterior-front-left.png`: massing view with roofs, patio, stoop and garage.
- `house.blend`: the built scene (1 Blender unit = 1 ft, imperial units display). Open it to look around, but never save edits back as the master copy.
- `verify.md`: check results plus a dimension table for every level and room, to compare against the renders.
- `state.json`: model hash, Blender version, outputs, and per-resource digests that `plan` diffs against.

## Overlays (renovation options)

An overlay uses the same schema as `model.yaml` and only lists what changes. List entries merge by `id`; `remove: true` deletes one.

```yaml
overlay: {name: open-kitchen, parent: house/model.yaml, description: "Remove the living/kitchen partition"}
rooms:
  - {id: living_room, remove: true}
  - {id: kitchen_dining, rect: [0.5, 0.5, 17.5, 23.5], prov: inferred, conf: low, tol: 2, src: "option A"}
```

`plan --overlay` then reads as the change list for that option.

## Requirements

- Python 3.10+ with PyYAML: `python -m pip install pyyaml`
- Blender 4.2+. Found via `--blender`, `$BLENDER`, `PATH`, or `C:\Program Files\Blender Foundation\Blender *`. Built and checked with 5.2.3 LTS.

## Model conventions

- Coordinates: origin at the front-left exterior corner of the main section at main floor level. +x runs along the front toward the two-story section, +y runs front to back, +z is up. Rectangles are `[x0, y0, x1, y1]` in feet.
- Every geometric entry carries `prov` and `tol`; inferred entries also carry `conf`. Plan labels show the confidence so guesses are never mistaken for measurements.
