"""Writes input.json, the file that the C++ program reads.

It puts the PVGIS table and all buildings (ID, outline, ground points, roof points) into one file:

{
  "pvgis":     {lat, lon, slopes, azimuths, irradiation, yield},
  "buildings": [{id, footprint: [[x, y], ...], ground_points: [[x, y, z], ...], roof_points: [...]}]
}

Coordinates are rounded to centimetres and the outline is not closed (the first corner is not
repeated at the end), the same as in the design doc example.

Design doc: 2.1, block "Zapis pliku wejściowego"; format 2.3; example 2.6.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from pvcompute.data_models import BuildingPoints, PvgisTable


class InputJsonWriter:
    """Writes the PVGIS table and the buildings with their points to input.json."""

    DECIMALS = 2

    def __init__(self, path: str | Path):
        """Set where input.json will be written."""
        self.path = Path(path)

    def write(self, pvgis_table: PvgisTable, buildings: Iterable[BuildingPoints]) -> None:
        """Write the file (missing folders are created, an existing file is replaced).

        The file is written building by building, because for a whole district it has
        hundreds of MB and building it in memory at once would need several times more.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file:
            file.write('{"pvgis": ')
            json.dump(self._pvgis_entry(pvgis_table), file)
            file.write(', "buildings": [')
            for number, building in enumerate(buildings):
                if number > 0:
                    file.write(", ")
                json.dump(self._building_entry(building), file)
            file.write("]}")

    @staticmethod
    def _pvgis_entry(table: PvgisTable) -> dict:
        """Return the `pvgis` object of input.json."""
        return {
            "lat": table.lat,
            "lon": table.lon,
            "slopes": table.slopes,
            "azimuths": table.azimuths,
            "irradiation": table.irradiation,
            "yield": table.yield_per_kwp,
        }

    def _building_entry(self, building: BuildingPoints) -> dict:
        """Return one entry of the `buildings` list of input.json.

        Shapely repeats the first corner of an outline at the end; input.json does not, so it is cut off.
        """
        outline_corners = building.footprint.polygon.exterior.coords[:-1]
        return {
            "id": building.footprint.building_id,
            "footprint": self._rounded(outline_corners),
            "ground_points": self._rounded(building.ground_points),
            "roof_points": self._rounded(building.roof_points),
        }

    def _rounded(self, coordinates) -> list[list[float]]:
        """Return the coordinates as lists of numbers rounded to centimetres."""
        return np.round(np.asarray(coordinates, dtype=float), self.DECIMALS).tolist()
