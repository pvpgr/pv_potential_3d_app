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
    """Assigns ground and roof points to every building outline.

    Ground points are taken from a ring GROUND_RING_WIDTH metres wide around the outline;
    the design doc only says "a ring around the building", 3 m was chosen.
    """

    GROUND_RING_WIDTH = 3.0

    def match(self, footprints: Iterable[Footprint], point_cloud_parts: Iterable[PointCloud]) -> list[BuildingPoints]:
        """Return every building together with its ground points and roof points.

        The LiDAR points come in parts (see LidarReader.read). From every part each building takes
        the points that belong to it and the rest is dropped, so only the needed points stay in memory.
        A part is checked only against the buildings that lie near it. The outlines are "prepared"
        first, which makes the many "is this point inside?" tests faster.
        """
        footprints = list(footprints)
        outlines = [footprint.polygon for footprint in footprints]
        outlines_with_ring = [outline.buffer(self.GROUND_RING_WIDTH) for outline in outlines]
        shapely.prepare(outlines)
        shapely.prepare(outlines_with_ring)
        ring_bounds = np.array([shape.bounds for shape in outlines_with_ring]).reshape(-1, 4)
        ground_found: list[list[np.ndarray]] = [[] for _ in footprints]
        roof_found: list[list[np.ndarray]] = [[] for _ in footprints]
        for part in point_cloud_parts:
            ground_points = PointsSortedByX(part.ground_points)
            building_points = PointsSortedByX(part.building_points)
            for index in self._buildings_near(ring_bounds, part):
                ground_found[index].append(ground_points.inside(outlines_with_ring[index], excluding=outlines[index]))
                roof_found[index].append(building_points.inside(outlines[index]))
        return [
            BuildingPoints(footprint, self._join(ground), self._join(roof))
            for footprint, ground, roof in zip(footprints, ground_found, roof_found)
        ]

    @staticmethod
    def _buildings_near(ring_bounds: np.ndarray, part: PointCloud) -> np.ndarray:
        """Return the numbers of the buildings whose outline with ring overlaps the rectangle covered by `part`."""
        points = np.concatenate((part.ground_points, part.building_points))
        if len(points) == 0:
            return np.empty(0, dtype=int)
        min_x, min_y = points[:, 0].min(), points[:, 1].min()
        max_x, max_y = points[:, 0].max(), points[:, 1].max()
        overlaps = (
            (ring_bounds[:, 0] <= max_x)
            & (ring_bounds[:, 2] >= min_x)
            & (ring_bounds[:, 1] <= max_y)
            & (ring_bounds[:, 3] >= min_y)
        )
        return np.flatnonzero(overlaps)

    @staticmethod
    def _join(parts: list[np.ndarray]) -> np.ndarray:
        """Join the points found in all parts into one array (an empty one when nothing was found)."""
        return np.concatenate(parts) if parts else np.empty((0, 3))


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
