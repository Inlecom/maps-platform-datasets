"""Minimal ESRI Shapefile point writer — standard library only.

Deliberately dependency-free: this repo has no GDAL and no geopandas, and a
point layer is the one shapefile geometry simple enough to emit by hand.
Writes .shp / .shx / .dbf / .prj / .cpg, UTF-8 attributes, EPSG:4326.
"""

from __future__ import annotations

import datetime as _dt
import struct
from pathlib import Path

# Same WKT the existing datasets in this repo carry, byte for byte.
PRJ_WGS84 = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",'
    "6378137.0,298.257223563]],PRIMEM[\"Greenwich\",0.0],"
    'UNIT["Degree",0.0174532925199433]]'
)

SHAPE_TYPE_POINT = 1


class Field:
    """One DBF column. `width` is in BYTES, not characters."""

    def __init__(self, name: str, ftype: str, width: int, decimals: int = 0):
        if len(name) > 10:
            raise ValueError(f"DBF field name too long (max 10): {name}")
        if not 1 <= width <= 254:
            raise ValueError(f"DBF field width out of range for {name}: {width}")
        self.name = name
        self.ftype = ftype  # 'C' or 'N'
        self.width = width
        self.decimals = decimals


def _fmt_char(value, width: int) -> tuple[bytes, bool]:
    """Encode a text value to exactly `width` bytes. Returns (bytes, truncated)."""
    raw = ("" if value is None else str(value)).encode("utf-8")
    truncated = False
    if len(raw) > width:
        truncated = True
        raw = raw[:width]
        # Never leave a half-written multi-byte character behind.
        while raw and (raw[-1] & 0xC0) == 0x80:
            raw = raw[:-1]
        if raw and raw[-1] >= 0xC0:
            raw = raw[:-1]
    return raw.ljust(width, b" "), truncated


def _fmt_num(value, width: int, decimals: int) -> tuple[bytes, bool]:
    if value is None or value == "":
        return b" " * width, False
    text = f"{float(value):.{decimals}f}" if decimals else f"{int(value)}"
    if len(text) > width:
        return b"*" * width, True
    return text.rjust(width).encode("ascii"), False


def write_point_shapefile(base_path, fields, records, prj: str = PRJ_WGS84) -> dict:
    """Write a point shapefile bundle.

    base_path : path without extension, e.g. .../unlocode_ports
    fields    : list[Field]
    records   : iterable of (lon, lat, {field_name: value})

    Returns a dict of per-field truncation counts and the feature count.
    """
    base = Path(base_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    records = list(records)
    n = len(records)

    # ---- .shp / .shx -----------------------------------------------------
    xs = [r[0] for r in records]
    ys = [r[1] for r in records]
    bbox = (min(xs), min(ys), max(xs), max(ys)) if n else (0.0, 0.0, 0.0, 0.0)

    shp_body, shx_body = bytearray(), bytearray()
    offset_words = 50  # the 100-byte header, counted in 16-bit words
    for i, (lon, lat, _) in enumerate(records, start=1):
        content = struct.pack("<idd", SHAPE_TYPE_POINT, lon, lat)  # 20 bytes
        shp_body += struct.pack(">ii", i, len(content) // 2) + content
        shx_body += struct.pack(">ii", offset_words, len(content) // 2)
        offset_words += (8 + len(content)) // 2

    def header(file_length_bytes: int) -> bytes:
        return (
            struct.pack(">iiiiiii", 9994, 0, 0, 0, 0, 0, file_length_bytes // 2)
            + struct.pack("<ii", 1000, SHAPE_TYPE_POINT)
            + struct.pack("<4d", *bbox)
            + struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)  # z and m ranges, unused
        )

    base.with_suffix(".shp").write_bytes(header(100 + len(shp_body)) + shp_body)
    base.with_suffix(".shx").write_bytes(header(100 + len(shx_body)) + shx_body)

    # ---- .dbf ------------------------------------------------------------
    record_length = 1 + sum(f.width for f in fields)
    header_length = 32 + 32 * len(fields) + 1
    today = _dt.date.today()

    dbf = bytearray()
    dbf += struct.pack(
        "<BBBBIHH20x",
        0x03,
        today.year - 1900,
        today.month,
        today.day,
        n,
        header_length,
        record_length,
    )
    for f in fields:
        dbf += (
            f.name.encode("ascii").ljust(11, b"\x00")
            + f.ftype.encode("ascii")
            + b"\x00" * 4
            + struct.pack("<BB", f.width, f.decimals)
            + b"\x00" * 14
        )
    dbf += b"\x0d"

    truncations = {f.name: 0 for f in fields}
    for _, _, attrs in records:
        row = bytearray(b" ")  # deletion flag
        for f in fields:
            value = attrs.get(f.name)
            if f.ftype == "N":
                encoded, over = _fmt_num(value, f.width, f.decimals)
            else:
                encoded, over = _fmt_char(value, f.width)
            if over:
                truncations[f.name] += 1
            row += encoded
        dbf += row
    dbf += b"\x1a"
    base.with_suffix(".dbf").write_bytes(bytes(dbf))

    # ---- sidecars --------------------------------------------------------
    base.with_suffix(".prj").write_bytes(prj.encode("ascii"))
    base.with_suffix(".cpg").write_bytes(b"UTF-8")

    return {"features": n, "truncations": {k: v for k, v in truncations.items() if v}}
