"""Builds input.json for one area by running all Python data-preparation steps in the order of the design doc.

1. read the building outlines from BDOT10k,
2. read the ground and building points from LiDAR,
3. give every building its ground points (ring around it) and roof points (inside it),
   then thin the points out (not in the design doc, added to make input.json smaller),
4. download the PVGIS sunlight table for the center of the area,
5. write the table and all buildings to input.json.

Design doc: 2.1 (blocks "Wczytanie obrysów" to "Zapis pliku wejściowego"); 2.5 "Przygotowanie danych (Python)".
"""

from __future__ import annotations

from pathlib import Path

from pvcompute.area import Area
from pvcompute.input_builder.input_json_writer import InputJsonWriter
from pvcompute.matching.point_matcher import PointMatcher
from pvcompute.matching.point_thinner import PointThinner
from pvcompute.sources.bdot10k_reader import Bdot10kReader
from pvcompute.sources.lidar_reader import LidarReader
from pvcompute.sources.pvgis_reader import PvgisReader


class InputJsonBuilder:
    """Runs the data-preparation steps for one area and writes input.json."""

    def __init__(
        self,
        bdot10k_reader: Bdot10kReader,
        lidar_reader: LidarReader,
        pvgis_reader: PvgisReader,
        point_matcher: PointMatcher,
        point_thinner: PointThinner,
    ):
        """Take the objects that do the single steps."""
        self.bdot10k_reader = bdot10k_reader
        self.lidar_reader = lidar_reader
        self.pvgis_reader = pvgis_reader
        self.point_matcher = point_matcher
        self.point_thinner = point_thinner

    def build(self, area: Area, input_json_path: str | Path) -> None:
        """Prepare all data of `area` and write it to `input_json_path`.

        LiDAR points are read for the area grown by the ground ring width, so buildings
        at the edge of the area also get the ground points around them.
        """
        footprints = self.bdot10k_reader.read(area)
        point_cloud_parts = self.lidar_reader.read(area.grown_by(self.point_matcher.GROUND_RING_WIDTH))
        buildings = self.point_matcher.match(footprints, point_cloud_parts)
        buildings = [self.point_thinner.thin(building) for building in buildings]
        pvgis_table = self.pvgis_reader.read(area)
        InputJsonWriter(input_json_path).write(pvgis_table, buildings)
