"""Command for the data operator: prepares input.json for one area.

Run it inside compute/python with the virtual environment active, for example:

    python -m pvcompute.input_builder --bdot10k OT_BUBD_A.gpkg --lidar lidar_folder
        --area 465600 728830 466000 729300 --output input.json

--area is the chosen rectangle in EPSG:2180: west, south, east, north edge in metres.
--lidar takes LAS/LAZ files or folders with them.

Design doc: 2.1, use case "Przygotowanie danych wejściowych" (the module is run by hand, once per area).
"""

from __future__ import annotations

import argparse

from pvcompute.area import Area
from pvcompute.input_builder.input_json_builder import InputJsonBuilder
from pvcompute.matching.point_matcher import PointMatcher
from pvcompute.matching.point_thinner import PointThinner
from pvcompute.sources.bdot10k_reader import Bdot10kReader
from pvcompute.sources.lidar_reader import LidarReader
from pvcompute.sources.pvgis_reader import PvgisReader


def main(argv: list[str] | None = None) -> None:
    """Read the command-line options and build input.json."""
    parser = argparse.ArgumentParser(prog="python -m pvcompute.input_builder", description="Prepare input.json for one area.")
    parser.add_argument("--bdot10k", required=True, help="BDOT10k building file (OT_BUBD_A: GML, GPKG or SHP)")
    parser.add_argument("--lidar", required=True, nargs="+", help="LAS/LAZ files or folders with them")
    parser.add_argument("--area", required=True, nargs=4, type=float, metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"),
                        help="the area in EPSG:2180 metres")
    parser.add_argument("--output", required=True, help="where to write input.json")
    args = parser.parse_args(argv)

    builder = InputJsonBuilder(
        bdot10k_reader=Bdot10kReader(args.bdot10k),
        lidar_reader=LidarReader(args.lidar),
        pvgis_reader=PvgisReader(),
        point_matcher=PointMatcher(),
        point_thinner=PointThinner(),
    )
    builder.build(Area(*args.area), args.output)


if __name__ == "__main__":
    main()
