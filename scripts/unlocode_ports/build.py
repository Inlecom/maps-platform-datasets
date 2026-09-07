#!/usr/bin/env python3
"""Build the `unlocode_ports` GeoServer dataset from a UN/LOCODE release.

Downloads the UN/LOCODE code list (default: the UNECE/UN-CEFACT open-source
mirror), keeps every entry whose function classifier marks it as a port,
resolves the degree-and-minute coordinates into decimal degrees, and writes a
zipped ESRI Shapefile shaped like the other datasets in this repo.

Every point in the output has a coordinate that parses and falls in range, and
no place is listed twice.

    python scripts/unlocode_ports/build.py
    python scripts/unlocode_ports/build.py --url https://.../loc251csv.zip
    python scripts/unlocode_ports/build.py --force        # re-download

Standard library only - no GDAL, no geopandas.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.download import decode, fetch  # noqa: E402
from common.geo import distance_km  # noqa: E402
from common.shapefile_writer import Field, write_point_shapefile  # noqa: E402

DEFAULT_URL = (
    "https://opensource.unicc.org/un/unece/uncefact/vocab-locode/-/jobs/"
    "artifacts/2025-1/download?job=package-release"
)

DATASET_PAGE = "https://unece.org/trade/cefact/UNLOCODE-Download"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_NAME = "unlocode_ports"

# Two entries in one country sharing a name this close are one place listed
# twice. Measured against this release: seven pairs fall within 2.2 km, nothing
# at all lands between 2.2 and 25 km, and beyond that the matches are genuinely
# different places (two San Martins 724 km apart). The threshold sits in that gap.
DUPLICATE_RADIUS_KM = 5.0

# UN/LOCODE CSV columns - the file ships without a header row.
(CH, COUNTRY, LOCATION, NAME, NAME_WODIA, SUBDIV,
 FUNCTION, STATUS, DATE, IATA, COORD, REMARKS) = range(12)

# Function classifier: 8 positions, "1" in position 0 means port.
FUNCTION_FLAGS = [
    (1, "FN_RAIL", "2"),
    (2, "FN_ROAD", "3"),
    (3, "FN_AIR", "4"),
    (4, "FN_POST", "5"),
    (5, "FN_MULTI", "6"),
    (6, "FN_FIXED", "7"),
    (7, "FN_BORDER", "B"),
]

# Statuses that mean a competent authority signed the entry off.
VERIFIED_STATUSES = {"AA", "AC", "AF", "AI", "AM", "AS"}

STATUS_MEANING = {
    "AA": "Approved by competent national government agency",
    "AC": "Approved by Customs Authority",
    "AF": "Approved by national facilitation body",
    "AI": "Code adopted by international organisation (IATA/ECLAC)",
    "AM": "Approved by the UN/LOCODE Maintenance Agency",
    "AQ": "Entry approved, functions not verified",
    "AS": "Approved by national standardisation body",
    "QQ": "Original entry not verified since the date indicated",
    "RL": "Recognised location, confirmed by a non-government source",
    "RN": "Request from a credible national source",
    "RQ": "Request under consideration",
    "RR": "Request rejected",
    "UR": "Included on a user request, not officially approved",
    "XX": "Entry to be removed from the next issue",
}

COORD_RE = re.compile(r"^(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])$")

FIELDS = [
    Field("LOCODE", "C", 5),
    Field("COUNTRY", "C", 2),
    Field("LOCATION", "C", 3),
    Field("CTRY_NAME", "C", 50),
    Field("NAME", "C", 70),
    Field("NAME_ASCII", "C", 70),
    Field("SUBDIV", "C", 3),
    Field("SUBDIV_NM", "C", 80),
    Field("FUNCTION", "C", 8),
    *[Field(name, "C", 1) for _, name, _ in FUNCTION_FLAGS],
    Field("STATUS", "C", 2),
    Field("VERIFIED", "C", 1),
    Field("DATE", "C", 4),
    Field("IATA", "C", 3),
    Field("CH", "C", 2),
    Field("REMARKS", "C", 50),
    Field("COORD", "C", 12),
    Field("LAT", "N", 10, 6),
    Field("LON", "N", 11, 6),
]


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

def filename_for(url: str) -> str | None:
    """Name the cached download after the release, when the URL says which.

    The artifact URL carries the release tag in a path segment and nothing useful
    in Content-Disposition (it says only "artifacts.zip"), so caching by release
    tag keeps successive releases side by side. Returns None when the URL gives
    nothing to go on, leaving the choice to the downloader.
    """
    tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if tail.lower().endswith(".zip"):
        return tail

    generic = {"download", "artifacts", "jobs", "raw", "file", "-", ""}
    segments = [s for s in url.split("?")[0].split("/") if s not in generic]
    if segments and segments[-1] not in {"unece", "uncefact", "vocab-locode"}:
        return "unlocode-%s.zip" % segments[-1]
    return None


def download(url: str, dest_dir: Path, force: bool) -> Path:
    return fetch(url, dest_dir, force=force, filename=filename_for(url),
                 fallback="unlocode.zip", magic=b"PK",
                 help_url=DATASET_PAGE, local_flag="--archive")


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def read_csv_members(archive: zipfile.ZipFile):
    """Pull the code-list rows and the subdivision lookup out of the archive."""
    code_rows = []
    subdivisions = {}
    code_members = []

    for info in archive.infolist():
        name = Path(info.filename).name.lower()
        if info.is_dir() or not name.endswith(".csv"):
            continue
        rows = list(csv.reader(io.StringIO(decode(archive.read(info)))))
        if not rows:
            continue
        if "subdivision" in name:
            subdivisions.update({(r[0], r[1]): r[2] for r in rows if len(r) >= 3})
        elif len(rows[0]) == 12:
            code_members.append(info.filename)
            code_rows += [r for r in rows if len(r) == 12]

    if not code_rows:
        members = [i.filename for i in archive.infolist()][:20]
        raise SystemExit("No 12-column UN/LOCODE code-list CSV in the archive. Members: %s" % members)

    print("Code list: %s" % ", ".join(sorted(Path(m).name for m in code_members)))
    return code_rows, subdivisions


def parse_coordinate(text: str):
    """'4230N 00131E' -> (lat, lon) in decimal degrees, or None if not usable.

    Rejects anything that is not the documented degrees-and-minutes form, has a
    minutes field of 60 or more, or lands outside the valid range. A point that
    fails here has no correct position, so it does not go in the shapefile.
    """
    match = COORD_RE.match(text.strip())
    if not match:
        return None
    lat_d, lat_m, ns, lon_d, lon_m, ew = match.groups()
    if int(lat_m) >= 60 or int(lon_m) >= 60:
        return None
    lat = int(lat_d) + int(lat_m) / 60
    lon = int(lon_d) + int(lon_m) / 60
    if lat > 90 or lon > 180:
        return None
    return (-lat if ns == "S" else lat, -lon if ew == "W" else lon)


def issue_key(yymm: str) -> int:
    """UN/LOCODE dates are YYMM with a 2-digit year; the list began in 1996."""
    if len(yymm) != 4 or not yymm.isdigit():
        return -1
    year = int(yymm[:2])
    return (1900 + year if year >= 90 else 2000 + year) * 100 + int(yymm[2:])


def merge_renamed(ports):
    """A renamed location is republished under the same code with a new date.

    Keep the newest issue of each LOCODE; if that row lost its coordinate,
    inherit the most recent one that had it.
    """
    groups = defaultdict(list)
    for row in ports:
        groups[(row[COUNTRY], row[LOCATION])].append(row)

    kept, collapsed, inherited = [], 0, 0
    for rows in groups.values():
        if len(rows) == 1:
            kept.append(rows[0])
            continue
        collapsed += len(rows) - 1
        rows.sort(key=lambda r: (issue_key(r[DATE]), bool(r[COORD].strip())), reverse=True)
        winner = rows[0]
        if not winner[COORD].strip():
            donor = next((r for r in rows[1:] if r[COORD].strip()), None)
            if donor is not None:
                winner = list(winner)
                winner[COORD] = donor[COORD]
                inherited += 1
        kept.append(winner)

    kept.sort(key=lambda r: (r[COUNTRY], r[LOCATION]))
    return kept, collapsed, inherited


def merge_same_place(placed):
    """Drop the second listing of a place that appears under two codes.

    `placed` is a list of (row, (lat, lon)). Two entries are the same place when
    they share a country, share a diacritic-free name, and sit within
    DUPLICATE_RADIUS_KM of each other. Same coordinate alone is not enough - at
    this list's 1.8 km precision distinct towns collide - and same name alone is
    not enough either, since countries reuse names freely.

    The survivor is the better-sourced entry: authority-verified first, then the
    one describing more transport functions, then the newer issue, then the
    lower code so the choice is stable between runs.
    """
    def rank(item):
        row = item[0]
        modes = sum(1 for c in row[FUNCTION] if c not in "-0")
        return (row[STATUS] not in VERIFIED_STATUSES, -modes,
                -issue_key(row[DATE]), row[COUNTRY] + row[LOCATION])

    groups = defaultdict(list)
    for item in placed:
        groups[(item[0][COUNTRY], item[0][NAME_WODIA].strip().lower())].append(item)

    kept, dropped = [], []
    for items in groups.values():
        if len(items) == 1:
            kept.append(items[0])
            continue
        items.sort(key=rank)
        survivors = []
        for item in items:
            twin = next((s for s in survivors
                         if distance_km(s[1], item[1]) <= DUPLICATE_RADIUS_KM), None)
            if twin is None:
                survivors.append(item)
            else:
                dropped.append((item, twin))
        kept += survivors

    kept.sort(key=lambda item: (item[0][COUNTRY], item[0][LOCATION]))
    return kept, dropped


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(archive_path: Path, out_dir: Path, source_url: str) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        rows, subdivisions = read_csv_members(archive)

    countries = {r[COUNTRY]: r[NAME].lstrip(".") for r in rows if r[NAME].startswith(".")}
    entries = [r for r in rows if r[LOCATION].strip()]
    ports = [r for r in entries if r[FUNCTION][:1] == "1"]

    ports, renamed, inherited = merge_renamed(ports)

    with_coord = [r for r in ports if r[COORD].strip()]
    without_coord = len(ports) - len(with_coord)

    placed, malformed = [], []
    for row in with_coord:
        point = parse_coordinate(row[COORD])
        if point is None:
            malformed.append(row)
        else:
            placed.append((row, point))

    placed, duplicates = merge_same_place(placed)

    records, subdiv_resolved = [], 0
    for row, (lat, lon) in placed:
        subdiv_name = ""
        if row[SUBDIV].strip():
            subdiv_name = subdivisions.get((row[COUNTRY], row[SUBDIV]), "")
            if subdiv_name:
                subdiv_resolved += 1
        attrs = {
            "LOCODE": row[COUNTRY] + row[LOCATION],
            "COUNTRY": row[COUNTRY],
            "LOCATION": row[LOCATION],
            "CTRY_NAME": countries.get(row[COUNTRY], ""),
            "NAME": row[NAME],
            "NAME_ASCII": row[NAME_WODIA],
            "SUBDIV": row[SUBDIV],
            "SUBDIV_NM": subdiv_name,
            "FUNCTION": row[FUNCTION],
            "STATUS": row[STATUS],
            "VERIFIED": "Y" if row[STATUS] in VERIFIED_STATUSES else "N",
            "DATE": row[DATE],
            "IATA": row[IATA],
            "CH": row[CH],
            "REMARKS": row[REMARKS],
            "COORD": row[COORD].strip(),
            "LAT": round(lat, 6),
            "LON": round(lon, 6),
        }
        for index, flag_name, code in FUNCTION_FLAGS:
            attrs[flag_name] = "Y" if row[FUNCTION][index:index + 1] == code else "N"
        records.append((lon, lat, attrs))

    assert len({a["LOCODE"] for _, _, a in records}) == len(records), "duplicate LOCODE in output"

    # Evidence for the two rules the README explains: how many ports share a
    # position without being duplicates, and how many share a name without being
    # the same place.
    position_counts = Counter(point for _, point in placed)
    colliding = sum(count for count in position_counts.values() if count > 1)
    name_groups = defaultdict(list)
    for row, point in placed:
        name_groups[(row[COUNTRY], row[NAME_WODIA].strip().lower())].append(point)
    kept_name_gaps = [
        distance_km(points[i], points[j])
        for points in name_groups.values() if len(points) > 1
        for i in range(len(points))
        for j in range(i + 1, len(points))
    ]

    merged_pairs = [
        (loser[0][COUNTRY] + loser[0][LOCATION], winner[0][COUNTRY] + winner[0][LOCATION],
         winner[0][NAME], distance_km(loser[1], winner[1]))
        for loser, winner in duplicates]

    dataset_dir = out_dir / DATASET_NAME
    result = write_point_shapefile(dataset_dir / DATASET_NAME, FIELDS, records)

    stats = {
        "entries": len(entries),
        "ports_raw": len(ports) + renamed,
        "renamed": renamed,
        "inherited": inherited,
        "ports": len(ports),
        "with_coord": len(with_coord),
        "without_coord": without_coord,
        "malformed": len(malformed),
        "valid": len(with_coord) - len(malformed),
        "duplicates": len(duplicates),
        "colliding": colliding,
        "kept_name_pairs": len(kept_name_gaps),
        "nearest_kept_name_km": min(kept_name_gaps, default=0.0),
        "widest_merge_km": max((gap for _, _, _, gap in merged_pairs), default=0.0),
        "written": len(records),
        "subdiv_resolved": subdiv_resolved,
        "countries": len({a["COUNTRY"] for _, _, a in records}),
        "verified": sum(1 for _, _, a in records if a["VERIFIED"] == "Y"),
        "multimodal": sum(1 for _, _, a in records if a["FUNCTION"][1:].strip("-") != ""),
        "status_counts": Counter(r[STATUS] for r in ports),
        "no_coord_by_status": Counter(r[STATUS] for r in ports if not r[COORD].strip()),
        "missing_verified": sum(1 for r in ports
                                if not r[COORD].strip() and r[STATUS] in VERIFIED_STATUSES),
        "bad_example": malformed[0][COORD].strip() if malformed else "n/a",
        "duplicate_examples": merged_pairs,
        "source_url": source_url,
        "archive": archive_path.name,
    }

    readme = dataset_dir / "README.md"
    readme.write_text(render_readme(stats), encoding="utf-8")

    zip_path = dataset_dir / (DATASET_NAME + ".zip")
    members = [readme] + [dataset_dir / (DATASET_NAME + ext)
                          for ext in (".cpg", ".dbf", ".prj", ".shp", ".shx")]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for member in members:
            bundle.write(member, member.name)
    for member in members:
        if member.suffix != ".md":
            member.unlink()

    report(stats, result, zip_path, malformed)


def report(stats, result, zip_path: Path, malformed) -> None:
    with zipfile.ZipFile(zip_path) as bundle:
        unpacked = sum(i.file_size for i in bundle.infolist())
    ports = max(stats["ports"], 1)

    print()
    print("=" * 64)
    print("UN/LOCODE ports")
    print("=" * 64)
    print("  Code-list entries read      %8d" % stats["entries"])
    print("  Port entries (function 1)   %8d" % stats["ports_raw"])
    print("    renamed duplicates merged %8d%s" % (
        stats["renamed"],
        "  (%d inherited a coordinate)" % stats["inherited"] if stats["inherited"] else ""))
    print("  PORTS                       %8d" % stats["ports"])
    print()
    print("  With coordinates            %8d   %5.1f%%" % (
        stats["with_coord"], 100 * stats["with_coord"] / ports))
    print("  Without coordinates         %8d   %5.1f%%   dropped" % (
        stats["without_coord"], 100 * stats["without_coord"] / ports))
    print("  Malformed coordinates       %8d   %5.1f%%   dropped, minutes >= 60" % (
        stats["malformed"], 100 * stats["malformed"] / ports))
    for row in malformed[:3]:
        print("        %s%s  %-14s %s" % (
            row[COUNTRY], row[LOCATION], row[COORD].strip(), row[NAME][:30]))
    if len(malformed) > 3:
        print("        ... and %d more" % (len(malformed) - 3))
    print("  RESOLVED to a valid point   %8d   %5.1f%%   of all ports" % (
        stats["valid"], 100 * stats["valid"] / ports))
    print()
    print("  Same place under two codes  %8d           dropped, <= %.0f km apart" % (
        stats["duplicates"], DUPLICATE_RADIUS_KM))
    for loser, winner, name, gap in stats["duplicate_examples"]:
        print("        %s dropped, kept %s  %-24s %.1f km" % (loser, winner, name[:24], gap))
    print()
    print("  POINTS WRITTEN              %8d" % stats["written"])
    print("  Countries / territories     %8d" % stats["countries"])
    print("  Authority-verified status   %8d   %5.1f%%" % (
        stats["verified"], 100 * stats["verified"] / max(stats["written"], 1)))
    print("  Also rail/road/air/etc.     %8d" % stats["multimodal"])
    print("  Subdivision name resolved   %8d" % stats["subdiv_resolved"])
    if result["truncations"]:
        print("  Attribute values truncated  %s" % result["truncations"])
    print()
    print("  Written  %s" % zip_path)
    print("           %.2f MB zipped, %.2f MB unpacked, %d points" % (
        zip_path.stat().st_size / 1e6, unpacked / 1e6, result["features"]))
    print("=" * 64)


def render_readme(s) -> str:
    top_missing = ", ".join(
        "`%s` %s" % (code or "(blank)", format(count, ","))
        for code, count in s["no_coord_by_status"].most_common(4))
    status_rows = "\n".join(
        "| %s | %s | %s |" % ("`%s`" % code if code else "(blank)",
                              STATUS_MEANING.get(code, "not documented in the release"),
                              format(count, ","))
        for code, count in s["status_counts"].most_common())
    inherited_note = (", and %d inherited a coordinate from the older row" % s["inherited"]
                      if s["inherited"] else "")
    duplicate_rows = "\n".join(
        "| `%s` | `%s` | %s | %.1f km |" % (winner, loser, name, gap)
        for loser, winner, name, gap in sorted(s["duplicate_examples"],
                                               key=lambda d: d[2].lower()))

    return """# {name}

