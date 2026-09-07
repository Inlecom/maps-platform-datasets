"""Small geographic helpers shared by the dataset build scripts."""

from __future__ import annotations

import math


def distance_km(a, b) -> float:
    """Distance between two (lat, lon) pairs in kilometres.

    Equirectangular approximation. It is used here only to decide whether two
    entries are the same place, a question asked at single-digit kilometres, and
    at that range it agrees with the haversine formula to well under a metre.
    Do not reach for it near the antimeridian or the poles, where it breaks.
    """
    mean_lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111.32,
                      (a[1] - b[1]) * 111.32 * math.cos(mean_lat))


def in_range(lat, lon) -> bool:
    """True when a coordinate pair is inside the valid WGS 84 range."""
    return (lat is not None and lon is not None
            and math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180)
