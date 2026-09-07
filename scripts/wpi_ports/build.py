#!/usr/bin/env python3
"""Build the `wpi_ports` GeoServer dataset from NGA's live World Port Index feed.

Downloads UpdatedPub150.csv - the CSV export behind the modern NGA WPI Viewer
(https://msi.nga.mil/Publications/WPI), which carries UN/LOCODE, an alternate
name, Harbor Use, and per-cargo-type facility flags (Container, Solid Bulk,
Liquid Bulk, Breakbulk, Ro-Ro, Oil Terminal, LNG Terminal) - none of which exist
in the static 2019 shapefile release this repo shipped before. Writes a zipped
ESRI Shapefile shaped like the other datasets in this repo.

    python scripts/wpi_ports/build.py
    python scripts/wpi_ports/build.py --url https://.../UpdatedPub150.csv
    python scripts/wpi_ports/build.py --force        # re-download
    python scripts/wpi_ports/build.py --source downloaded/UpdatedPub150.csv

Standard library only - no GDAL, no geopandas.

Note on sourcing: NGA also serves a documented query API at
/api/publications/world-port-index?output=csv (see /api/v3/api-docs). That
endpoint returns a smaller, older-schema export (2,951 rows, no UN/LOCODE, no
Harbor Use, no facility flags) that predates this one - it is not a substitute.
UpdatedPub150.csv is not listed in NGA's own stored-publication catalog
(/api/publications/stored-pubs) either; it is served fresh on every request
(confirmed via response headers - no Last-Modified/ETag, but Content-Disposition
consistently names it and the CDN reports a cache HIT with a ~8h max-age), which
is why this script re-downloads by default rather than trusting a long-lived cache.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.download import decode, fetch  # noqa: E402
from common.shapefile_writer import Field, write_point_shapefile  # noqa: E402

DEFAULT_URL = (
    "https://msi.nga.mil/api/publications/download"
    "?type=view&key=16920959/SFH00000/UpdatedPub150.csv"
)
SOURCE_FILENAME = "UpdatedPub150.csv"
DATASET_PAGE = "https://msi.nga.mil/Publications/WPI"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = "wpi_ports"
LAYER_NAME = "wpi_ports"

REQUIRED_COLUMNS = (
    "World Port Index Number", "Main Port Name", "Alternate Port Name", "UN/LOCODE",
    "Country Code", "Region Name", "Latitude", "Longitude",
    "Harbor Size", "Harbor Type", "Harbor Use", "Shelter Afforded", "Repairs",
    "Channel Depth (m)", "Cargo Pier Depth (m)",
    "Maximum Vessel Length (m)", "Maximum Vessel Draft (m)",
    "Facilities - Ro-Ro", "Facilities - Solid Bulk", "Facilities - Liquid Bulk",
    "Facilities - Container", "Facilities - Breakbulk",
    "Facilities - Oil Terminal", "Facilities - LNG Terminal",
)

# Country Code in this feed is a full name ("United States"), not ISO 3166-1
# alpha-2 like every other dataset in this repo. There are exactly 195 distinct
# names in a given release; this build derives the alpha-2 for each from the
# UN/LOCODE column of that release's own rows (the first two letters of a
# location's UN/LOCODE are its ISO country code), by majority vote across all
# rows sharing that name. That resolves ~97% of names outright.
#
# A handful of names have zero UN/LOCODE evidence in any release seen so far -
# small territories where none of their ports carry a UN/LOCODE. Those fall back
# to this table. It is NOT verified against this release's own data the way the
# rest of the mapping is - check FALLBACK_COUNTRY_ISO2 usage in the build report
# before trusting it for a name not listed here.
FALLBACK_COUNTRY_ISO2 = {
    "Gibraltar": "GI",
    "Johnson Atoll": "UM",   # Johnston Atoll; no distinct ISO 3166 code, folded
                             # into US Minor Outlying Islands as ISO does
    "Midway Islands": "UM",
    "Norfolk Island": "NF",
    "Palau": "PW",
    "Wake Island": "UM",
}

FIELDS = [
    Field("WPI_NO", "N", 8),
    Field("LOCODE", "C", 5),
    Field("NAME", "C", 50),
    Field("ALT_NAME", "C", 80),
    Field("COUNTRY", "C", 2),
    Field("CTRY_NAME", "C", 60),
    Field("REGION", "C", 50),
    Field("HARBORSIZE", "C", 12),
    Field("HARBORTYPE", "C", 24),
    Field("HARBORUSE", "C", 10),
    Field("FAC_CONTAI", "C", 1),
    Field("FAC_RORO", "C", 1),
    Field("FAC_SOLIDB", "C", 1),
    Field("FAC_LIQUID", "C", 1),
    Field("FAC_BREAKB", "C", 1),
    Field("FAC_OILTER", "C", 1),
    Field("FAC_LNGTER", "C", 1),
    Field("SHELTER", "C", 10),
    Field("REPAIRS", "C", 16),
    Field("CHAN_DEPTH", "N", 6, 1),
    Field("CARGODEPTH", "N", 6, 1),
    Field("MAX_LOA", "N", 6, 1),
    Field("MAX_DRAFT", "N", 5, 1),
    Field("LAT", "N", 10, 6),
    Field("LON", "N", 11, 6),
]

FACILITY_FIELDS = [
    ("FAC_CONTAI", "Facilities - Container"),
    ("FAC_RORO", "Facilities - Ro-Ro"),
    ("FAC_SOLIDB", "Facilities - Solid Bulk"),
    ("FAC_LIQUID", "Facilities - Liquid Bulk"),
    ("FAC_BREAKB", "Facilities - Breakbulk"),
    ("FAC_OILTER", "Facilities - Oil Terminal"),
    ("FAC_LNGTER", "Facilities - LNG Terminal"),
]

# These fields use 0.0 to mean "not recorded", not a real zero: e.g. Maximum
# Vessel Draft is 0.0 on 75% of rows, which is not plausible for a working port.
# Storing 0.0 as-is would read as "vessels of zero draft only." Blank is honest.
DEPTH_FIELDS = [
    ("CHAN_DEPTH", "Channel Depth (m)"),
    ("CARGODEPTH", "Cargo Pier Depth (m)"),
    ("MAX_LOA", "Maximum Vessel Length (m)"),
    ("MAX_DRAFT", "Maximum Vessel Draft (m)"),
]

YES_NO = {"Yes": "Y", "No": "N", "Unknown": "U", "": "U"}


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def read_rows(path: Path):
    text = decode(path.read_bytes())
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(
            "%s is missing the column(s) %s - NGA may have changed the export "
            "schema.\nColumns found: %s"
            % (path.name, ", ".join(missing), reader.fieldnames))
    return [row for row in reader if any((v or "").strip() for v in row.values())]


def build_country_map(rows):
    """Country name -> ISO 3166-1 alpha-2, derived from this release's own data."""
    votes = defaultdict(Counter)
    for row in rows:
        locode = row["UN/LOCODE"].strip().replace(" ", "")
        name = row["Country Code"].strip()
        if len(locode) >= 2 and locode[:2].isalpha():
            votes[name][locode[:2].upper()] += 1

    mapping, ambiguous = {}, {}
    for name, counter in votes.items():
        iso2, top_count = counter.most_common(1)[0]
        mapping[name] = iso2
        if len(counter) > 1:
            ambiguous[name] = counter.most_common()

    fallback_used = {}
    for name in {row["Country Code"].strip() for row in rows} - set(mapping):
        if name in FALLBACK_COUNTRY_ISO2:
            mapping[name] = FALLBACK_COUNTRY_ISO2[name]
            fallback_used[name] = FALLBACK_COUNTRY_ISO2[name]

    unresolved = sorted({row["Country Code"].strip() for row in rows} - set(mapping))
    return mapping, ambiguous, fallback_used, unresolved


