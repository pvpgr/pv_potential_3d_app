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
    """Assigns ground and roof points to every building outline."""

    DEFAULT_GROUND_RING_WIDTH = 3.0

    def __init__(self, ground_ring_width: float = DEFAULT_GROUND_RING_WIDTH):
        """Set the width (metres) of the ring around a building where ground points are taken.

        The design doc only says "a ring around the building"; 3 m is the default.
        """
        if ground_ring_width <= 0:
            raise ValueError("ground ring width must be positive")
        self.ground_ring_width = ground_ring_width

    def match(self, footprints: Iterable[Footprint], point_cloud: PointCloud) -> list[BuildingPoints]:
        """Return every building together with its ground points and roof points.

        The outlines are "prepared" first, which makes the many "is this point inside?" tests faster.
        """
        ground_points = PointsSortedByX(point_cloud.ground_points)
        building_points = PointsSortedByX(point_cloud.building_points)
        buildings = []
        for footprint in footprints:
            outline = footprint.polygon
            outline_with_ring = outline.buffer(self.ground_ring_width)
            shapely.prepare(outline)
            shapely.prepare(outline_with_ring)
            buildings.append(
                BuildingPoints(
                    footprint=footprint,
                    ground_points=ground_points.inside(outline_with_ring, excluding=outline),
                    roof_points=building_points.inside(outline),
                )
            )
        return buildings


class PointsSortedByX:
    """Points kept sorted by x, so finding the points inside a shape checks only the points near it."""

    def __init__(self, points: np.ndarray):
        """Sort the points (one row per point: x, y, z) by x."""
        self.points = points[np.argsort(points[:, 0], kind="stable")]

    def inside(self, shape: BaseGeometry, excluding: BaseGeometry | None = None) -> np.ndarray:
        """Return the points inside `shape` (its edge counts as inside) but not inside `excluding`."""
        min_x, min_y, max_x, max_y = shape.bounds
        first = np.searchsorted(self.points[:, 0], min_x, side="left")
        after_last = np.searchsorted(self.points[:, 0], max_x, side="right")
        nearby = self.points[first:after_last]
        nearby = nearby[(nearby[:, 1] >= min_y) & (nearby[:, 1] <= max_y)]
        x, y = nearby[:, 0], nearby[:, 1]
        is_inside = shapely.intersects_xy(shape, x, y)
        if excluding is not None:
            is_inside &= ~shapely.intersects_xy(excluding, x, y)
        return nearby[is_inside]
