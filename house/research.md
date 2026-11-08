# House research

_Public facts about the house. Every entry gets a source and a date retrieved. Provenance follows CLAUDE.md: `measured` > `imported` > `researched` > `inferred`._

**Sources**
- **[A] Polk County Assessor**: residential inventory export for Altoona, retrieved 2026-11-08. This house's row is saved as [imports/polk-assessor-record-2026-11-08.csv](imports/polk-assessor-record-2026-11-08.csv). Bulk file: https://web.assess.co.polk.ia.us/info/web/exports/res/inven/juris/AT.csv
- **[Z] Zillow listing** (from the 2022 sale), summarized via web search on 2026-11-08; direct fetch was blocked. https://www.zillow.com/homedetails/514-Village-Ct-Altoona-IA-50009/823732_zpid
- **[T] TopHap**: automated property summary, 2026-11-08. https://www.tophap.com/sitemap/usa/ia/polk/altoona/village-ct
- **[P] Polk County Assessor parcel page + building sketch**, read in a browser on 2026-11-08. Sketch vector and areas are transcribed in [imports/polk-assessor-sketch-2026-11-08.txt](imports/polk-assessor-sketch-2026-11-08.txt), with a [screenshot](imports/polk-assessor-sketch-2026-11-08-screenshot.jpg). Parcel page: https://www.assess.co.polk.ia.us/cgi-bin/web/tt/infoqry.cgi?tt=card/card&dp=17100178117000

## Identity & lot

| Fact | Value | Provenance | Source |
| :--- | :--- | :--- | :--- |
| Address | 514 Village Ct, Altoona, IA 50009-1251 | researched | A |
| Parcel (district / geo) | 171/00178-117-000 · 792313101060 | researched | A |
| Legal | Lot 17, Altoona Village Plat 3 | researched | A |
| Lot size | 10,846 sf (0.249 ac); frontage/depth not recorded | researched | A |
| Location (Iowa State Plane South, ft) | x 1645572.618, y 603236.337 | researched | A |
| Backs onto | Walking/biking trail, partly fenced yard | researched | Z |
| School district | Southeast Polk | researched | A |
| Last transfer | Deed 2022-09-02, Book 19252 Pg 160; sold $245,000 (Aug 2022) | researched | A, Z |
| Assessed value | Land $57,100 + building $201,900 = $259,000 | researched | A |

## Building

| Fact | Value | Provenance | Source |
| :--- | :--- | :--- | :--- |
| Year built | 1978 (no remodel year recorded) | researched | A, T |
| Style | Single family, split level, **4-level split** | researched | A, Z |
| Above-grade living area | 992 sf ("main"; upper recorded as 0) | researched | A |
| Basement area | 952 sf, of which 520 sf finished ("Living Quarters" quality) | researched | A |
| Walkout | No basement walkout recorded | researched | A |
| Foundation | Poured concrete | researched | A |
| Exterior wall | Hardboard siding, plus 152 sf of veneer | researched | A |
| Roof | Gable, asphalt shingle | researched | A |
| Bedrooms | 3 above grade, plus a non-conforming 4th in the basement | researched | A, Z |
| Bathrooms | ⚠ Assessor: 1 full bath, 0 toilet rooms. Zillow: 2 baths (a half bath near the family room) | conflict | A, Z |
| Rooms | 5 | researched | A |
| Fireplace | 1, in the family room | researched | A, Z |
| Heating / cooling | Electric forced air; 100% air-conditioned | researched | A |
| Garage | **Detached**, frame, 24 × 24 ft (576 sf), 2-car, built **1982** (added after the house), condition "Above Normal" | researched | A, P |
| Zoning | R-5 Planned Unit Development | researched | P |
| Lot shape | Irregular, normal topography | researched | P |
| Permits on file | 1 — 1995 "replace step" (applied 1994-05-09, complete). No remodel permit on record for the main-level update. | researched | P |
| Sale history | 2006 $154,730 · 2017 $171,500 · 2020 $200,000 · 2022 $245,000 | researched | P |
| Patio / canopy | 144 sf patio + 144 sf canopy (the covered patio off the dining sliders) | researched | A, Z |
| Deck | 30 sf (probably a stoop or landing) | researched | A |
| Radon | Mitigation system installed | researched | Z |
| Construction grade | 4+05; condition "Normal" | researched | A |

## Footprint from the assessor sketch [P]

Exterior dimensions in whole feet (assessor sketches round; treat as `imported`, ±6 in, until measured). North is not marked.

```
            12
         +------+
      12 |Canopy|          (1 ft strip, 20 sf, no basement)
         |Patio |    +--------------------+
         +------+----+                    |
         |    18     |        20          |
         |           |                    |
      24 |  West     |    East section    | 26
         |  section  |   20 x 26          |
         |  18 x 24  |                    |
         +-----------+--+-----------------+
                18   |Dk|   (1 ft strip, 20 sf, no basement)
                     +--+ 5 x 6 deck
```

- **Overall:** 38 ft wide. The west section is 18 × 24 (432 sf); the east section is 20 × 26 (520 sf), stepping out 1 ft past the west section on both long sides. Together: **952 sf, all over basement/lower levels.**
- **Main living area 992 sf = 952 + two 1 × 20 ft strips** with no basement under them (Basement% 0). They run along both long sides of the east section. Most likely reading (`inferred`, medium): the upper level of the split cantilevers about 1 ft past the walls below on the front and back. Verify on site: look for a floor overhang above the lower-level siding.
- **20 × 26 east section = 520 sf = the finished-basement figure.** Likely (`inferred`, medium) the east section is the upper/lower stack and the west 18 × 24 section is the main level over the basement or crawl.
- **Canopy/patio:** 12 × 12, off the 24 ft side of the west section (the covered patio off the dining sliders). **Deck:** 5 × 6, by the front, at the joint between the sections (likely the entry stoop, i.e. the 1995 "replace step" permit).

