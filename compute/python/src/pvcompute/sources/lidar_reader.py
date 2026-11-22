"""Reads LiDAR points (a laser scan of the terrain) from LAS/LAZ files.

From the scan it keeps only the points marked as ground (class 2) and as building (class 6)
that lie in the chosen area, and gives them out part by part as PointCloud objects. The files must
already be in EPSG:2180, like the LiDAR data published for Poland; heights stay in metres above sea level.

Design doc: 2.1, block "Wczytanie chmury punktów"; 2.4 (laspy reads LAZ files).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
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

    def read(self, area: Area) -> Iterator[PointCloud]:
        """Give out the ground and building points that lie in `area`, one part of a file at a time.

        All points of a district do not fit into memory at once (hundreds of millions), so they come
        in parts of POINTS_PER_CHUNK file points and the caller keeps only what it needs.
        Pass the chosen area grown by the ground ring width, so buildings at the edge of the area
        also get the ground points around them. Files that lie outside the area are skipped.
        """
        for path in self.files:
            if not self._file_area(path).overlaps(area):
                continue
            with laspy.open(path) as lidar_file:
                for chunk in lidar_file.chunk_iterator(self.POINTS_PER_CHUNK):
                    points = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
                    point_classes = np.asarray(chunk.classification)
                    in_area = area.contains_points(points)
                    yield PointCloud(
                        ground_points=points[in_area & (point_classes == self.GROUND_CLASS)],
                        building_points=points[in_area & (point_classes == self.BUILDING_CLASS)],
                    )

    @staticmethod
    def _file_area(path: Path) -> Area:
        """Return the rectangle covered by a LiDAR file, read from its header (without reading the points)."""
        with laspy.open(path) as lidar_file:
            header = lidar_file.header
            return Area(header.mins[0], header.mins[1], header.maxs[0], header.maxs[1])

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
