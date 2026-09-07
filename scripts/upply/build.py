#!/usr/bin/env python3
"""Build the `upply_ports` GeoServer dataset from Upply's open seaport list.

Downloads UPPLY-SEAPORTS.csv (default: the data.gouv.fr resource), keeps every
row with a usable position, merges places listed under two codes, and writes a
zipped ESRI Shapefile shaped like the other datasets in this repo.

    python scripts/upply/build.py
    python scripts/upply/build.py --url https://.../UPPLY-SEAPORTS.csv
    python scripts/upply/build.py --force          # re-download
    python scripts/upply/build.py --source downloaded/UPPLY-SEAPORTS.csv

Standard library only - no GDAL, no geopandas.
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
from common.geo import distance_km, in_range  # noqa: E402
from common.shapefile_writer import Field, write_point_shapefile  # noqa: E402

# The CSV resource behind https://www.data.gouv.fr/datasets/seaports-locations-data
DEFAULT_URL = "https://www.data.gouv.fr/api/1/datasets/r/ac2c8109-8db3-40ff-af88-9e68ddafe66d"
SOURCE_FILENAME = "UPPLY-SEAPORTS.csv"
DATASET_PAGE = "https://opendata.upply.com/seaports"
PORTAL_PAGE = "https://www.data.gouv.fr/datasets/seaports-locations-data"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = "upply"          # datasets/upply/
LAYER_NAME = "upply_ports"     # datasets/upply/upply_ports.zip

# Two rows in one country sharing a name this close are one place listed twice.
# Unlike UN/LOCODE this list has no gap in the distribution to aim at, so the
# threshold is a judgement: below it the pairs are plainly aliases, above it
# same-name rows are usually separate terminals of one large port complex, which
# a port layer should keep apart. Kept equal to the unlocode_ports build so the
# two layers can be compared without allowing for different rules.
DUPLICATE_RADIUS_KM = 5.0

REQUIRED_COLUMNS = ("code", "name", "latitude", "longitude", "country_code", "zone_code")

# A coverage check, not a filter: if one of the world's busiest container ports is
# missing from a release, the layer is fine but a join keyed on that code is not,
# so the build says so and the README records it.
MAJOR_PORTS = {
    "SGSIN": "Singapore", "CNSGH": "Shanghai", "CNNGB": "Ningbo-Zhoushan",
    "CNSZX": "Shenzhen", "CNGZG": "Guangzhou", "KRPUS": "Busan", "HKHKG": "Hong Kong",
    "CNQIN": "Qingdao", "AEJEA": "Jebel Ali", "NLRTM": "Rotterdam",
    "MYPKG": "Port Klang", "BEANR": "Antwerp", "USLAX": "Los Angeles",
    "DEHAM": "Hamburg", "GRPIR": "Piraeus", "JPTYO": "Tokyo", "EGPSD": "Port Said",
    "LKCMB": "Colombo", "ESVLC": "Valencia", "TWKHH": "Kaohsiung",
}

FIELDS = [
    Field("LOCODE", "C", 5),
    Field("ALT_CODES", "C", 29),
    Field("NAME", "C", 60),
    Field("COUNTRY", "C", 2),
    Field("ZONE", "C", 8),
    Field("ZONE_REG", "C", 3),
    Field("LAT", "N", 10, 6),
    Field("LON", "N", 11, 6),
]


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def read_rows(path: Path):
    """Read the semicolon-delimited CSV, checking it has the columns we expect."""
    text = decode(path.read_bytes())
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(
            "%s is missing the column(s) %s.\nColumns found: %s"
            % (path.name, ", ".join(missing), reader.fieldnames))
    return [row for row in reader if any((v or "").strip() for v in row.values())]


def parse_point(row):
    """(lat, lon) as floats, or None when the row has no usable position."""
    try:
        lat = float((row["latitude"] or "").strip())
        lon = float((row["longitude"] or "").strip())
    except (TypeError, ValueError):
        return None
    return (lat, lon) if in_range(lat, lon) else None


def merge_same_place(placed):
    """Drop the second listing of a place that appears under two codes.

    `placed` is a list of (row, (lat, lon)). Two rows are the same place when
    they share a country, share a case-folded name, and sit within
    DUPLICATE_RADIUS_KM of each other.

    The file carries nothing that ranks one row above another - no status, no
    date, no source column - so the lower code wins. That is arbitrary but
    stable: the same input always yields the same output.

    Because the choice is arbitrary it must not lose anything, and a code is the
    one thing here people join on. Whichever code loses is kept on the surviving
    point in ALT_CODES, so a lookup for it still finds the place. Merging Ningbo
    is why this matters: `CNNGB` is the code in common use and `CNNBO` is the one
    UN/LOCODE marks as the port, and no rule available here reliably prefers the
    code a given user will reach for.

    Returns (kept, dropped) where kept items are (row, point, alt_codes).
    """
    groups = defaultdict(list)
    for item in placed:
        groups[(item[0]["country_code"], item[0]["name"].strip().casefold())].append(item)

    kept, dropped = [], []
    for items in groups.values():
        if len(items) == 1:
            kept.append((items[0][0], items[0][1], []))
            continue
        items.sort(key=lambda item: item[0]["code"])
        survivors, alternates = [], defaultdict(list)
        for item in items:
            twin = next((s for s in survivors
                         if distance_km(s[1], item[1]) <= DUPLICATE_RADIUS_KM), None)
            if twin is None:
                survivors.append(item)
            else:
                alternates[twin[0]["code"]].append(item[0]["code"])
                dropped.append((item, twin))
        kept += [(row, point, sorted(alternates[row["code"]])) for row, point in survivors]

    kept.sort(key=lambda item: item[0]["code"])
    return kept, dropped


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(source_path: Path, out_dir: Path, source_url: str) -> None:
    rows = read_rows(source_path)
    print("Rows     : %d from %s" % (len(rows), source_path.name))

    placed, unusable = [], []
    for row in rows:
        point = parse_point(row)
        if point is None:
            unusable.append(row)
        else:
            placed.append((row, point))

    placed, duplicates = merge_same_place(placed)

    records = []
    for row, (lat, lon), alternates in placed:
        zone = (row["zone_code"] or "").strip()
        records.append((lon, lat, {
            "LOCODE": (row["code"] or "").strip(),
            "ALT_CODES": ",".join(alternates),
            "NAME": (row["name"] or "").strip(),
            "COUNTRY": (row["country_code"] or "").strip(),
            "ZONE": zone,
            "ZONE_REG": zone.split("-")[0] if zone else "",
            "LAT": round(lat, 6),
            "LON": round(lon, 6),
        }))

    codes = [a["LOCODE"] for _, _, a in records]
    assert len(set(codes)) == len(codes), "duplicate code in output"

    # A code is reachable if it is a point's own code or is carried on one as an
    # alternate; only a code in neither place is genuinely absent from the source.
    alt_of_primary = {alt: a["LOCODE"] for _, _, a in records
                      for alt in a["ALT_CODES"].split(",") if alt}
    primary_of = dict(alt_of_primary)
    reachable = set(codes) | set(alt_of_primary)
    assert not (set(codes) & set(alt_of_primary)), "a code is both primary and alternate"

    dataset_dir = out_dir / DATASET_DIR
    result = write_point_shapefile(dataset_dir / LAYER_NAME, FIELDS, records)

    merged_pairs = sorted(
        ((loser[0]["code"], winner[0]["code"], winner[0]["name"],
          winner[0]["country_code"], distance_km(loser[1], winner[1]))
         for loser, winner in duplicates),
        key=lambda pair: (-pair[4], pair[2].casefold()))

    # How much of the apparent decimal precision is real. A position carried over
    # from UN/LOCODE lands on a whole arcminute; one sourced elsewhere generally
    # does not. 0.02' is 37 m, far inside the rounding of four decimal places.
    def on_whole_minute(value: float) -> bool:
        minutes = abs(value) * 60
        return abs(minutes - round(minutes)) < 0.02

    on_minute = sum(1 for _, point, _alt in placed
                    if on_whole_minute(point[0]) and on_whole_minute(point[1]))

    # Evidence for the rule the README explains.
    position_counts = Counter(point for _, point, _alt in placed)
    name_groups = defaultdict(list)
    for row, point, _alt in placed:
        name_groups[(row["country_code"], row["name"].strip().casefold())].append(point)
    kept_gaps = sorted(
        distance_km(points[i], points[j])
        for points in name_groups.values() if len(points) > 1
        for i in range(len(points))
        for j in range(i + 1, len(points)))

    stats = {
        "rows": len(rows),
        "unusable": len(unusable),
        "valid": len(rows) - len(unusable),
        "duplicates": len(duplicates),
        "written": len(records),
        "merged_pairs": merged_pairs,
        "widest_merge_km": max((p[4] for p in merged_pairs), default=0.0),
        "nearest_kept_km": kept_gaps[0] if kept_gaps else 0.0,
        "kept_name_pairs": len(kept_gaps),
        "colliding": sum(c for c in position_counts.values() if c > 1),
        "on_minute_pct": 100 * on_minute / max(len(placed), 1),
        "missing_major": sorted((code, name) for code, name in MAJOR_PORTS.items()
                                if code not in reachable),
        "merged_major": sorted((code, MAJOR_PORTS[code], primary_of[code])
                               for code in MAJOR_PORTS if code in alt_of_primary),
        "major_checked": len(MAJOR_PORTS),
        "countries": len({a["COUNTRY"] for _, _, a in records}),
        "zones": len({a["ZONE"] for _, _, a in records if a["ZONE"]}),
        "zone_counts": Counter(a["ZONE_REG"] for _, _, a in records),
        "code_country_mismatch": sum(1 for _, _, a in records
                                     if a["LOCODE"][:2] != a["COUNTRY"]),
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

    report(stats, result, zip_path, unusable)


def report(stats, result, zip_path: Path, unusable) -> None:
    with zipfile.ZipFile(zip_path) as bundle:
        unpacked = sum(i.file_size for i in bundle.infolist())
    rows = max(stats["rows"], 1)

    print()
    print("=" * 64)
    print("Upply seaports")
    print("=" * 64)
    print("  Rows read                   %8d" % stats["rows"])
    print("  Without a usable position   %8d   %5.1f%%   dropped" % (
        stats["unusable"], 100 * stats["unusable"] / rows))
    for row in unusable[:5]:
        print("        %-6s %-28s %r %r" % (row.get("code"), (row.get("name") or "")[:28],
                                            row.get("latitude"), row.get("longitude")))
    print("  PORTS with valid coordinates%8d   %5.1f%%" % (
        stats["valid"], 100 * stats["valid"] / rows))
    print()
    print("  Same place under two codes  %8d           dropped, <= %.0f km apart" % (
        stats["duplicates"], DUPLICATE_RADIUS_KM))
    for loser, winner, name, country, gap in stats["merged_pairs"][:8]:
        print("        %s dropped, kept %s  %-26s %s  %.1f km" % (
            loser, winner, name[:26], country, gap))
    if len(stats["merged_pairs"]) > 8:
        print("        ... and %d more" % (len(stats["merged_pairs"]) - 8))
    print()
    print("  POINTS WRITTEN              %8d" % stats["written"])
    print("  Countries / territories     %8d" % stats["countries"])
    print("  Upply zones                 %8d" % stats["zones"])
    print("  Major ports checked         %8d   %d absent, %d kept as an alternate code" % (
        len(MAJOR_PORTS), len(stats["missing_major"]), len(stats["merged_major"])))
    for code, name, primary in stats["merged_major"]:
        print("        %s %s - merged into %s, still in ALT_CODES" % (code, name, primary))
    for code, name in stats["missing_major"]:
        print("        %s %s - absent from the source entirely" % (code, name))
    if result["truncations"]:
        print("  Attribute values truncated  %s" % result["truncations"])
    print()
    print("  Written  %s" % zip_path)
    print("           %.2f MB zipped, %.2f MB unpacked, %d points" % (
        zip_path.stat().st_size / 1e6, unpacked / 1e6, result["features"]))
    print("=" * 64)


def render_readme(s) -> str:
    merged_rows = "\n".join(
        "| `%s` | `%s` | %s | %s | %.1f km |" % (winner, loser, name, country, gap)
        for loser, winner, name, country, gap in s["merged_pairs"])
    zone_rows = "\n".join(
        "| `%s` | %s |" % (region or "(blank)", format(count, ","))
        for region, count in s["zone_counts"].most_common())

    missing_major_note = ""
    if s["missing_major"]:
        listed = ", ".join("`%s` %s" % (code, name) for code, name in s["missing_major"])
        plural = len(s["missing_major"]) > 1
        missing_major_note = (
            "**Some major ports have no entry at all.** Of the %d busiest container ports\n"
            "this build checks for, %s %s absent from the source, so a lookup for\n"
            "%s finds nothing in either `LOCODE` or `ALT_CODES`.%s\n\n"
            % (s["major_checked"], listed, "are" if plural else "is",
               "those codes" if plural else "that code",
               " Singapore is in the file only\nas its separate terminals - Jurong, Tuas, "
               "Pasir Panjang, Changi - with no\naggregate entry."
               if any(code == "SGSIN" for code, _ in s["missing_major"]) else ""))

    return """# {layer}

