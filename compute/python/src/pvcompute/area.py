"""The map area that the data operator chooses for one calculation.

All positions in the project are in EPSG:2180, the Polish map coordinate system in metres
(x grows to the east, y grows to the north). An Area is a rectangle in that system.
PVGIS needs latitude and longitude instead (EPSG:4326, the system used by GPS).
It is used to pick the buildings and LiDAR points to process and to find the place for PVGIS.

Design doc: 2.1 (the module runs once for a chosen area); 2.3 (coordinates in metres, EPSG:2180).
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon, box

PROJECT_CRS = "EPSG:2180"
GPS_CRS = "EPSG:4326"


@dataclass(frozen=True)
class Area:
    """A rectangle on the map in EPSG:2180, given by its west, south, east and north edges."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def grown_by(self, margin: float) -> Area:
        """Return a bigger rectangle: every edge moved `margin` metres outwards."""
        return Area(self.min_x - margin, self.min_y - margin, self.max_x + margin, self.max_y + margin)

    def overlaps(self, other: Area) -> bool:
        """Tell whether this rectangle and `other` share at least one point."""
        return (
            self.min_x <= other.max_x
            and other.min_x <= self.max_x
            and self.min_y <= other.max_y
            and other.min_y <= self.max_y
        )

    def contains_points(self, points: np.ndarray) -> np.ndarray:
        """For an array of points (columns x, y, ...) return True/False per point: is it inside (edges count)."""
        x, y = points[:, 0], points[:, 1]
        return (x >= self.min_x) & (x <= self.max_x) & (y >= self.min_y) & (y <= self.max_y)

    def center_lat_lon(self) -> tuple[float, float]:
        """Return the latitude and longitude of the rectangle's center, rounded to 4 decimals (about 10 m)."""
        center = Point((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)
        center_gps = gpd.GeoSeries([center], crs=PROJECT_CRS).to_crs(GPS_CRS).iloc[0]
        return round(center_gps.y, 4), round(center_gps.x, 4)

    def to_polygon(self) -> Polygon:
        """Return the rectangle as a shapely polygon (for geometry operations)."""
        return box(self.min_x, self.min_y, self.max_x, self.max_y)
