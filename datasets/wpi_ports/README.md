# wpi_ports

NGA World Port Index (PUB 150), 25th edition — world ports as points.

```
3,669 points | EPSG:4326 (WGS 84) | UTF-8 | 2.73 MB unpacked
```

## Where it comes from

**National Geospatial-Intelligence Agency**, World Port Index PUB 150.
Project page: https://msi.nga.mil/Publications/WPI

NGA's own site is a JavaScript application and its download API refuses
scripted access, so this copy was pulled from a public ArcGIS mirror of the
25th edition (2017) and converted. Port positions do not change; the facilities
attributes are that edition's age.

## Licence — free, no strings

A work of the United States Government, therefore **public domain**. No
permission required, commercial use included, attribution not required.

## Contents

`.shp` `.shx` `.dbf` `.prj` `.cpg` — CRS `GCS_WGS_1984`, encoding `UTF-8`.

| Field | Notes |
|---|---|
| `PORT_NAME` | port name, **title-cased** (see below) |
| `COUNTRY` | ISO 3166-1 alpha-2 |
| `INDEX_NO` | WPI index number |
| `HARBORSIZE` | **L / M / S / V** — a real four-level ranking: L 160, M 361, S 990, V 2,153, 5 null |
| `HARBORTYPE` | coded harbour type |
| `CHAN_DEPTH`, `ANCH_DEPTH`, `CARGODEPTH`, `MAX_VESSEL` | WPI **range codes**, see warning |
| `SHELTER` | shelter afforded |

## Read this before you use it

**The depth fields are letters, not metres.** `CHAN_DEPTH = J` is a range code
from the PUB 150 tables, not a number. They cannot be compared or filtered
numerically without that lookup.

**`HARBORSIZE` is the useful ranking.** Far better than Natural Earth's
`scalerank` for deciding what to draw at which zoom.

**Names are NGA romanisations, not English exonyms.** `Piraievs` not Piraeus,
`Canea` not Chania. Compared against Natural Earth's ports for every pair
within 10 km: 971 matched, **729 identical (75%)**, 242 different (25%), most
mildly (`St Johns` / `Saint John's`). Correct for a chart audience, unfamiliar
for a general one.

**Do not stack this over a basemap that already draws ports.** They do not
dedupe by name, so every shared harbour gets two pins.

## Two fixes applied when this was built

`PORT_NAME` ships in ALL CAPS (`KAWASAKI KO`, `CAPE TOWN`) and is title-cased
here, small words kept lowercase.

The source has **74 columns**, mostly single-letter codes. DBF is fixed-width,
so that was **19.33 MB of attributes around 0.10 MB of geometry**. Cut to the
ten fields above: **2.55 MB**.
