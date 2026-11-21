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

from pvcompute.data_models import BuildingPoints, Footprint, PvgisTable


class InputJsonWriter:
    DECIMALS = 2

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, table: PvgisTable, buildings: Iterable[BuildingPoints]) -> None:
        document = {
            "pvgis": table.to_dict(),
            "buildings": [self._building_entry(b) for b in buildings],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(document, f)

    def _building_entry(self, building: BuildingPoints) -> dict:
        return {
            "id": building.id,
            "footprint": self._footprint_coords(building.footprint),
            "ground_points": self._points(building.ground_points),
            "roof_points": self._points(building.roof_points),
        }

    def _footprint_coords(self, footprint: Footprint) -> list[list[float]]:
        coords = np.round(np.asarray(footprint.polygon.exterior.coords)[:-1], self.DECIMALS)
        # Rounding can merge neighbouring corners; drop the repeats (cyclically).
        distinct = np.any(coords != np.roll(coords, 1, axis=0), axis=1)
        return coords[distinct].tolist()

    def _points(self, points: np.ndarray) -> list[list[float]]:
        return np.round(points, self.DECIMALS).tolist()
