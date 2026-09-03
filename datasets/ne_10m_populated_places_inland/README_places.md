# ne_10m_populated_places_inland

Natural Earth populated places with everything within **12 km of a port**
removed, and the attribute table cut down to ten useful fields.

```
6,537 points (from 7,342) | EPSG:4326 (WGS 84) | UTF-8 | 3.06 MB unpacked
```

## Where it comes from

**Natural Earth**, 10m Cultural Vectors — `ne_10m_populated_places`.

| | |
|---|---|
| Project | https://www.naturalearthdata.com |
| Dataset page | https://www.naturalearthdata.com/downloads/10m-cultural-vectors/ |
| Bundle downloaded | `https://naturalearth.s3.amazonaws.com/10m_cultural/10m_cultural.zip` |
| Also used | `ne_10m_ports` from the same bundle, as the exclusion source |

## Licence — free, no strings

Natural Earth data is in the **public domain**. No permission is required for
any use including commercial, and attribution is not required.
Terms: https://www.naturalearthdata.com/about/terms-of-use/

Both inputs are Natural Earth, so this derived layer carries no additional
restrictions. Redistribute it freely.

## Why places near ports are removed

On a maritime map the port layer is already labelled, and most major ports share
a name with the city beside them. Drawing both prints **"Thessaloniki"** twice,
a few millimetres apart.

This cannot be fixed with label settings. `spaceAround` and
`conflictResolution` suppress labels that *collide*; these two points are
genuinely kilometres apart, so their labels never overlap and the renderer is
behaving correctly. It is **semantic** duplication, so it is solved in the data:
coastal names come from the ports layer, inland names from this one.

**805 of the 7,342 places** fall within 12 km of a port and are dropped —
Piraeus, Volos, Thessaloniki, Bur Said, Dumyat, København, Malmö and so on.

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` — CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Type | Notes |
|---|---|---|
| `NAME` | String(100) | label text, UTF-8 |
| `NAMEASCII` | String(100) | ASCII fallback |
| `SCALERANK` | Integer | 0–10, see the warning below |
| `POP_MAX` | Integer64 | maximum population estimate |
| `ADM0NAME` | String(50) | country |
| `ADM1NAME` | String(100) | first-level admin area |
| `ISO_A2` | String(5) | country code |
| `FEATURECLA` | String(50) | place class |
| `LATITUDE` / `LONGITUDE` | Real | as shipped by Natural Earth |

### Why only ten fields

Natural Earth ships **137** fields on populated places — around a hundred of
them localised name variants (`NAME_BN`, `NAME_DE`, `NAME_EN`…) plus four
`C(254)` free-text columns. DBF is fixed-width, so every record pays for every
field whether or not it holds anything:

```
137 fields x 6,575 bytes/record x 6,537 records = 41.0 MB of attributes
                                       wrapped around 0.17 MB of geometry
```

Trimming to these ten takes the DBF to **2.76 MB** — a 93% cut with no effect on
rendering and a still-useful GetFeatureInfo response. If you need the full
attribute set, derive your own from `ne_10m_populated_places`.

## Read this before you style it

**`SCALERANK` is a cartographic hint, not a size ranking.** Zagazig (285k) is
rank 10 while Siwa (23k) is rank 6, and 514 places above 250k population sit at
rank 7 or worse — Katowice, Mannheim, Essen, Quezon City, Dammam.

Two consequences:

1. **Cover the whole 0–10 range.** Banding 0–3 and 4–6 and stopping there
   silently drops **4,583 of the 6,537 features** — 70% of the layer, invisible
   at every zoom, with no error to tell you.
2. **Rescue the mis-ranked ones on `POP_MAX`** if you want large cities to
   appear at the zoom their size deserves rather than the zoom their rank does.

Also: bands must not overlap. Every rule that matches a feature draws it, so
`SCALERANK <= n` tiers make a rank-1 city match five rules and print its label
five times. Use non-overlapping `BETWEEN` ranges.

## How it was built

```sh
# where = NOT within 12 km of any point in ne_10m_ports (built as an OGR
# -where clause from the port coordinates)
ogr2ogr -lco ENCODING=UTF-8 \
  -select NAME,NAMEASCII,SCALERANK,POP_MAX,ADM0NAME,ADM1NAME,ISO_A2,FEATURECLA,LATITUDE,LONGITUDE \
  -where "@_inland_where.txt" \
  ne_10m_populated_places_inland.shp ne_10m_populated_places.shp
```

`-lco ENCODING=UTF-8` is not optional: without it ogr2ogr writes ISO-8859-1 and
every non-ASCII place name comes back as mojibake (`KÃ¸benhavn`).
