"""Reads LiDAR points (a laser scan of the terrain) from LAS/LAZ files.

From the scan it keeps only the points marked as ground (class 2) and as building (class 6),
converts their position to EPSG:2180 when needed and returns them as a PointCloud.
Heights are left as they are: metres above sea level.

Design doc: 2.1, block "Wczytanie chmury punktów".
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import laspy
import numpy as np
from pyproj import CRS, Transformer

from pvcompute.geo import TARGET_CRS, BoundingBox, is_target_crs
from pvcompute.models import PointCloud

log = logging.getLogger(__name__)


class LidarReader:
    GROUND_CLASS = 2
    BUILDING_CLASS = 6
    SUFFIXES = frozenset({".las", ".laz"})
    CHUNK_SIZE = 2_000_000

    def __init__(self, paths: Iterable[str | Path], crs: str | None = None):
        """`paths`: LAS/LAZ files or directories containing them.

        `crs` overrides the CRS stored in the files (needed when headers have none and data is not EPSG:2180).
        """
        self.files = self._expand(paths)
        self._crs_override = CRS.from_user_input(crs) if crs else None
        self._warned_missing_crs = False

    def read(self, extent: BoundingBox) -> PointCloud:
        """Ground and building points inside `extent` (EPSG:2180).

        Pass the selected area expanded by the ground ring width, so buildings at the edge get their ground points.
        """
        ground: list[np.ndarray] = []
        building: list[np.ndarray] = []
        for path in self.files:
            with laspy.open(path) as reader:
                src = self._file_crs(reader.header, path)
                if not self._header_bounds(reader.header, src).intersects(extent):
                    log.debug("%s: outside the area, skipped", path.name)
                    continue
                to_target = None if is_target_crs(src) else Transformer.from_crs(src, TARGET_CRS, always_xy=True)
                log.info("reading %s (%d points)", path.name, reader.header.point_count)
                for chunk in reader.chunk_iterator(self.CHUNK_SIZE):
                    classes = np.asarray(chunk.classification)
                    xyz = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
                    for wanted, out in ((self.GROUND_CLASS, ground), (self.BUILDING_CLASS, building)):
                        selected = xyz[classes == wanted]
                        if not len(selected):
                            continue
                        if to_target is not None:
                            selected[:, 0], selected[:, 1] = to_target.transform(selected[:, 0], selected[:, 1])
                        out.append(selected[extent.contains_xy(selected[:, 0], selected[:, 1])])
        return PointCloud(self._stack(ground), self._stack(building))

    def _file_crs(self, header: laspy.LasHeader, path: Path) -> CRS | None:
        if self._crs_override is not None:
            return self._crs_override
        try:
            crs = header.parse_crs()
        except Exception as exc:  # malformed CRS records are common in older LAS files
            log.warning("%s: unreadable CRS (%s), assuming EPSG:2180", path.name, exc)
            return None
        if crs is None and not self._warned_missing_crs:
            log.warning("LiDAR files without CRS are assumed to be EPSG:2180 (pass `crs` to LidarReader otherwise)")
            self._warned_missing_crs = True
        return crs

    @staticmethod
    def _header_bounds(header: laspy.LasHeader, src: CRS | None) -> BoundingBox:
        bounds = BoundingBox(header.mins[0], header.mins[1], header.maxs[0], header.maxs[1])
        return bounds if is_target_crs(src) else bounds.transformed(src, TARGET_CRS)

    @classmethod
    def _expand(cls, paths: Iterable[str | Path]) -> list[Path]:
        """Directories are replaced by the LAS/LAZ files they contain."""
        paths = [Path(p) for p in paths]
        files: list[Path] = []
        for path in paths:
            if path.is_dir():
                files += sorted(f for f in path.iterdir() if f.suffix.lower() in cls.SUFFIXES)
            elif path.is_file():
                files.append(path)
            else:
                raise FileNotFoundError(path)
        if not files:
            raise FileNotFoundError(f"no LAS/LAZ files in {[str(p) for p in paths]}")
        return files

    @staticmethod
    def _stack(parts: list[np.ndarray]) -> np.ndarray:
        return np.concatenate(parts) if parts else np.empty((0, 3))
