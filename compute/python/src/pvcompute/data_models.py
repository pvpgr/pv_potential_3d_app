"""The data objects that the rest of the code passes around.

These classes only hold data; they do not read, write or calculate anything.
- Before the C++ calculation (what goes into input.json): Footprint (building outline),
  PointCloud (LiDAR points), BuildingPoints (one building with its points) and
  PvgisTable (sunlight table from PVGIS).
- After the C++ calculation (what comes from output.json and goes to the database):
  RoofFace (one roof face with its solar data) and BuildingResult (one building with its roof).

Points are arrays with one row per point: x, y, z (EPSG:2180, heights in metres above sea level).
Field names follow input.json, output.json and the database columns.

Design doc: 2.3 (input.json, output.json); 3.2 (database tables).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon


@dataclass(frozen=True)
class Footprint:
    """A building outline seen from above: the BDOT10k building ID and a single polygon."""

    building_id: str
    polygon: Polygon


@dataclass
class PointCloud:
    """LiDAR points of an area: ground points (class 2) and building points (class 6)."""

    ground_points: np.ndarray
    building_points: np.ndarray


@dataclass
class BuildingPoints:
    """One building ready for input.json: its outline, the ground points around it and the roof points inside it."""

    footprint: Footprint
    ground_points: np.ndarray
    roof_points: np.ndarray


@dataclass
class PvgisTable:
    """The PVGIS sunlight table for the center of the area: one row per slope, one column per azimuth."""

    lat: float
    lon: float
    slopes: list[float]
    azimuths: list[float]
    irradiation: list[list[float]]
    yield_per_kwp: list[list[float]]


@dataclass(frozen=True)
class RoofFace:
    """One roof face from output.json: its corner numbers (`roof.faces`) and its solar data (`roof.pv`)."""

    vertex_nos: list[int]
    area: float
    slope: float
    azimuth: float
    irradiation: float
    energy: float


@dataclass(frozen=True)
class BuildingResult:
    """One building after the C++ calculation: its outline (from input.json) and its roof (from output.json)."""

    footprint: Footprint
    z_ground: float
    roof_vertices: list[list[float]]
    roof_faces: list[RoofFace]
    pv_energy: float
