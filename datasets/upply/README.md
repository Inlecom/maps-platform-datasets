# upply_ports

Upply's open list of world seaports, as points.

```
14,186 points | EPSG:4326 (WGS 84) | UTF-8
```

## Data Source & Attribution

This shapefile dataset is derived from **Seaports Locations Data** (published by
Upply as the *Upply Open Data - Global Seaports List*, file `UPPLY-SEAPORTS.csv`)
created by **Upply**, available at https://opendata.upply.com/seaports.

Licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0):

https://creativecommons.org/licenses/by/4.0/

Modifications: converted original data format to ESRI Shapefile (.shp) and
compressed into .zip format; split the semicolon-delimited CSV into typed
shapefile attributes; split `zone_code` into `ZONE` and its macro-region prefix
`ZONE_REG`; dropped rows without a usable position (0 in this release);
merged 83 places that the source lists under two codes, keeping the merged-away
code in `ALT_CODES`; wrote attributes as UTF-8 with a matching `.cpg`.
Coordinates were **not** reprojected - the source publishes WGS 84, which is
already EPSG:4326.

| | |
|---|---|
| Dataset page | https://opendata.upply.com/seaports |
| Open-data portal | https://www.data.gouv.fr/datasets/seaports-locations-data |
| Resource downloaded | `https://www.data.gouv.fr/api/1/datasets/r/ac2c8109-8db3-40ff-af88-9e68ddafe66d` |
| File | `UPPLY-SEAPORTS.csv` |
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

**The precision is not as fine as it looks.** 89.5% of the coordinates land
exactly on a whole arcminute, because they are UN/LOCODE's degrees-and-minutes
converted to decimal. Four decimal places suggests 11 m; the real resolution for
those rows is the arcminute UN/LOCODE gave, about **1.8 km**. The remaining
10.5% carry genuinely finer positions.

**This is not a seaport-only list, despite the name.** It inherits UN/LOCODE's
definition of a port, so inland places are in it - Chauffour, Ravigny and
Saint-Pierre-sur-Dives are French villages, not harbours.

## What was left out

14,269 rows went in, 14,186 points came out.

| Dropped | Count | Why |
|---|---:|---|
| No usable position | 0 | Latitude or longitude absent, non-numeric, or out of range |
| Same place, second code | 83 | Listed twice under two codes |

**Every coordinate in the source parses and falls in range.** Nothing was dropped
on those grounds in this release. Points that look like outliers are real:
Kiska Island and Tanaga Bay are Aleutian, west of the antimeridian; Uelen and
Mys Shmidta are Chukotkan, east of it; the `BQ` codes are Bonaire, Saba and Sint
Eustatius, which the file attributes to country `NL`. That last case is why
5 rows have a `LOCODE` whose first two letters differ from `COUNTRY`.

**In range is not the same as in the right place.** Range and format are all that
can be checked without boundary data to test against. A well-formed coordinate
pointing at the wrong town would survive.

