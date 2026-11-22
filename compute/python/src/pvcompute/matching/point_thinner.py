"""Thins out the LiDAR points of every building, so input.json is smaller.

The LiDAR scans from 2024 are very dense: on a roof the points lie about 11 cm apart (about 24 points
per m²), far more than needed to find the roof planes. The map is divided into square cells of
CELL_SIZE x CELL_SIZE metres and in every cell only one point of a building is kept. Places with few
points keep all of them; only crowded places lose points. On the Osowa data this removes about half of the points.

Not in the design doc: the doc passes all points; thinning was added on request to make input.json smaller.
Design doc: 2.3 (ground_points and roof_points of input.json).
"""

from __future__ import annotations

import numpy as np

from pvcompute.data_models import BuildingPoints


class PointThinner:
    """Keeps at most one point per square cell of the map, for the ground points and the roof points of a building."""

    CELL_SIZE = 0.25

    def thin(self, building: BuildingPoints) -> BuildingPoints:
        """Return the building with its ground points and roof points thinned out."""
        return BuildingPoints(
            footprint=building.footprint,
            ground_points=self._thin_points(building.ground_points),
            roof_points=self._thin_points(building.roof_points),
        )

    def _thin_points(self, points: np.ndarray) -> np.ndarray:
        """Return at most one point per cell (the first one found in it), keeping the original order."""
        if len(points) == 0:
            return points
        cells = np.floor(points[:, :2] / self.CELL_SIZE).astype(np.int64)
        _, first_in_cell = np.unique(cells, axis=0, return_index=True)
        return points[np.sort(first_in_cell)]
