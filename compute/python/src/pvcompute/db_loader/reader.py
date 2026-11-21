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

from pvcompute.models import BuildingResult, Footprint, RoofFace


class ComputeResultReader:
    def __init__(self, input_path: str | Path, output_path: str | Path):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)

    def read(self) -> list[BuildingResult]:
        footprints = self._read_footprints()
        results = []
        for building in self._load(self.output_path)["buildings"]:
            building_id = building["id"]
            footprint = footprints.get(building_id)
            if footprint is None:
                raise ValueError(f"building {building_id} from {self.output_path} is missing in {self.input_path}")
            roof = building["roof"]
            if len(roof["faces"]) != len(roof["pv"]):
                raise ValueError(f"building {building_id}: roof.faces and roof.pv differ in length")
            results.append(
                BuildingResult(
                    footprint=footprint,
                    z_ground=building["z_ground"],
                    vertices=roof["vertices"],
                    faces=[self._face(vertex_nos, pv) for vertex_nos, pv in zip(roof["faces"], roof["pv"])],
                    pv_energy=building["pv_energy"],
                )
            )
        return results

    def _read_footprints(self) -> dict[str, Footprint]:
        buildings = self._load(self.input_path)["buildings"]
        return {b["id"]: Footprint(b["id"], Polygon(b["footprint"])) for b in buildings}

    @staticmethod
    def _face(vertex_nos: list[int], pv: dict) -> RoofFace:
        return RoofFace(
            vertex_nos=list(vertex_nos),
            area=pv["area"],
            slope=pv["slope"],
            azimuth=pv["azimuth"],
            irradiation=pv["irradiation"],
            energy=pv["energy"],
        )

    @staticmethod
    def _load(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
