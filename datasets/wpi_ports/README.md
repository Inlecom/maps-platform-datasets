# wpi_ports

NGA World Port Index ports, as points - live feed.

```
3,807 points | EPSG:4326 (WGS 84) | UTF-8
```

## Where it comes from

**National Geospatial-Intelligence Agency**, World Port Index (Pub 150).

| | |
|---|---|
| Publication page | https://msi.nga.mil/Publications/WPI |
| CSV downloaded | `https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv` |
| File | `UpdatedPub150.csv` |

Built by [scripts/wpi_ports/build.py](../../scripts/wpi_ports/build.py). Re-run
it any time to pick up NGA's latest edit to the live feed - there is no fixed
edition number to track, unlike the shapefile release this replaces.

## Licence - free, no strings

A work of the United States Government: **public domain**. No permission
required, commercial use included, attribution not required.

## This replaces the earlier build

The version of this dataset previously in this repo came from a 2017 ArcGIS
mirror of NGA's static shapefile release, cut down from 74 columns to 10. This
build instead reads NGA's live CSV export directly - the file behind the
"Download Updated CSV" option on the WPI Viewer, not the static shapefile/MDB
archive on the same page (those two are different exports of different vintages
that NGA maintains separately; the live CSV is the current one and the one with
cargo-type detail).

**Two NGA endpoints both claim to be "the" WPI API and disagree.** NGA also
publishes a documented query endpoint,
`/api/publications/world-port-index?output=csv`. It returns an older, smaller
export (2,951 rows at last check) with none of `UN/LOCODE`, `Alternate Port
Name`, `Harbor Use`, or the facility flags below - it was not used here for
exactly that reason.

## What's new here that the old build didn't have

- **`UN/LOCODE`** - lets this layer join to `unlocode_ports` and `upply_ports`
  directly by code, rather than by name and distance.
- **`Harbor Use`** - Fishing / Military / Cargo / Ferry / Unknown. This is the
  closest thing in any dataset in this repo to a port-type field.
- **Seven cargo-facility flags** - Container, Ro-Ro, Solid Bulk, Liquid Bulk,
  Breakbulk, Oil Terminal, LNG Terminal - each Yes/No/Unknown. This is the
  detail the previous build was missing entirely: `HARBORTYPE` (kept from
  before) describes the harbor's *geography* - coastal, river, canal,
  roadstead - not what it handles. These fields describe what it handles.
- **Real depths in metres**, not the WPI range-code letters (`J`, `K`, `L`...)
  the old build had to carry a warning about. `CHAN_DEPTH` and `CARGODEPTH` are
  the source's own metric values.
- **An alternate name** where the source gives one (867 of 3,807 rows).

## Read this before you use it

**Most facility flags are `Unknown`, not `No`.** NGA's coverage of the newer
facility questions is thin - `Facilities - Container` alone is `Unknown` on
roughly 85% of rows. `U` means *not asked/not answered*, not *absent*. Filter
on `= 'Y'` to find ports confirmed to have a facility; do not treat `!= 'Y'` as
confirmation they lack it.

**`Harbor Use` is mostly `Unknown` too** - populated on 9% of ports. Where
it is populated, it is the one real port-type signal in this repo:

| Harbor Use | Ports |
|---|---:|
| Unknown | 3,473 |
| Cargo | 290 |
| Fishing | 25 |
| Ferry | 11 |
| Military | 8 |

**Depth and vessel-size fields use `0.0` to mean "not recorded," not zero.**
Checked against `Facilities - Oil Terminal`: even where that flag is `Yes`,
`Oil Terminal Depth` is `0.0` on about 15% of those rows - a port cannot have
an oil terminal with zero draft. Storing `0.0` as given would silently read as
a real value. This build writes those fields blank instead:

| Field | Has a value | Source column |
|---|---:|---|
| `CHAN_DEPTH` | 3,169 / 3,807 | Channel Depth (m) |
| `CARGODEPTH` | 3,164 / 3,807 | Cargo Pier Depth (m) |
| `MAX_LOA` | 863 / 3,807 | Maximum Vessel Length (m) |
| `MAX_DRAFT` | 945 / 3,807 | Maximum Vessel Draft (m) |

**`LOCODE` is deliberately not unique, and that's different from the other two
port layers in this repo.** `unlocode_ports` and `upply_ports` merge to one
point per place. This dataset does not - NGA gives separate named rows to
distinct facilities that share one UN/LOCODE (a port and its offshore oil
terminal, for instance):

```
LOCODE = 'USVDZ'  NAME = 'Valdez'
LOCODE = 'USVDZ'  NAME = 'Valdez Marine Terminal'
```

28 codes cover more than one row this way. Group by `LOCODE` when you want
one row per UN/LOCODE place; use every row as-is when you want every named
facility.

