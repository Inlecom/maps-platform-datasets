# ne_10m_ports_dedup

Natural Earth ports with same-name clusters collapsed to a single point.

```
1,063 points (from 1,081) | EPSG:4326 (WGS 84) | UTF-8 | 0.47 MB unpacked
```

## Where it comes from

**Natural Earth**, 10m Cultural Vectors — `ne_10m_ports`.

| | |
|---|---|
| Project | https://www.naturalearthdata.com |
| Dataset page | https://www.naturalearthdata.com/downloads/10m-cultural-vectors/ |
| Bundle downloaded | `https://naturalearth.s3.amazonaws.com/10m_cultural/10m_cultural.zip` |

## Licence — free, no strings

Natural Earth data is in the **public domain**. No permission is required for
any use including commercial, and attribution is not required.
Terms: https://www.naturalearthdata.com/about/terms-of-use/

This derived layer adds no restrictions. Redistribute it freely.

## What was collapsed and why

Natural Earth lists separate points for terminals and basins that a reader sees
as one port. Piraeus is three points; at low zoom they overlap into a smear of
identical markers.

Points sharing a name within **25 km** of each other are collapsed to one,
keeping the highest-ranked (lowest `scalerank`) of the group. **18 of 1,081**
points are removed.

Note this is a *marker* problem, not a label problem. The obvious fix —
`<VendorOption name="group">yes</VendorOption>` — is label-only: tested on
Piraeus it collapses three labels to one but **all three point symbols still
draw**. Marker duplication has to be solved in the data.

The full `ne_10m_ports` layer is still worth keeping alongside this one: a map
can show the deduplicated layer when zoomed out and hand over to the full layer
once individual terminals become meaningful (around z12).

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` — CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Type | Notes |
|---|---|---|
| `name` | String(50) | port name, UTF-8 |
| `scalerank` | Integer | 0–10, lower is more prominent |
| `featurecla` | String(80) | feature class |
| `website` | String(254) | as shipped by Natural Earth |
| `natlscale` | Real | natural scale hint |
| `ne_id` | Integer64 | Natural Earth stable id |

## How it was built

Name + proximity clustering (25 km), then written out with:

```sh
ogr2ogr -lco ENCODING=UTF-8 -where "@_dedup_where.txt" \
  ne_10m_ports_dedup.shp ne_10m_ports.shp
```

`-lco ENCODING=UTF-8` is not optional: without it ogr2ogr writes ISO-8859-1 and
non-ASCII port names come back as mojibake.
