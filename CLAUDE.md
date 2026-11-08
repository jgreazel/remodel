# remodel

Personal passion project. No monetization path beyond Jon & Madison; skip market/income prompts in this repo.

## P3

- **Person** — Jon & Madison (homeowners).
- **Problem** — They want construction and design consultation for their home while keeping full control of the process, instead of handing it to a hired professional.
- **Promise** — A Claude workflow that builds an accurate 3D model of their home in Blender, then maintains a portfolio of feasible renovation simulations, each with mockups, price and time estimates, and design recommendations (layout, furniture, feng shui).

## Value

Saves money and time: no paid contractor/designer consultations, and no time spent with humans until the options have been fully thought through.

## Current milestone

1. MVP house model in Blender: no materials, dimensions accurate to **±1 inch** of measured values. Verified by a top-down render with dimension labels, checked against `house/model.yaml`.
2. One full cycle (consultation → proposal) completed, with every intermediate artifact kept. The data is the architecture.

## Workflow

1. **Research** — Find everything public about the house (year built, square footage, lot, permits, listing photos, assessor records, builder/subdivision). Record findings with sources in `house/research.md`. Look for blueprints/floor plans as a potential import source.
2. **Measurement interview** — Interview Jon room by room for measurements, using research and imports to pre-fill and ask only for what's missing or uncertain. Write results to `house/model.yaml`.
3. **Build** — `blender/build_house.py` generates the scene from `house/model.yaml`. Verify against the tolerance above.
4. **Consultation** — Capture the goal for a project in `projects/<slug>/01-consultation.md`, grounded in `household/preferences.md`.
5. **Options** — Explore feasible variants in `02-options.md` (model diffs + renders).
6. **Proposal** — `03-proposal.md`: chosen design, mockups, estimate, design recommendations, open risks.
7. **Retro** — Write `retros/<date>-<slug>.md` and update the affected skills.

## Data rules

- `house/model.yaml` is the single source of truth for the house. The `.blend` file is a build output (committed via Git LFS) and is never edited by hand as the master copy.
- Renovation options are expressed as diffs/overlays against `house/model.yaml`, never as edits to the baseline.
- Tag every value with its provenance: `measured`, `imported` (blueprint/listing), `researched`, or `inferred`. Measured beats imported beats researched beats inferred. Never overwrite a `measured` value without asking.
- **Blueprints and floor plans are import sources, not core artifacts.** Keep originals in `house/imports/`. The workflow must work without them.
- **Era knowledge is a prior, not a fact.** Use what's typical for houses of this age, region, and builder (framing style, likely beam and bearing-wall locations, wiring/plumbing eras, likely hazards like asbestos or lead paint) to guide judgement. Record it as `inferred` with a confidence level, and say how to verify it on site (e.g. "check joist direction in the attic/basement").

## Safety guardrails

- Never present structural, electrical, plumbing, gas, HVAC, or permit decisions as final. Flag them as **needs licensed review** and explain why.
- Treat walls as potentially load-bearing until evidence says otherwise.
- Estimates are planning ranges (low / likely / high), not quotes. Cite source, date, and region for every cost figure. Refresh figures older than ~6 months before relying on them.

## Autonomous loops

Favor fully autonomous loops that hypothesize and iterate without human input for long stretches, and add new loops when a repeatable process is identified.

Every loop must define:
- **Goal** and **stop condition**: an iteration or time cap, plus "stop after N tries with no improvement."
- **Output location**: artifacts go in the repo, never only in chat.

Loops must **not**, without asking first:
- spend money or credits (e.g. Blender MCP `generate_3d`, paid APIs)
- make taste or priority decisions on Jon & Madison's behalf (propose options instead)
- overwrite or delete `measured` data or anything in `house/imports/`

## Skills

You are expected to create, maintain, and expand a library of project skills in `.claude/skills/`.
- **Trigger:** once a process has been done twice, turn it into a skill.
- **Cadence:** after each consultation → proposal cycle, write a retro and update the affected skills.
- Keep skills small and single-purpose. Note in the retro which skills were added or changed and why.

## Repo layout

```
household/preferences.md   # taste, budget, constraints, must-keeps
house/
  research.md              # public facts about the house, with sources
  model.yaml               # source of truth: rooms, walls, openings, units
  imports/                 # blueprints, listing photos, scans (originals)
blender/                   # build scripts; .blend outputs (LFS)
projects/<slug>/           # 01-consultation, 02-options, 03-proposal, renders/
retros/                    # what each cycle taught us
.claude/skills/            # project skills
infra/                     # IaC / scripts, if any infrastructure is ever needed
```

## Conventions

- Infrastructure lives in `infra/` as IaC or re-runnable scripts; manual steps go in `infra/README.md`.
- Binary assets (`.blend`, images, PDFs, scans) are tracked with Git LFS (see `.gitattributes`).
- Trunk-based development: short-lived branches, squash-merged to `main` for a clean history.
- Markdown files in the repo are the standard storage for deliverables and workflow handoffs.
- Units: imperial (feet/inches) unless stated otherwise; record units explicitly in `model.yaml`.