**`WPI_NO` has 2 duplicate value(s) in NGA's own data - not fixed here.**
Unlike the `LOCODE` sharing above, these look like data-entry errors: the two
rows are unrelated places, not a port and one of its terminals.

| WPI_NO | Rows sharing it |
|---|---|
| 400 | Seydhisfjordhur / Seydisfjordur |
| 46135 | Escravos Oil Terminal / Lekki |

Neither row was dropped or renumbered - `WPI_NO` just isn't safe to treat as a
primary key until NGA fixes it upstream.

**`COUNTRY` is derived, not given.** The source's `Country Code` column is a
country *name* ("United States"), not an ISO code, unlike every other dataset
in this repo. `COUNTRY` is built by taking the first two letters of `UN/LOCODE`
from this release's own rows and majority-voting per country name -
189 of 195 names resolved this way. 6 names with no
UN/LOCODE evidence in this release (Gibraltar, Johnson Atoll, Midway Islands, Norfolk Island, Palau, Wake Island) fall back to a small
hardcoded table in the build script - correct as far as I could confirm, but
not verified against this release's own data the way the rest of the mapping
is.

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` - CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Type | Notes |
|---|---|---|
| `WPI_NO` | N(8) | World Port Index Number. Not globally unique - see above |
| `LOCODE` | C(5) | UN/LOCODE, blank when the source gives none. Not unique - see above |
| `NAME` | C(50) | Main Port Name |
| `ALT_NAME` | C(80) | Alternate Port Name, blank on most rows |
| `COUNTRY` | C(2) | ISO 3166-1 alpha-2, derived - see above |
| `CTRY_NAME` | C(50) | Country Code as the source gives it (a name, not a code) |
| `REGION` | C(50) | Region Name, with NGA's trailing internal id (`-- 6585`) stripped |
| `HARBORSIZE` | C(12) | Very Small / Small / Medium / Large |
| `HARBORTYPE` | C(24) | harbor construction/geography - see table below |
| `HARBORUSE` | C(10) | Fishing / Military / Cargo / Ferry / Unknown |
| `FAC_CONTAI` `FAC_RORO` `FAC_SOLIDB` `FAC_LIQUID` `FAC_BREAKB` `FAC_OILTER` `FAC_LNGTER` | C(1) | `Y`/`N`/`U`, see table below |
| `SHELTER` | C(10) | Excellent / Good / Fair / Poor / None / Unknown |
| `REPAIRS` | C(16) | Major / Moderate / Limited / Emergency Only / None / Unknown |
| `CHAN_DEPTH` | N(6,1) | Channel Depth, metres, blank if not recorded |
| `CARGODEPTH` | N(6,1) | Cargo Pier Depth, metres, blank if not recorded |
| `MAX_LOA` | N(6,1) | Maximum Vessel Length, metres, blank if not recorded |
| `MAX_DRAFT` | N(5,1) | Maximum Vessel Draft, metres, blank if not recorded |
| `LAT` `LON` | N(10,6) N(11,6) | decimal degrees, WGS 84, as published |

### Cargo-type facilities (the field this dataset was rebuilt to add)

| Field | Source column | Confirmed present (`Y`) |
|---|---|---:|
| `FAC_CONTAI` | Facilities - Container | 379 |
| `FAC_RORO` | Facilities - Ro-Ro | 399 |
| `FAC_SOLIDB` | Facilities - Solid Bulk | 533 |
| `FAC_LIQUID` | Facilities - Liquid Bulk | 490 |
| `FAC_BREAKB` | Facilities - Breakbulk | 632 |
| `FAC_OILTER` | Facilities - Oil Terminal | 143 |
| `FAC_LNGTER` | Facilities - LNG Terminal | 41 |

### Harbor Type - construction, not cargo type

| Harbor Type | Ports |
|---|---:|
| Coastal (Natural) | 1,252 |
| Coastal (Breakwater) | 793 |
| River (Natural) | 666 |
| Open Roadstead | 665 |
| (blank) | 179 |
| River (Basins) | 87 |
| Canal or Lake | 72 |
| River (Tide Gates) | 55 |
| Coastal (Tide Gates) | 34 |
| Typhoon Harbor | 4 |

## How it was built

```sh
python scripts/wpi_ports/build.py
```

Downloads the CSV into `downloaded/`, validates its column set (NGA has changed
this schema once already - the build fails loudly rather than silently if it
changes again), derives `COUNTRY` from `UN/LOCODE`, nulls out placeholder-zero
depth fields, and writes the shapefile with a dependency-free writer
([scripts/common/shapefile_writer.py](../../scripts/common/shapefile_writer.py)) -
this repo has no GDAL. Nothing is merged or deduplicated: every row NGA
publishes is written as its own point.
