"""Reads the C++ results so they can be saved to the database.

Takes the roofs and solar results from output.json and the building outlines from input.json
(output.json has no outlines) and joins them by building ID into BuildingResult objects.
In output.json every roof face is described in two lists, `roof.faces` (its corners) and
`roof.pv` (its solar data), in the same order; this file pairs them into one RoofFace.

Design doc: 2.5 "Zapis wyników do bazy"; 3.2.
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import Polygon

from pvcompute.data_models import BuildingResult, Footprint, RoofFace


class OutputJsonReader:
    """Reads output.json and the outlines from input.json and joins them per building."""

    def __init__(self, input_json_path: str | Path, output_json_path: str | Path):
        """Set the paths of input.json (outlines) and output.json (roofs and solar data)."""
        self.input_json_path = Path(input_json_path)
        self.output_json_path = Path(output_json_path)

    def read(self) -> list[BuildingResult]:
        """Return every building of output.json with its outline and roof."""
        footprints = self._read_footprints()
        results = []
        for building in self._load_json(self.output_json_path)["buildings"]:
            building_id = building["id"]
            if building_id not in footprints:
                raise ValueError(f"building {building_id} is in output.json but not in input.json")
            roof = building["roof"]
            if len(roof["faces"]) != len(roof["pv"]):
                raise ValueError(f"building {building_id}: roof.faces and roof.pv have different lengths")
            results.append(
                BuildingResult(
                    footprint=footprints[building_id],
                    z_ground=building["z_ground"],
                    roof_vertices=roof["vertices"],
                    roof_faces=[self._roof_face(corners, pv) for corners, pv in zip(roof["faces"], roof["pv"])],
                    pv_energy=building["pv_energy"],
                )
            )
        return results

    def _read_footprints(self) -> dict[str, Footprint]:
        """Return the outlines from input.json, keyed by building ID."""
        buildings = self._load_json(self.input_json_path)["buildings"]
        return {b["id"]: Footprint(b["id"], Polygon(b["footprint"])) for b in buildings}

    @staticmethod
    def _roof_face(corner_numbers: list[int], pv: dict) -> RoofFace:
        """Join one entry of `roof.faces` (corner numbers) with the matching entry of `roof.pv` (solar data)."""
        return RoofFace(
            vertex_nos=list(corner_numbers),
            area=pv["area"],
            slope=pv["slope"],
            azimuth=pv["azimuth"],
            irradiation=pv["irradiation"],
            energy=pv["energy"],
        )

    @staticmethod
    def _load_json(path: Path) -> dict:
        """Read a JSON file."""
        with open(path, encoding="utf-8") as file:
            return json.load(file)