**83 places are listed under two codes.** Two rows count as one place when they
share a country, share a case-folded name, and sit within 5 km of each other.
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
| `CNDJK` | `CNDOO` | Dongjiangkou | CN | 4.8 km |
| `CNGON` | `CNZGL` | Gaolan | CN | 3.9 km |
| `RUAMD` | `RUAMV` | Amderma | RU | 3.9 km |
| `CNTIZ` | `CNTZO` | Taizhou | CN | 3.8 km |
| `CNCAN` | `CNXSA` | Guangzhou | CN | 3.6 km |
| `CNCAN` | `CNGGZ` | Guangzhou | CN | 3.2 km |
| `PRSIG` | `PRSJU` | San Juan | PR | 3.0 km |
| `RUAGK` | `RURSK` | Angarsk | RU | 2.9 km |
| `EEMUG` | `EEMUU` | Muuga | EE | 2.6 km |
| `CNSIN` | `CNSTI` | Shatian | CN | 2.5 km |
| `USEZX` | `USPEB` | Port Elizabeth | US | 2.3 km |
| `FRLGQ` | `FRUEV` | Le Grand-Quevilly | FR | 2.3 km |
| `FRTHI` | `FRVIG` | Saint-Thibault-des-Vignes | FR | 2.2 km |
| `FRXLG` | `FRYLS` | Lignorelles | FR | 2.2 km |
| `SESCA` | `SESTA` | Stocka | SE | 2.1 km |
| `BRIIM` | `BRITZ` | Itapemirim | BR | 1.9 km |
| `CHMSC` | `CHMWA` | Meisterschwanden | CH | 1.9 km |
| `EEKND` | `EEKUN` | Kunda | EE | 1.9 km |
| `GRARM` | `GREFL` | Argostolion | GR | 1.9 km |
| `EETRU` | `EETYR` | Turusadam | EE | 1.9 km |
| `FRBEE` | `FRETB` | Berre-l'Etang | FR | 1.8 km |
| `RUFIP` | `RUVVO` | Vladivostok | RU | 1.8 km |
| `DEMHM` | `DEXMP` | Monheim | DE | 1.8 km |
| `CNTGG` | `CNTGU` | Tanggu | CN | 1.7 km |
| `MYNII` | `MYNIL` | Nilai | MY | 1.6 km |
| `CNCGM` | `CNCMG` | Chongming | CN | 1.6 km |
| `FRPKE` | `FRQZS` | Saint-Julien-de-Peyrolas | FR | 1.6 km |
| `TNRAD` | `TNRDS` | Rades | TN | 1.5 km |
| `CNNHN` | `CNWUH` | Wuhan | CN | 1.3 km |
| `FRVIY` | `FRVNH` | Vincey | FR | 1.2 km |
| `PLNCH` | `PLNIC` | Niechorze | PL | 1.1 km |
| `SESMV` | `SESPP` | Simpevarp | SE | 1.0 km |
| `CNXMG` | `CNXMP` | Xiamen Pt | CN | 1.0 km |
| `LVPAV` | `LVPVT` | Pavilosta | LV | 1.0 km |
| `EEKDV` | `EEKII` | Kiideva | EE | 1.0 km |
| `FIKNA` | `FIKSN` | Kasnas | FI | 0.9 km |
| `RUNJC` | `RUNNT` | Nizhnevartovsk | RU | 0.9 km |
| `USPAL` | `USPLL` | Port Allen | US | 0.8 km |
| `CNTJP` | `CNTNG` | Tianjin Pt | CN | 0.4 km |
| `LYDNF` | `LYDRX` | Darnah | LY | 0.0 km |
| `FRNPH` | `FRSRL` | Saint-Raphael | FR | 0.0 km |
| `BECMS` | `BECOM` | Comines | BE | 0.0 km |
| `FRCFG` | `FRMHJ` | Chateauneuf-le-Rouge | FR | 0.0 km |
| `FRBOI` | `FRNEG` | Bouguenais | FR | 0.0 km |
| `CYANM` | `CYAYI` | Ayia Napa | CY | 0.0 km |
| `BRLNH` | `BRLRS` | Linhares | BR | 0.0 km |
| `BRSBJ` | `BRSMS` | Sao Mateus | BR | 0.0 km |
| `IDSRG` | `IDTES` | Semarang | ID | 0.0 km |
| `INEKM` | `INERN` | Ernakulam | IN | 0.0 km |
| `CNWAI` | `CNWIH` | Waihai | CN | 0.0 km |
| `USPOA` | `USQRT` | Port Arthur | US | 0.0 km |
| `GRMAG` | `GRMGL` | Magoula | GR | 0.0 km |
| `USPOW` | `USRWR` | Port Washington | US | 0.0 km |
| `HRVRA` | `HRVRN` | Vranjic | HR | 0.0 km |
| `FRGMS` | `FRGUJ` | Gujan-Mestras | FR | 0.0 km |
| `CLGUR` | `CLISG` | Isla Guarello | CL | 0.0 km |
| `GBBEL` | `GBBFS` | Belfast | GB | 0.0 km |
| `SEVGO` | `SEVRN` | Vrango | SE | 0.0 km |
| `EERHV` | `EERUV` | Ruhve | EE | 0.0 km |
| `NOSAD` | `NOTRF` | Sandefjord | NO | 0.0 km |
| `EENEE` | `EENME` | Neeme | EE | 0.0 km |
| `FIMTL` | `FIMTY` | Mantyluoto | FI | 0.0 km |
| `FORUN` | `FORVK` | Runavik | FO | 0.0 km |
| `USWYZ` | `USYWZ` | Wayzata | US | 0.0 km |
| `SEGLM` | `SEGLN` | Glommen | SE | 0.0 km |
| `PAPSA` | `PAROD` | Rodman | PA | 0.0 km |
| `BHMIN` | `BHMSP` | Mina Sulman Port | BH | 0.0 km |
| `CNFCE` | `CNFCH` | Fengcheng | CN | 0.0 km |
| `KRICH` | `KRINC` | Incheon | KR | 0.0 km |
| `EEMDR` | `EEMID` | Miiduranna | EE | 0.0 km |
| `EEKLK` | `EEKNS` | Koljunuki | EE | 0.0 km |
| `NOHVR` | `NOKLD` | Kolvereid | NO | 0.0 km |
| `GBCSN` | `GBGTN` | Garston | GB | 0.0 km |
| `IEGGA` | `IEGGF` | Glengarriff | IE | 0.0 km |
| `EEHDI` | `EEHLD` | Haldi | EE | 0.0 km |
| `PLKMR` | `PLKRM` | Krynica Morska | PL | 0.0 km |
| `FRNCB` | `FRNQU` | Le Conquet | FR | 0.0 km |
| `FRMC9` | `FRMCC` | Morance | FR | 0.0 km |
| `CNNBO` | `CNNGB` | Ningbo | CN | 0.0 km |
| `CNSGH` | `CNSHA` | Shanghai | CN | 0.0 km |
| `KHSHV` | `KHSIH` | Sihanoukville | KH | 0.0 km |
| `US9AI` | `USWH7` | Waianae | US | 0.0 km |
| `CNYGS` | `CNYSN` | Yangshan | CN | 0.0 km |

Same position alone would not do as a test: 679 points share a position with
another port and are mostly distinct places. Same name alone would not either -
127 same-country name pairs survive as genuinely different places.

**Unlike `unlocode_ports`, the threshold here sits in no natural gap.** The widest
pair merged is 4.8 km apart and the closest same-name pair kept is 5.1 km apart -
the distribution is continuous, so 5 km is a judgement rather than a boundary the
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
| `EU` | 8,648 |
| `NAE` | 2,031 |
| `AS` | 1,399 |
| `SA` | 492 |
| `OC` | 448 |
| `AF` | 396 |
| `NAW` | 391 |
| `ME` | 381 |

## Read this before you use it

**Some major ports have no entry at all.** Of the 20 busiest container ports
this build checks for, `SGSIN` Singapore is absent from the source, so a lookup for
that code finds nothing in either `LOCODE` or `ALT_CODES`. Singapore is in the file only
as its separate terminals - Jurong, Tuas, Pasir Panjang, Changi - with no
aggregate entry.

**Do not stack this over another port layer without deduplicating.** It overlaps
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