UN/LOCODE locations flagged as **ports**, as points.

```
{written:,} points (from {ports:,} port entries) | EPSG:4326 (WGS 84) | UTF-8
```

Every point has a coordinate that parses and falls in range, and no place
appears twice. See [What was left out](#what-was-left-out).

## Where it comes from

**UNECE / UN-CEFACT**, UN/LOCODE - the United Nations Code for Trade and
Transport Locations.

| | |
|---|---|
| Dataset page | https://unece.org/trade/cefact/UNLOCODE-Download |
| Bundle downloaded | `{source_url}` |
| Archive | `{archive}` |

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
seaport list. {multimodal:,} of these points are also a rail, road, air, postal,
multimodal, fixed-transport or border-crossing location; the `FN_*` fields say
which.

## What was left out

{ports:,} port entries went in, {written:,} points came out.

| Dropped | Count | Why |
|---|---:|---|
| No coordinate | {without_coord:,} | The source gives no position at all |
| Malformed coordinate | {malformed} | Minutes field reads 60 or higher |
| Same place, second code | {duplicates} | Listed twice under two codes |

**{without_coord:,} entries ({pct_missing:.0f}%) carry no coordinate.** This is not a quality
signal: {missing_verified:,} of them ({pct_missing_verified:.0f}%) are authority-approved entries, and the
largest groups are {top_missing}. If you need the complete code list, read the
source CSV; if you need those places on a map, geocode them elsewhere.

**{malformed} entries carry a malformed coordinate** - the minutes field reads 60 or
higher, e.g. `{bad_example}`. They look like decimal degrees typed into a
degrees-and-minutes field, but reading them that way drops several into the wrong
country or into open ocean, so they are discarded rather than guessed at.

**{duplicates} places are listed under two codes.** Two entries count as one place when
they share a country, share a diacritic-free name, and sit within {radius:.0f} km of each
other. The better-sourced entry survives - authority-verified first, then the one
describing more transport functions, then the newer issue.

| Kept | Dropped | Place | Apart |
|---|---|---|---:|
{duplicate_rows}

Neither test alone would do. **Same coordinate is not duplication**: {colliding} points
share their position with another port, and they are mostly distinct towns
rounding into one cell at this list's 1.8 km precision - Fengkai, Huaiji and
Zhaoqing all land on 23.05N 112.45E. **Same name is not duplication either**:
{kept_name_pairs} same-country name pairs survive, and they are different places that happen to
share a name, two San Martins 724 km apart in Argentina among them.

The threshold sits in a gap the data itself draws. The widest pair merged here is
**{widest_merge_km:.1f} km** apart; the closest same-name pair kept is **{nearest_kept_name_km:.0f} km** apart. Nothing
in this release falls between the two, so {radius:.0f} km separates them cleanly.

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

**Status is not uniform.** {verified:,} of {written:,} points carry a status
meaning a competent authority approved the entry. `VERIFIED = 'Y'` filters to
those; the rest are recognised locations, pending requests, or entries not
re-verified since the date shown.

**Renamed locations ship twice in the source.** A location whose name changed
appears once under the old name and once under the new, sharing one code. {renamed}
such pairs were collapsed to the newest issue{inherited_note}.

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
| `SUBDIV_NM` | C(80) | resolved from `SubdivisionCodes.csv` ({subdiv_resolved:,} of {written:,}) |
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

Counted over all {ports:,} port entries, including those with no usable position.

| Code | Meaning | Port entries |
|---|---|---:|
{status_rows}

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
""".format(
        name=DATASET_NAME,
        written=s["written"],
        ports=s["ports"],
        source_url=s["source_url"],
        archive=s["archive"],
        multimodal=s["multimodal"],
        without_coord=s["without_coord"],
        malformed=s["malformed"],
        duplicates=s["duplicates"],
        duplicate_rows=duplicate_rows,
        radius=DUPLICATE_RADIUS_KM,
        colliding=s["colliding"],
        kept_name_pairs=s["kept_name_pairs"],
        nearest_kept_name_km=s["nearest_kept_name_km"],
        widest_merge_km=s["widest_merge_km"],
        pct_missing=100 * s["without_coord"] / max(s["ports"], 1),
        missing_verified=s["missing_verified"],
        pct_missing_verified=100 * s["missing_verified"] / max(s["without_coord"], 1),
        top_missing=top_missing,
        verified=s["verified"],
        renamed=s["renamed"],
        inherited_note=inherited_note,
        subdiv_resolved=s["subdiv_resolved"],
        status_rows=status_rows,
        bad_example=s["bad_example"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a UN/LOCODE release and build the unlocode_ports dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="UN/LOCODE release zip to download")
    parser.add_argument("--download-dir", type=Path, default=REPO_ROOT / "downloaded",
                        help="where the release zip is cached")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "datasets",
                        help="where the dataset folder is written")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    parser.add_argument("--archive", type=Path, help="skip the download, use this local zip")
    args = parser.parse_args()

    # Port names are UTF-8; the Windows console is not, by default.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    if args.archive:
        build(args.archive, args.out_dir, str(args.archive))
    else:
        build(download(args.url, args.download_dir, args.force), args.out_dir, args.url)


if __name__ == "__main__":
    main()
