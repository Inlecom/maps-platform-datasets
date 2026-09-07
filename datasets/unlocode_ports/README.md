# unlocode_ports

UN/LOCODE locations flagged as **ports**, as points.

```
11,725 points (from 17,524 port entries) | EPSG:4326 (WGS 84) | UTF-8
```

Every point has a coordinate that parses and falls in range, and no place
appears twice. See [What was left out](#what-was-left-out).

## Where it comes from

**UNECE / UN-CEFACT**, UN/LOCODE - the United Nations Code for Trade and
Transport Locations.

| | |
|---|---|
| Dataset page | https://unece.org/trade/cefact/UNLOCODE-Download |
| Bundle downloaded | `https://opensource.unicc.org/un/unece/uncefact/vocab-locode/-/jobs/artifacts/2025-1/download?job=package-release` |
| Archive | `unlocode-2025-1.zip` |

Built by [scripts/unlocode_ports/build.py](../../scripts/unlocode_ports/build.py).
Point it at another release with `--url`.

## Licence - free, no strings

UN/LOCODE is published by UNECE for free use, copying and redistribution,
commercial use included. Attribution to UNECE is expected. Terms are on the
dataset page above.

## What "port" means here

UN/LOCODE gives every location an 8-character **function classifier**. Position 1
is `1` when the location is a port *as defined in UN/CEFACT Recommendation 16* -
that is **any** port: seaport, river port, lake port, canal wharf. This is not a
seaport list. 8,171 of these points are also a rail, road, air, postal,
multimodal, fixed-transport or border-crossing location; the `FN_*` fields say
which.

## What was left out

17,524 port entries went in, 11,725 points came out.

| Dropped | Count | Why |
|---|---:|---|
| No coordinate | 5,757 | The source gives no position at all |
| Malformed coordinate | 35 | Minutes field reads 60 or higher |
| Same place, second code | 7 | Listed twice under two codes |

**5,757 entries (33%) carry no coordinate.** This is not a quality
signal: 3,896 of them (68%) are authority-approved entries, and the
largest groups are `AF` 2,092, `AI` 1,141, `RL` 1,101, `QQ` 677. If you need the complete code list, read the
source CSV; if you need those places on a map, geocode them elsewhere.

**35 entries carry a malformed coordinate** - the minutes field reads 60 or
higher, e.g. `3492S 13866E`. They look like decimal degrees typed into a
degrees-and-minutes field, but reading them that way drops several into the wrong
country or into open ocean, so they are discarded rather than guessed at.

**7 places are listed under two codes.** Two entries count as one place when
they share a country, share a diacritic-free name, and sit within 5 km of each
other. The better-sourced entry survives - authority-verified first, then the one
describing more transport functions, then the newer issue.

| Kept | Dropped | Place | Apart |
|---|---|---|---:|
| `GBGTN` | `GBCSN` | Garston | 0.0 km |
| `PLKRM` | `PLKMR` | Krynica Morska | 0.0 km |
| `FRNQU` | `FRNCB` | Le Conquet | 0.0 km |
| `FROS2` | `FRRHP` | Ouessant | 2.2 km |
| `MYPRA` | `MYRAI` | Perai | 0.0 km |
| `CNTZU` | `CNTZO` | Taizhou | 1.9 km |
| `US9AI` | `USWH7` | Waianae | 0.0 km |

Neither test alone would do. **Same coordinate is not duplication**: 333 points
share their position with another port, and they are mostly distinct towns
rounding into one cell at this list's 1.8 km precision - Fengkai, Huaiji and
Zhaoqing all land on 23.05N 112.45E. **Same name is not duplication either**:
79 same-country name pairs survive, and they are different places that happen to
share a name, two San Martins 724 km apart in Argentina among them.

The threshold sits in a gap the data itself draws. The widest pair merged here is
**2.2 km** apart; the closest same-name pair kept is **26 km** apart. Nothing
in this release falls between the two, so 5 km separates them cleanly.

`LOCODE` is unique in the output, and so is every country + name + position.

## Read this before you use it

**Coordinates are degrees and minutes only.** The source writes `4230N 00131E` -
no seconds. Every point is therefore good to roughly **1.8 km**, enough to place
a marker on a coastline, not enough to identify a berth. `COORD` keeps the raw
source string so you can see exactly what was given.

**In range is not the same as in the right place.** Every coordinate here parses
and falls inside the valid range, which is all that can be checked without
country boundaries to test against. A well-formed coordinate pointing at the
wrong town would survive.

**Status is not uniform.** 4,026 of 11,725 points carry a status
meaning a competent authority approved the entry. `VERIFIED = 'Y'` filters to
those; the rest are recognised locations, pending requests, or entries not
re-verified since the date shown.

**Renamed locations ship twice in the source.** A location whose name changed
appears once under the old name and once under the new, sharing one code. 76
such pairs were collapsed to the newest issue.

**Do not stack this over another port layer without deduplicating.** It overlaps
heavily with `wpi_ports` and `ne_10m_ports_dedup`, and these are UN
romanisations, so a naive name join will miss matches.

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` - CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Type | Notes |
|---|---|---|
| `LOCODE` | C(5) | country + location code, e.g. `NLRTM`. Unique |
| `COUNTRY` | C(2) | ISO 3166-1 alpha-2 |
| `LOCATION` | C(3) | the 3-character location part |
| `CTRY_NAME` | C(50) | country name as given in the code list |
| `NAME` | C(70) | location name with diacritics, UTF-8 |
| `NAME_ASCII` | C(70) | the source's own diacritic-free spelling of `NAME` |
| `SUBDIV` | C(3) | ISO 3166-2 subdivision code |
| `SUBDIV_NM` | C(80) | resolved from `SubdivisionCodes.csv` (9,580 of 11,725) |
| `FUNCTION` | C(8) | raw 8-position classifier |
| `FN_RAIL` `FN_ROAD` `FN_AIR` `FN_POST` `FN_MULTI` `FN_FIXED` `FN_BORDER` | C(1) | `Y`/`N`, decoded from `FUNCTION`. There is no `FN_PORT` - it is `Y` on every row |
| `STATUS` | C(2) | see the table below |
| `VERIFIED` | C(1) | `Y` when `STATUS` is one of `AA AC AF AI AM AS` |
| `DATE` | C(4) | `YYMM` of the issue that last touched the entry |
| `IATA` | C(3) | IATA code, present only when it differs from `LOCATION` |
| `CH` | C(2) | change indicator: blank unchanged, `+` added, `#` name changed, `X` to be removed, `¦` otherwise changed |
| `REMARKS` | C(50) | as shipped |
| `COORD` | C(12) | raw source coordinate, `4230N 00131E` |
| `LAT` `LON` | N(10,6) N(11,6) | decimal degrees parsed from `COORD` |

### Status codes present

Counted over all 17,524 port entries, including those with no usable position.

| Code | Meaning | Port entries |
|---|---|---:|
| `RL` | Recognised location, confirmed by a non-government source | 8,207 |
| `AF` | Approved by national facilitation body | 2,907 |
| `AA` | Approved by competent national government agency | 2,060 |
| `AI` | Code adopted by international organisation (IATA/ECLAC) | 1,967 |
| `QQ` | Original entry not verified since the date indicated | 690 |
| `RN` | Request from a credible national source | 673 |
| `AS` | Approved by national standardisation body | 661 |
| `AC` | Approved by Customs Authority | 291 |
| `AM` | Approved by the UN/LOCODE Maintenance Agency | 38 |
| `AQ` | Entry approved, functions not verified | 19 |
| (blank) | not documented in the release | 7 |
| `UR` | Included on a user request, not officially approved | 4 |

## How it was built

```sh
python scripts/unlocode_ports/build.py
```

Downloads the release zip into `downloaded/`, reads the code-list CSVs, keeps
function position 1 = `1`, collapses renamed entries, converts degrees and
minutes to decimal degrees, drops everything without a usable position, merges
places listed under two codes, and writes the shapefile with a dependency-free
writer ([scripts/common/shapefile_writer.py](../../scripts/common/shapefile_writer.py)) -
this repo has no GDAL. `.cpg` says `UTF-8` and the attribute bytes are UTF-8 to
match, so non-ASCII names survive.