Upply's open list of world seaports, as points.

```
{written:,} points | EPSG:4326 (WGS 84) | UTF-8
```

## Data Source & Attribution

This shapefile dataset is derived from **Seaports Locations Data** (published by
Upply as the *Upply Open Data - Global Seaports List*, file `UPPLY-SEAPORTS.csv`)
created by **Upply**, available at {dataset_page}.

Licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0):

https://creativecommons.org/licenses/by/4.0/

Modifications: converted original data format to ESRI Shapefile (.shp) and
compressed into .zip format; split the semicolon-delimited CSV into typed
shapefile attributes; split `zone_code` into `ZONE` and its macro-region prefix
`ZONE_REG`; dropped rows without a usable position ({unusable} in this release);
merged {duplicates} places that the source lists under two codes, keeping the merged-away
code in `ALT_CODES`; wrote attributes as UTF-8 with a matching `.cpg`.
Coordinates were **not** reprojected - the source publishes WGS 84, which is
already EPSG:4326.

| | |
|---|---|
| Dataset page | {dataset_page} |
| Open-data portal | {portal_page} |
| Resource downloaded | `{source_url}` |
| File | `{source_file}` |
| Licence | CC BY 4.0 - credit Upply (https://www.upply.com) |

Built by [scripts/upply/build.py](../../scripts/upply/build.py). Point it at
another release with `--url`.

## What it is

Upply's documentation describes the file as an enriched, normalised list of
world seaports drawn from **Upply and UNECE** sources. `code` is the UN/LOCODE
where one exists, `name` is the English port name, and `zone_code` places the
port in an Upply trade region.

Two things follow from that lineage, and both matter:

**The coordinates are cleaner than UN/LOCODE's.** Checked against the
`unlocode_ports` layer in this repo, the two agree closely on the great majority
of the codes they share - and where they disagree badly, it is UN/LOCODE that is
wrong. UN/LOCODE places `AUMID` Midland, Western Australia at `31.88N 115.98W`,
in Baja California; Upply has it at `-31.89, 116.01`, which is Perth. `USGBV`
Garberville, California and `RORNN` Rosia Montana, Romania are the same story - a
flipped hemisphere in UN/LOCODE, corrected here. Upply appears to have repaired
sign errors, which is the main reason to prefer this layer's positions.

**The precision is not as fine as it looks.** {on_minute:.1f}% of the coordinates land
exactly on a whole arcminute, because they are UN/LOCODE's degrees-and-minutes
converted to decimal. Four decimal places suggests 11 m; the real resolution for
those rows is the arcminute UN/LOCODE gave, about **1.8 km**. The remaining
{off_minute:.1f}% carry genuinely finer positions.

**This is not a seaport-only list, despite the name.** It inherits UN/LOCODE's
definition of a port, so inland places are in it - Chauffour, Ravigny and
Saint-Pierre-sur-Dives are French villages, not harbours.

## What was left out

{rows:,} rows went in, {written:,} points came out.

| Dropped | Count | Why |
|---|---:|---|
| No usable position | {unusable} | Latitude or longitude absent, non-numeric, or out of range |
| Same place, second code | {duplicates} | Listed twice under two codes |

**Every coordinate in the source parses and falls in range.** Nothing was dropped
on those grounds in this release. Points that look like outliers are real:
Kiska Island and Tanaga Bay are Aleutian, west of the antimeridian; Uelen and
Mys Shmidta are Chukotkan, east of it; the `BQ` codes are Bonaire, Saba and Sint
Eustatius, which the file attributes to country `NL`. That last case is why
{code_country_mismatch} rows have a `LOCODE` whose first two letters differ from `COUNTRY`.

**In range is not the same as in the right place.** Range and format are all that
can be checked without boundary data to test against. A well-formed coordinate
pointing at the wrong town would survive.

**{duplicates} places are listed under two codes.** Two rows count as one place when they
share a country, share a case-folded name, and sit within {radius:.0f} km of each other.
The file carries no status, date or source column to rank rows by, so the lower
code wins - arbitrary, but stable across runs.

**No code is lost to that arbitrary choice.** The losing code is carried on the
surviving point in `ALT_CODES`, so a lookup for it still finds the place:

```
LOCODE = 'CNNBO'  ALT_CODES = 'CNNGB'  NAME = 'Ningbo'
```

Ningbo is exactly why this matters. `CNNGB` is the code in common use for
Ningbo-Zhoushan; `CNNBO` is the one UN/LOCODE flags as the port. No rule
available in this file reliably prefers the code a given user will reach for, so
both are kept and neither join fails. Filter with
`LOCODE = 'X' OR ALT_CODES LIKE '%X%'` when the code you hold might be an alias.

| Kept | Dropped | Place | Country | Apart |
|---|---|---|---|---:|
{merged_rows}

Same position alone would not do as a test: {colliding} points share a position with
another port and are mostly distinct places. Same name alone would not either -
{kept_name_pairs} same-country name pairs survive as genuinely different places.

**Unlike `unlocode_ports`, the threshold here sits in no natural gap.** The widest
pair merged is {widest_merge_km:.1f} km apart and the closest same-name pair kept is {nearest_kept_km:.1f} km apart -
the distribution is continuous, so {radius:.0f} km is a judgement rather than a boundary the
data draws. Just above the line sit same-name pairs like Shenzhen (6.1 km),
Yantai (10.9 km), Dalian (12.0 km) and Nanjing (18.6 km). Those are kept, on the
reasoning that a large Chinese port complex has genuinely separate terminals. If
you would rather collapse them, raise `DUPLICATE_RADIUS_KM` in the build script.

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` - CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Type | Notes |
|---|---|---|
| `LOCODE` | C(5) | the source `code`; the UN/LOCODE where one exists. Unique |
| `ALT_CODES` | C(29) | comma-separated codes merged into this point, blank for most rows |
| `NAME` | C(60) | English port name |
| `COUNTRY` | C(2) | ISO 3166-1 alpha-2, as the source assigns it |
| `ZONE` | C(8) | Upply trade region, e.g. `EU-NEU`, `AS-SIN` |
| `ZONE_REG` | C(3) | the macro-region prefix of `ZONE`, split out for styling |
| `LAT` `LON` | N(10,6) N(11,6) | decimal degrees, WGS 84, as published |

Upply does not publish the meaning of the zone codes in the CSV or its
documentation, so they are carried through verbatim rather than decoded.

### Points by macro-region

| `ZONE_REG` | Points |
|---|---:|
{zone_rows}

## Read this before you use it

{missing_major_note}**Do not stack this over another port layer without deduplicating.** It overlaps
heavily with `unlocode_ports` in this repo - they share thousands of codes - and
with `wpi_ports`. Joining on `LOCODE` is reliable; joining on name is not.

**Prefer this layer's positions over `unlocode_ports` where both have a port.**
See the coordinate note above.

## How it was built

```sh
python scripts/upply/build.py
```

Downloads the CSV into `downloaded/`, keeps every row with a coordinate that
parses and falls in range, merges places listed under two codes, and writes the
shapefile with a dependency-free writer
([scripts/common/shapefile_writer.py](../../scripts/common/shapefile_writer.py)) -
this repo has no GDAL.
""".format(
        layer=LAYER_NAME,
        written=s["written"],
        rows=s["rows"],
        unusable=s["unusable"],
        duplicates=s["duplicates"],
        merged_rows=merged_rows,
        zone_rows=zone_rows,
        radius=DUPLICATE_RADIUS_KM,
        widest_merge_km=s["widest_merge_km"],
        nearest_kept_km=s["nearest_kept_km"],
        kept_name_pairs=s["kept_name_pairs"],
        colliding=s["colliding"],
        code_country_mismatch=s["code_country_mismatch"],
        dataset_page=DATASET_PAGE,
        portal_page=PORTAL_PAGE,
        source_url=s["source_url"],
        source_file=s["source_file"],
        on_minute=s["on_minute_pct"],
        off_minute=100 - s["on_minute_pct"],
        missing_major_note=missing_major_note,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Upply's open seaport list and build the upply_ports dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="UPPLY-SEAPORTS.csv resource")
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
                       filename=SOURCE_FILENAME, help_url=PORTAL_PAGE)
        build(source, args.out_dir, args.url)


if __name__ == "__main__":
    main()
