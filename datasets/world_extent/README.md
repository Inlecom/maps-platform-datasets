# world_extent

A single polygon covering the whole world, used as the flat sea fill beneath
the naviqore v2 basemap.

```
1 polygon | EPSG:4326 (WGS 84) | UTF-8 | ~600 bytes
extent -180,-85.0511 .. 180,85.0511
```

## Why it exists

No layer owns fine coastal water. OSM's land polygons correctly exclude a
harbour basin, and Natural Earth's bathymetry does not reach into one, because
NE's coastline is generalised to ~1,504 m against OSM's ~6.5 m. Anywhere OSM
resolves water that NE smooths into land — harbour basins, narrow channels,
river mouths — nothing draws at all. Measured at Piraeus z14: 1.32% of the
frame transparent, 100% of it outside OSM land.

`ne_10m_ocean` cannot fix it: it carries the same NE coastline, so its landward
limit is identical and the same basins stay empty. A synthetic rectangle has no
coastline to disagree with, which is the whole point.

## Why 85.0511 and not 90

That is the latitude limit Web Mercator can represent. ±90 reprojects to
infinity.

## Licence

Synthetic geometry, not derived from any source dataset. No restrictions.

## How it was built

```sh
# world.geojson: one Polygon, [-180,-85.0511] .. [180,85.0511]
ogr2ogr -lco ENCODING=UTF-8 -nln world_extent -a_srs EPSG:4326 \
  world_extent.shp world.geojson
```
