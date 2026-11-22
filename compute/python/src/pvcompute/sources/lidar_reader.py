"""Reads LiDAR points (a laser scan of the terrain) from LAS/LAZ files.

From the scan it keeps only the points marked as ground (class 2) and as building (class 6)
that lie in the chosen area, and returns them as a PointCloud. The files must already be in
EPSG:2180, like the LiDAR data published for Poland; heights stay in metres above sea level.

Design doc: 2.1, block "Wczytanie chmury punktów"; 2.4 (laspy reads LAZ files).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import laspy
import numpy as np

from pvcompute.area import Area
from pvcompute.data_models import PointCloud


class LidarReader:
    """Reads the ground and building points of one area from LAS/LAZ files."""

    GROUND_CLASS = 2
    BUILDING_CLASS = 6
    LIDAR_FILE_SUFFIXES = (".las", ".laz")
    POINTS_PER_CHUNK = 2_000_000

    def __init__(self, paths: Iterable[str | Path]):
        """Take LAS/LAZ files, or folders with such files, to read from."""
        self.files = self._find_lidar_files(paths)

    def read(self, area: Area) -> PointCloud:
        """Return the ground and building points that lie in `area`.

        Pass the chosen area grown by the ground ring width, so buildings at the edge
        of the area also get the ground points around them. Files that lie outside the area
        are skipped, and big files are read in parts so they do not have to fit into memory.
        """
        ground_parts: list[np.ndarray] = []
        building_parts: list[np.ndarray] = []
        for path in self.files:
            with laspy.open(path) as lidar_file:
                header = lidar_file.header
                file_area = Area(header.mins[0], header.mins[1], header.maxs[0], header.maxs[1])
                if not file_area.overlaps(area):
                    continue
                for chunk in lidar_file.chunk_iterator(self.POINTS_PER_CHUNK):
                    points = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
                    point_classes = np.asarray(chunk.classification)
                    in_area = area.contains_points(points)
                    ground_parts.append(points[in_area & (point_classes == self.GROUND_CLASS)])
                    building_parts.append(points[in_area & (point_classes == self.BUILDING_CLASS)])
        return PointCloud(self._join(ground_parts), self._join(building_parts))

    @classmethod
    def _find_lidar_files(cls, paths: Iterable[str | Path]) -> list[Path]:
        """Return the list of files to read: files are kept, folders are replaced by the LAS/LAZ files inside."""
        files: list[Path] = []
        for path in map(Path, paths):
            if path.is_dir():
                files += sorted(file for file in path.iterdir() if file.suffix.lower() in cls.LIDAR_FILE_SUFFIXES)
            elif path.is_file():
                files.append(path)
            else:
                raise FileNotFoundError(f"LiDAR path not found: {path}")
        if not files:
            raise FileNotFoundError("no LAS/LAZ files found in the given paths")
        return files

    @staticmethod
    def _join(parts: list[np.ndarray]) -> np.ndarray:
        """Join the point arrays from all chunks into one array (an empty one when there are no points)."""
        return np.concatenate(parts) if parts else np.empty((0, 3))