**Listing layout notes [Z]:** updated main level; sliding doors from the dining area to the covered patio; a family room with fireplace near the dining area; a half bath; a basement with the 4th bedroom, laundry and storage.

## Twin houses (same builder era, same footprint)

The Altoona Village plats contain 27 four-level splits built 1974–1980 [A]. These share this house's exact assessor footprint (992 sf main / 952 sf basement), so they very likely use the same plan, possibly mirrored:

| Address | Plat | Built | Finished bsmt | Baths (full/½) | Garage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **523 Village Ct** | Plat 3 | 1978 | 500 | 1 / 1 | GAR/576 |
| 607 14th Ave NW | Plat 3 | 1979 | 650 | 2 / 0 | GAR/624 |
| 547 14th Ave NW | Plat 5 | 1980 | 520 | 1 / 0 | GAR/528 |
| _near-twin:_ 507 Village Ct | Plat 3 | 1978 | 500 | 2 / 0 | GAR/484 + 264 |

**Use:** any old listing photos or floor plans for these addresses are a strong import source for room layout. Treat them as `imported` with "twin, may be mirrored" noted until confirmed against measurements.

## Era / builder priors

_What's typical for a 1978 Central-Iowa 4-level split. All of these are `inferred`; each says how to verify it._

| Prior | Confidence | Verify by |
| :--- | :--- | :--- |
| **Level stack:** main (living/kitchen/dining) over a crawl or the basement; upper (bedrooms + full bath) over the lower level; lower (family room + fireplace, half bath, garage access) roughly half below grade; basement (4th level: laundry, storage, 4th bedroom) below the lower level. | High | Walk-through interview |
| 2×4 stud walls at 16" on center; 1/2" drywall | High | Outlet-box cutout or attic top plate |
| **Roof framed with engineered trusses spanning the exterior walls.** If so, interior walls on the upper level usually carry no roof load. | Medium-high | Attic: look for W-shaped webs (trusses) vs. rafters plus a ridge board |
| **The wall where main meets upper/lower is structural.** It carries the upper floor's joists and the half-level offset. Do not remove it without an engineer. | High | Joist direction and bearing at the split |
| Main-level floor joists span to a central beam (steel or built-up wood) on posts in the basement/crawl. Interior main-level walls above that beam line are likely load-bearing. | Medium-high | Basement ceiling: beam line and joist direction |
| The kitchen/living partition on the main level often runs perpendicular to the joists (non-bearing) or sits on the beam line (bearing). It's 50/50 without looking. | Low | Basement beam line vs. wall position |
| Electrical: copper NM cable; 100–200 A service (an all-electric house often has 200 A). Aluminum branch wiring is unlikely after 1975. | Medium | Panel label; wire jacket printing |
| Plumbing: copper supply; PVC/ABS drains with possible cast-iron stack sections | Medium | Basement/utility room |
| **Hazard screening (pre-1980):** possible asbestos in vinyl floor tile or mastic, popcorn ceilings, joint compound and duct wrap. Lead paint possible: the ban took effect 1978, so pre-ban stock may have been used. | Medium | Test before demolition or sanding (cheap lab kits) |
| Fiberglass batt insulation; minimal wall insulation by modern standards | Medium | Outlet cover or attic |
| All-electric house: no gas line may exist, which affects a gas range or fireplace conversion | Medium | Gas meter present? Fireplace type (wood vs. gas)? |

## Open questions for the measurement interview

1. Bathrooms: is there a half bath (Zillow) or not (assessor)? Which level?
2. ~~Is the garage attached or detached?~~ Resolved: detached, 24 × 24, built 1982 [P]. Remaining: where is it relative to the house, and is it in scope for the model?
3. Is the house mirrored relative to 523 Village Ct? Which compass direction does the front face?
3a. Does the sketch reading hold: west 18 × 24 = main level, east 20 × 26 = upper/lower stack, with ~1 ft upper-level overhangs front and back?
4. What does the radon system run through? (pipe route constrains basement and lower-level changes)
5. Is the fireplace wood-burning, gas, or electric insert? Is there a gas meter?
6. Attic: trusses or rafters?
7. Which rooms make up the "updated main level"? When was it done, and was it permitted?

## Blueprint / floor plan leads

- **Twin listings:** search old MLS photos and floor plans for 523 Village Ct, 607 14th Ave NW, 547 14th Ave NW and 507 Village Ct (Zillow, Redfin, Realtor.com and homes.com history).
- **Polk County Assessor parcel page:** ✅ done; the sketch is captured above [P]. Twin parcels' sketches can be compared the same way to confirm the shared plan. The original sketch PNG can't be fetched by script (bot protection); to keep it, right-click the sketch on the page → Save image as… into `house/imports/`.
- **Zillow:** still blocked, even in a browser (bot check). Open it yourself to save listing photos into `house/imports/`.
- **City of Altoona building permits:** search by address for remodel permits (the main-level update) and possibly original plans.
- **The 2022 sale:** your closing or inspection documents may include an inspection report with photos, and possibly a radon report.