def clean_region(text: str) -> str:
    """Strip the trailing internal region id NGA appends, e.g. ' -- 6585'."""
    text = text.strip()
    if "--" in text:
        head, _, tail = text.rpartition("--")
        if tail.strip().isdigit():
            return head.strip()
    return text


def clean_locode(raw: str) -> str | None:
    code = "".join(raw.split()).upper()
    return code if len(code) == 5 and code.isalnum() else None


def parse_depth(raw: str):
    if not raw.strip():
        return None
    value = float(raw)
    return round(value, 1) if value != 0.0 else None


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(source_path: Path, out_dir: Path, source_url: str) -> None:
    rows = read_rows(source_path)
    print("Rows     : %d from %s" % (len(rows), source_path.name))

    country_map, ambiguous_names, fallback_used, unresolved_names = build_country_map(rows)

    records, bad_position, bad_locode = [], [], 0
    for row in rows:
        try:
            lat, lon = float(row["Latitude"]), float(row["Longitude"])
        except ValueError:
            bad_position.append(row)
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            bad_position.append(row)
            continue

        locode = None
        if row["UN/LOCODE"].strip():
            locode = clean_locode(row["UN/LOCODE"])
            if locode is None:
                bad_locode += 1

        try:
            wpi_no = int(float(row["World Port Index Number"]))
        except ValueError:
            wpi_no = None

        country_name = row["Country Code"].strip()
        attrs = {
            "WPI_NO": wpi_no,
            "LOCODE": locode or "",
            "NAME": row["Main Port Name"].strip(),
            "ALT_NAME": row["Alternate Port Name"].strip(),
            "COUNTRY": country_map.get(country_name, ""),
            "CTRY_NAME": country_name,
            "REGION": clean_region(row["Region Name"]),
            "HARBORSIZE": row["Harbor Size"].strip(),
            "HARBORTYPE": row["Harbor Type"].strip(),
            "HARBORUSE": row["Harbor Use"].strip(),
            "SHELTER": row["Shelter Afforded"].strip(),
            "REPAIRS": row["Repairs"].strip(),
            "LAT": round(lat, 6),
            "LON": round(lon, 6),
        }
        for field_name, source_col in FACILITY_FIELDS:
            attrs[field_name] = YES_NO.get(row[source_col].strip(), "U")
        for field_name, source_col in DEPTH_FIELDS:
            attrs[field_name] = parse_depth(row[source_col])

        records.append((lon, lat, attrs))

    dataset_dir = out_dir / DATASET_DIR
    result = write_point_shapefile(dataset_dir / LAYER_NAME, FIELDS, records)

    wpi_no_counts = Counter(a["WPI_NO"] for _, _, a in records if a["WPI_NO"] is not None)
    wpi_no_dupes = sorted(
        (num, [a["NAME"] for _, _, a in records if a["WPI_NO"] == num])
        for num, count in wpi_no_counts.items() if count > 1)

    locode_counts = Counter(a["LOCODE"] for _, _, a in records if a["LOCODE"])
    locode_shared = sum(1 for c in locode_counts.values() if c > 1)

    stats = {
        "rows": len(rows),
        "bad_position": len(bad_position),
        "written": len(records),
        "country_names": len({row["Country Code"].strip() for row in rows}),
        "country_by_vote": len(country_map) - len(fallback_used),
        "country_by_fallback": len(fallback_used),
        "country_unresolved": unresolved_names,
        "ambiguous_names": sorted(ambiguous_names.items())[:8],
        "alt_name_filled": sum(1 for _, _, a in records if a["ALT_NAME"]),
        "locode_filled": sum(1 for _, _, a in records if a["LOCODE"]),
        "locode_malformed": bad_locode,
        "locode_shared": locode_shared,
        "wpi_no_dupes": wpi_no_dupes,
        "harbor_use": Counter(a["HARBORUSE"] or "(blank)" for _, _, a in records),
        "harbor_type": Counter(a["HARBORTYPE"] or "(blank)" for _, _, a in records),
        "harbor_size": Counter(a["HARBORSIZE"] or "(blank)" for _, _, a in records),
        "facility_yes": {name: sum(1 for _, _, a in records if a[name] == "Y")
                         for name, _ in FACILITY_FIELDS},
        "depth_known": {name: sum(1 for _, _, a in records if a[name] is not None)
                        for name, _ in DEPTH_FIELDS},
        "source_url": source_url,
        "source_file": source_path.name,
    }

    readme = dataset_dir / "README.md"
    readme.write_text(render_readme(stats), encoding="utf-8")

    zip_path = dataset_dir / (LAYER_NAME + ".zip")
    members = [readme] + [dataset_dir / (LAYER_NAME + ext)
                          for ext in (".cpg", ".dbf", ".prj", ".shp", ".shx")]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for member in members:
            bundle.write(member, member.name)
    for member in members:
        if member.suffix != ".md":
            member.unlink()

    report(stats, result, zip_path, bad_position)


