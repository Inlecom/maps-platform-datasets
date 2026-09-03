# ne_10m_bathymetry_all

World ocean bathymetry as **12 nested depth-band polygons** in one shapefile.
Ready to drop into GeoServer, QGIS or anything else that reads ESRI Shapefile.

```
5,779 polygons | EPSG:4326 (WGS 84) | UTF-8 | 34.4 MB unpacked
```

## Where it comes from

**Natural Earth**, 10m Physical Vectors — the "Bathymetry" dataset.

| | |
|---|---|
| Project | https://www.naturalearthdata.com |
| Dataset page | https://www.naturalearthdata.com/downloads/10m-physical-vectors/ |
| Bundle actually downloaded | `https://naturalearth.s3.amazonaws.com/10m_physical/10m_physical.zip` |

Natural Earth publishes bathymetry as **twelve separate shapefiles**, one per
depth band (`ne_10m_bathymetry_A_10000` … `ne_10m_bathymetry_L_0`). Their site
also offers a download called *Bathymetry (All)*, which is **not** a merged
layer — it is a zip of the same twelve separate files. This archive is the
merged version: the twelve appended into one layer, distinguished by the `depth`
attribute that Natural Earth already ships on every feature.

## Licence — free, no strings

Natural Earth data is in the **public domain**. No permission is required to
use it, for any purpose including commercial, and attribution is not required
(though the project appreciates a credit). Terms:
https://www.naturalearthdata.com/about/terms-of-use/

Because the merge is a mechanical append of public-domain inputs, this archive
carries no additional restrictions. Redistribute it freely.

## Contents

| File | Purpose |
|---|---|
| `ne_10m_bathymetry_all.shp` | geometry (34.0 MB) |
| `ne_10m_bathymetry_all.shx` | shape index |
| `ne_10m_bathymetry_all.dbf` | attributes |
| `ne_10m_bathymetry_all.prj` | CRS — GCS_WGS_1984 |
| `ne_10m_bathymetry_all.cpg` | encoding — `UTF-8` |
| `ne_10m_bathymetry_all.qix` | spatial index (regenerable) |

### Attributes

| Field | Type | Notes |
|---|---|---|
| `depth` | Integer | metres below sea level. **The only field that varies** — this is what you style on |
| `featurecla` | String | always `Bathymetry` |
| `scalerank` | Integer | always `0` |

### The twelve bands

| `depth` | polygons | | `depth` | polygons |
|---:|---:|---|---:|---:|
| 0 | 22 | | 5000 | 1,862 |
| 200 | 520 | | 6000 | 521 |
| 1000 | 157 | | 7000 | 59 |
| 2000 | 202 | | 8000 | 15 |
| 3000 | 671 | | 9000 | 22 |
| 4000 | 1,725 | | 10000 | 3 |

## Read this before you style it

**The bands are nested, not adjacent.** Each polygon covers everything *deeper
than* its value, so the `depth = 0` band is the entire ocean, `depth = 200`
covers everything below 200 m, and so on down. They stack like onion skins.

Two consequences:

1. **Paint shallow-first — 0, then 200, then 1000 …** Deeper bands go on top of
   shallower ones. Reverse it and the 0 m band covers the whole map in one flat
   colour.

2. **In SLD, give each band its own `FeatureTypeStyle`, not just its own
   `Rule`.** Inside a single `FeatureTypeStyle` the renderer walks features in
   *datastore* order and applies whichever rule matches, so listing rules
   shallow-to-deep guarantees nothing. This file happens to be stored
   deepest-first, so twelve rules in one `FeatureTypeStyle` paint the 0 m band
   last and you get a flat sea. A `FeatureTypeStyle` is a separate rendering
   pass, which is what actually fixes the order.

Twelve passes cost nothing measurable at this feature count — measured at
0.79–0.93 s for both the twelve-pass and the collapsed one-pass version of the
same view.

## How it was built

Appended with GDAL, from the twelve files in `10m_physical.zip`:

```sh
ogr2ogr -lco ENCODING=UTF-8 ne_10m_bathymetry_all.shp ne_10m_bathymetry_A_10000.shp
for b in B_9000 C_8000 D_7000 E_6000 F_5000 G_4000 \
         H_3000 I_2000 J_1000 K_200 L_0; do
  ogr2ogr -append ne_10m_bathymetry_all.shp ne_10m_bathymetry_$b.shp
done
```

`-lco ENCODING=UTF-8` matters: without it ogr2ogr writes ISO-8859-1 and the
`.cpg` no longer matches the bytes.

## Why merged at all

One layer in a map group instead of twelve, one style instead of twelve, and
the `depth` attribute expresses the whole ramp. There is no performance cost —
5,779 features is small enough that the twelve filtered passes read from page
cache.
