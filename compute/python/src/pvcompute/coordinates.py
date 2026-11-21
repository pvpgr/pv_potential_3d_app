"""Helpers for map coordinates.

The project keeps all positions in EPSG:2180, the Polish map coordinate system in metres
(x goes east, y goes north). This file knows that system and converts other systems to it.
It also holds BoundingBox: a simple rectangle on the map, used e.g. for the area chosen by the data operator.

Design doc: 2.3 (coordinates in metres, EPSG:2180).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box

TARGET_CRS = CRS.from_epsg(2180)
WGS84 = CRS.from_epsg(4326)


def is_target_crs(crs: CRS | str | None) -> bool:
    """True when data is already in EPSG:2180 (None, i.e. unknown, is treated as EPSG:2180).

    Compound CRSs (2D + height, common in LiDAR files) are compared by their horizontal part.
    """
    if crs is None:
        return True
    crs = CRS.from_user_input(crs)
    horizontal = crs.sub_crs_list[0] if crs.is_compound else crs
    return horizontal.equals(TARGET_CRS)


@dataclass(frozen=True)
class BoundingBox:
    """A rectangle in EPSG:2180, e.g. the area selected by the data operator."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def expanded(self, margin: float) -> BoundingBox:
        """E.g. the area plus the ground ring, so edge buildings get all their ground points."""
        return BoundingBox(self.min_x - margin, self.min_y - margin, self.max_x + margin, self.max_y + margin)

    def intersects(self, other: BoundingBox) -> bool:
        return (
            self.min_x <= other.max_x
            and other.min_x <= self.max_x
            and self.min_y <= other.max_y
            and other.min_y <= self.max_y
        )

    def contains_xy(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Boolean mask of the points lying inside the box (edges included)."""
        return (x >= self.min_x) & (x <= self.max_x) & (y >= self.min_y) & (y <= self.max_y)

    def transformed(self, src: CRS | str, dst: CRS | str) -> BoundingBox:
        transformer = Transformer.from_crs(src, dst, always_xy=True)
        return BoundingBox(*transformer.transform_bounds(*self.as_tuple()))

    def center_wgs84(self) -> tuple[float, float]:
        """(lat, lon) of the box center, as needed by PVGIS."""
        transformer = Transformer.from_crs(TARGET_CRS, WGS84, always_xy=True)
        lon, lat = transformer.transform((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)
        return round(lat, 4), round(lon, 4)

    def to_polygon(self) -> Polygon:
        return box(*self.as_tuple())

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)