def report(stats, result, zip_path: Path, bad_position) -> None:
    with zipfile.ZipFile(zip_path) as bundle:
        unpacked = sum(i.file_size for i in bundle.infolist())

    print()
    print("=" * 64)
    print("WPI ports (NGA World Port Index, live feed)")
    print("=" * 64)
    print("  Rows read                   %8d" % stats["rows"])
    print("  Bad position (dropped)      %8d" % stats["bad_position"])
    for row in bad_position[:3]:
        print("        %-30s %r %r" % (row["Main Port Name"][:30], row["Latitude"], row["Longitude"]))
    print("  POINTS WRITTEN               %8d" % stats["written"])
    print()
    print("  Country names in release    %8d" % stats["country_names"])
    print("    resolved via UN/LOCODE    %8d" % stats["country_by_vote"])
    print("    resolved via fallback tbl %8d  (unverified against this release's own data)" %
          stats["country_by_fallback"])
    if stats["country_unresolved"]:
        print("    UNRESOLVED (no ISO2)      %8d  %s" % (
            len(stats["country_unresolved"]), stats["country_unresolved"]))
    if stats["ambiguous_names"]:
        print("    names with >1 ISO2 candidate (majority vote used):")
        for name, votes in stats["ambiguous_names"]:
            print("        %-24s %s" % (name, votes))
    print()
    print("  LOCODE filled                %8d   %5.1f%%" % (
        stats["locode_filled"], 100 * stats["locode_filled"] / max(stats["written"], 1)))
    print("  LOCODE malformed (dropped)   %8d" % stats["locode_malformed"])
    print("  LOCODE shared by >1 facility %8d   one location code, several named piers/terminals" %
          stats["locode_shared"])
    print("  WPI_NO duplicate values      %8d   NGA source anomaly, not merged" % len(stats["wpi_no_dupes"]))
    for num, names in stats["wpi_no_dupes"]:
        print("        %s -> %s" % (num, names))
    print()
    print("  Harbor Use:  %s" % stats["harbor_use"].most_common())
    print("  Harbor Size: %s" % stats["harbor_size"].most_common())
    print()
    print("  Cargo-type facilities (Yes count):")
    for name, source_col in FACILITY_FIELDS:
        print("        %-10s %5d   %s" % (name, stats["facility_yes"][name], source_col))
    print()
    print("  Depth fields with a real value (0.0 treated as not-recorded):")
    for name, source_col in DEPTH_FIELDS:
        n = stats["depth_known"][name]
        print("        %-10s %5d / %-5d %s" % (name, n, stats["written"], source_col))
    if result["truncations"]:
        print()
        print("  Attribute values truncated  %s" % result["truncations"])
    print()
    print("  Written  %s" % zip_path)
    print("           %.2f MB zipped, %.2f MB unpacked, %d points" % (
        zip_path.stat().st_size / 1e6, unpacked / 1e6, result["features"]))
    print("=" * 64)


