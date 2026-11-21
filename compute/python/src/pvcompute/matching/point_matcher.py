"""Gives each building its own LiDAR points.

For every building outline it picks:
- roof points: building points that lie inside the outline,
- ground points: ground points in a narrow ring around the outline.
The C++ program later uses the ground points to find the terrain height, and from that the building height.

Design doc: 2.1, block "Dopasowanie punktów"; 2.5.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from pvcompute.data_models import BuildingPoints, Footprint, PointCloud


class PointMatcher:
    GROUND_RING_WIDTH = 3.0
    """Metres; the design doc only says "a ring around the building"."""

    def __init__(self, ground_ring_width: float = GROUND_RING_WIDTH):
        if ground_ring_width <= 0:
            raise ValueError("ground ring width must be positive")
        self.ground_ring_width = ground_ring_width

    def match(self, footprints: Iterable[Footprint], cloud: PointCloud) -> list[BuildingPoints]:
        ground = SortedPointIndex(cloud.ground)
        roof = SortedPointIndex(cloud.building)
        result = []
        for footprint in footprints:
            polygon = footprint.polygon
            surroundings = polygon.buffer(self.ground_ring_width)
            shapely.prepare(polygon)
            shapely.prepare(surroundings)
            result.append(
                BuildingPoints(
                    footprint=footprint,
                    ground_points=ground.within(surroundings, exclude=polygon),
                    roof_points=roof.within(polygon),
                )
            )
        return result


class SortedPointIndex:
    """Points sorted by x, so a query only tests the points in the geometry's x-range."""

    def __init__(self, points: np.ndarray):
        self.points = points[np.argsort(points[:, 0], kind="stable")]
        self._x = self.points[:, 0]

    def within(self, geometry: BaseGeometry, exclude: BaseGeometry | None = None) -> np.ndarray:
        """Points inside `geometry` (boundary included) and outside `exclude`."""
        min_x, min_y, max_x, max_y = geometry.bounds
        lo = np.searchsorted(self._x, min_x, side="left")
        hi = np.searchsorted(self._x, max_x, side="right")
        candidates = self.points[lo:hi]
        candidates = candidates[(candidates[:, 1] >= min_y) & (candidates[:, 1] <= max_y)]
        if not len(candidates):
            return candidates
        x, y = candidates[:, 0], candidates[:, 1]
        mask = shapely.intersects_xy(geometry, x, y)
        if exclude is not None:
            mask &= ~shapely.intersects_xy(exclude, x, y)
        return candidates[mask]
