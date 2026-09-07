# maps-platform-datasets

Geospatial datasets for the maps platform basemap and port/place layers, each
as a ready-to-load ESRI Shapefile in `EPSG:4326` (WGS 84), UTF-8 encoded.
Every dataset lives in its own folder under `datasets/` with its own README
covering provenance, licence, field reference, and anything you need to know
before styling or joining it.

## Datasets

| Dataset | What it is | Size | Licence |
|---|---:|---|---|
| [ne_10m_bathymetry_all](datasets/ne_10m_bathymetry_all/README.md) | World ocean bathymetry, 12 nested depth-band polygons | 5,779 polygons | Public domain (Natural Earth) |
| [ne_10m_populated_places_inland](datasets/ne_10m_populated_places_inland/README_places.md) | Populated places with anything within 12 km of a port removed | 6,537 points | Public domain (Natural Earth) |
| [ne_10m_ports_dedup](datasets/ne_10m_ports_dedup/README_ports.md) | Natural Earth ports with same-name clusters collapsed | 1,063 points | Public domain (Natural Earth) |
| [unlocode_ports](datasets/unlocode_ports/README.md) | UN/LOCODE locations flagged as ports | 11,725 points | Free use, attribution expected (UNECE) |
| [upply](datasets/upply/README.md) | Upply's open list of world seaports | 14,186 points | CC BY 4.0 (Upply) |
| [wpi_ports](datasets/wpi_ports/README.md) | NGA World Port Index ports, built from the live CSV feed | 3,807 points | Public domain (US Government) |
| [world_extent](datasets/world_extent/README.md) | Single polygon covering the whole world, used as flat sea fill | 1 polygon | Synthetic, no restrictions |

There are three overlapping seaport layers here — `wpi_ports`, `unlocode_ports`
and `upply` — each sourced independently (NGA, UNECE, Upply). They are not
merged into one canonical layer; check each README's "Read this before you use
it" section before stacking or joining them, especially around deduplication
and `UN/LOCODE` matching.

## How the datasets are built

Two build styles exist in this repo, depending on when the dataset was added:

- **GDAL-based** (`ne_10m_bathymetry_all`, `ne_10m_populated_places_inland`,
  `ne_10m_ports_dedup`, `world_extent`): built by hand with `ogr2ogr`, as
  documented in each dataset's own README.
- **Script-based, no GDAL** (`unlocode_ports`, `upply`, `wpi_ports`): built by
  Python scripts under [scripts/](scripts/), one folder per dataset plus a
  shared [scripts/common/](scripts/common/) with a download helper
  ([download.py](scripts/common/download.py)), geo utilities
  ([geo.py](scripts/common/geo.py)), and a dependency-free shapefile writer
  ([shapefile_writer.py](scripts/common/shapefile_writer.py)). These have no
  external Python dependencies — nothing to install.

To rebuild one of the scripted datasets:

```sh
python scripts/<dataset>/build.py
```

Source files are downloaded into `downloaded/` (git-ignored) and the
resulting shapefile is written into `datasets/<dataset>/`. Most build scripts
accept `--url` to point at a different release of the source.

## Licensing

Every dataset here is free to use, including commercially; see each dataset's
README for the exact terms and any attribution requirement (UNECE and Upply
both expect credit; Natural Earth, NGA and the synthetic `world_extent` do
not).