def render_readme(s) -> str:
    harbor_use_rows = "\n".join(
        "| %s | %s |" % (u, format(n, ",")) for u, n in s["harbor_use"].most_common())
    harbor_type_rows = "\n".join(
        "| %s | %s |" % (t, format(n, ",")) for t, n in s["harbor_type"].most_common())
    facility_rows = "\n".join(
        "| `%s` | %s | %s |" % (field, col, format(s["facility_yes"][field], ","))
        for field, col in FACILITY_FIELDS)
    wpi_dupe_rows = "\n".join(
        "| %s | %s |" % (num, " / ".join(names)) for num, names in s["wpi_no_dupes"])
    unresolved_note = (
        "\n\n**%d country name(s) could not be mapped to an ISO code at all: %s.** "
        "`COUNTRY` is blank for these; `CTRY_NAME` still carries the name as given."
        % (len(s["country_unresolved"]), ", ".join(s["country_unresolved"]))
        if s["country_unresolved"] else "")

    return """# {layer}

NGA World Port Index ports, as points - live feed.

```
{written:,} points | EPSG:4326 (WGS 84) | UTF-8
```

## Where it comes from

**National Geospatial-Intelligence Agency**, World Port Index (Pub 150).

| | |
|---|---|
| Publication page | {dataset_page} |
| CSV downloaded | `{source_url}` |
| File | `{source_file}` |

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
- **An alternate name** where the source gives one ({alt_name_note}).

## Read this before you use it

**Most facility flags are `Unknown`, not `No`.** NGA's coverage of the newer
facility questions is thin - `Facilities - Container` alone is `Unknown` on
roughly 85% of rows. `U` means *not asked/not answered*, not *absent*. Filter
on `= 'Y'` to find ports confirmed to have a facility; do not treat `!= 'Y'` as
confirmation they lack it.

**`Harbor Use` is mostly `Unknown` too** - populated on {harbor_use_pop:.0f}% of ports. Where
it is populated, it is the one real port-type signal in this repo:

| Harbor Use | Ports |
|---|---:|
{harbor_use_rows}

**Depth and vessel-size fields use `0.0` to mean "not recorded," not zero.**
Checked against `Facilities - Oil Terminal`: even where that flag is `Yes`,
`Oil Terminal Depth` is `0.0` on about 15% of those rows - a port cannot have
an oil terminal with zero draft. Storing `0.0` as given would silently read as
a real value. This build writes those fields blank instead:

| Field | Has a value | Source column |
|---|---:|---|
| `CHAN_DEPTH` | {chan_depth_known:,} / {written:,} | Channel Depth (m) |
| `CARGODEPTH` | {cargo_depth_known:,} / {written:,} | Cargo Pier Depth (m) |
| `MAX_LOA` | {max_loa_known:,} / {written:,} | Maximum Vessel Length (m) |
| `MAX_DRAFT` | {max_draft_known:,} / {written:,} | Maximum Vessel Draft (m) |

**`LOCODE` is deliberately not unique, and that's different from the other two
port layers in this repo.** `unlocode_ports` and `upply_ports` merge to one
point per place. This dataset does not - NGA gives separate named rows to
distinct facilities that share one UN/LOCODE (a port and its offshore oil
terminal, for instance):

```
LOCODE = 'USVDZ'  NAME = 'Valdez'
LOCODE = 'USVDZ'  NAME = 'Valdez Marine Terminal'
```

{locode_shared:,} codes cover more than one row this way. Group by `LOCODE` when you want
one row per UN/LOCODE place; use every row as-is when you want every named
facility.

**`WPI_NO` has {wpi_no_dupe_count} duplicate value(s) in NGA's own data - not fixed here.**
Unlike the `LOCODE` sharing above, these look like data-entry errors: the two
rows are unrelated places, not a port and one of its terminals.

| WPI_NO | Rows sharing it |
|---|---|
{wpi_dupe_rows}

Neither row was dropped or renumbered - `WPI_NO` just isn't safe to treat as a
primary key until NGA fixes it upstream.

**`COUNTRY` is derived, not given.** The source's `Country Code` column is a
country *name* ("United States"), not an ISO code, unlike every other dataset
in this repo. `COUNTRY` is built by taking the first two letters of `UN/LOCODE`
from this release's own rows and majority-voting per country name -
{country_by_vote} of {country_names} names resolved this way. {country_by_fallback} names with no
UN/LOCODE evidence in this release ({fallback_names}) fall back to a small
hardcoded table in the build script - correct as far as I could confirm, but
not verified against this release's own data the way the rest of the mapping
is.{unresolved_note}

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
{facility_rows}

### Harbor Type - construction, not cargo type

| Harbor Type | Ports |
|---|---:|
{harbor_type_rows}

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
""".format(
        layer=LAYER_NAME,
        written=s["written"],
        dataset_page=DATASET_PAGE,
        source_url=s["source_url"],
        source_file=s["source_file"],
        alt_name_note="%s of %s rows" % (format(s["alt_name_filled"], ","), format(s["written"], ",")),
        harbor_use_pop=100 - 100 * s["harbor_use"].get("Unknown", 0) / max(s["written"], 1),
        harbor_use_rows=harbor_use_rows,
        chan_depth_known=s["depth_known"]["CHAN_DEPTH"],
        cargo_depth_known=s["depth_known"]["CARGODEPTH"],
        max_loa_known=s["depth_known"]["MAX_LOA"],
        max_draft_known=s["depth_known"]["MAX_DRAFT"],
        locode_shared=s["locode_shared"],
        wpi_no_dupe_count=len(s["wpi_no_dupes"]),
        wpi_dupe_rows=wpi_dupe_rows,
        country_by_vote=s["country_by_vote"],
        country_names=s["country_names"],
        country_by_fallback=s["country_by_fallback"],
        fallback_names=", ".join(FALLBACK_COUNTRY_ISO2) or "none",
        unresolved_note=unresolved_note,
        facility_rows=facility_rows,
        harbor_type_rows=harbor_type_rows,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download NGA's live World Port Index CSV and build the wpi_ports dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="UpdatedPub150.csv endpoint")
    parser.add_argument("--download-dir", type=Path, default=REPO_ROOT / "downloaded",
                        help="where the CSV is cached")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "datasets",
                        help="where the dataset folder is written")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    parser.add_argument("--source", type=Path, help="skip the download, use this local CSV")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    if args.source:
        build(args.source, args.out_dir, str(args.source))
    else:
        source = fetch(args.url, args.download_dir, force=args.force,
                       filename=SOURCE_FILENAME, help_url=DATASET_PAGE,
                       local_flag="--source")
        build(source, args.out_dir, args.url)


if __name__ == "__main__":
    main()
