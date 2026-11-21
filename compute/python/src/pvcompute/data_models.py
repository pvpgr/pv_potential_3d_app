"""The data objects that the rest of the code passes around.

These classes only hold data and check that it makes sense; they do not read or write files.
- Before the C++ calculation (what goes into input.json): Footprint (building outline),
  PointCloud (LiDAR points), BuildingPoints (one building with its points),
  PvgisAxes and PvgisTable (sunlight table from PVGIS).
- After the C++ calculation (what comes from output.json and goes to the database):
  RoofFace (one roof face with its solar data) and BuildingResult (one building with its roof).

Design doc: 2.3 (input.json, output.json), 3.2 (database tables).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Footprint:
    """Building outline: 2D, EPSG:2180, a single ring (input.json `footprint`, table `building.footprint`)."""

    id: str
    polygon: Polygon

    @classmethod
    def from_geometry(cls, building_id: str, geometry: BaseGeometry) -> Footprint | None:
        """Normalise a raw BDOT10k geometry; None when it has no polygon area.

        input.json describes a footprint as one list of corners, so multipart outlines keep
        their largest part and holes are dropped. The ring is made counter-clockwise.
        """
        geometry = shapely.force_2d(geometry)
        if not geometry.is_valid:
            geometry = shapely.make_valid(geometry)
        parts = cls._polygon_parts(geometry)
        if not parts:
            log.warning("%s: footprint has no polygon area, skipped", building_id)
            return None
        largest = max(parts, key=lambda p: p.area)
        if len(parts) > 1:
            log.warning("%s: footprint has %d parts, keeping the largest", building_id, len(parts))
        if largest.interiors:
            log.info("%s: footprint holes dropped", building_id)
        return cls(building_id, orient(Polygon(largest.exterior), sign=1.0))

    @staticmethod
    def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
        if isinstance(geometry, Polygon):
            return [geometry] if geometry.area > 0 else []
        if hasattr(geometry, "geoms"):
            return [p for part in geometry.geoms for p in Footprint._polygon_parts(part)]
        return []


@dataclass
class PointCloud:
    """LiDAR points marked as ground and building, EPSG:2180, each array of shape (n, 3): x, y, z."""

    ground: np.ndarray
    building: np.ndarray


@dataclass
class BuildingPoints:
    """A footprint with its ground points (ring around it) and roof points (inside it)."""

    footprint: Footprint
    ground_points: np.ndarray
    roof_points: np.ndarray

    @property
    def id(self) -> str:
        return self.footprint.id


@dataclass(frozen=True)
class PvgisAxes:
    """Slopes and compass azimuths for which the PVGIS table is fetched (input.json `pvgis.slopes`, `pvgis.azimuths`).

    The C++ program takes values lying between neighbouring entries, so both axes must be strictly increasing.
    """

    slopes: tuple[float, ...]
    azimuths: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "slopes", tuple(self.slopes))
        object.__setattr__(self, "azimuths", tuple(self.azimuths))
        self._validate("slopes", self.slopes, upper=90, upper_inclusive=True)
        self._validate("azimuths", self.azimuths, upper=360, upper_inclusive=False)

    @property
    def request_count(self) -> int:
        """A flat plane (slope 0) does not depend on azimuth, so it needs one request."""
        return sum(1 if slope == 0 else len(self.azimuths) for slope in self.slopes)

    @staticmethod
    def _validate(name: str, axis: tuple[float, ...], upper: float, upper_inclusive: bool) -> None:
        if not axis:
            raise ValueError(f"{name} must not be empty")
        if any(b <= a for a, b in zip(axis, axis[1:])):
            raise ValueError(f"{name} must be strictly increasing: {list(axis)}")
        too_high = axis[-1] > upper if upper_inclusive else axis[-1] >= upper
        if axis[0] < 0 or too_high:
            raise ValueError(f"{name} out of range 0..{upper}: {list(axis)}")


@dataclass
class PvgisTable:
    """The `pvgis` object of input.json: tables slope × azimuth for the area center."""

    lat: float
    lon: float
    axes: PvgisAxes
    irradiation: list[list[float]]
    """Yearly irradiation of the plane, kWh/m²."""
    yield_: list[list[float]]
    """Yearly production of 1 kWp, kWh."""

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "slopes": list(self.axes.slopes),
            "azimuths": list(self.axes.azimuths),
            "irradiation": self.irradiation,
            "yield": self.yield_,
        }


@dataclass(frozen=True)
class RoofFace:
    """One roof face: an entry of `roof.faces` with the matching entry of `roof.pv` (table `roof_face`)."""

    vertex_nos: list[int]
    area: float
    slope: float
    azimuth: float
    irradiation: float
    energy: float


@dataclass(frozen=True)
class BuildingResult:
    """A building of output.json with its footprint from input.json (tables `building`, `roof_vertex`, `roof_face`)."""

    footprint: Footprint
    z_ground: float
    vertices: list[list[float]]
    """Roof corners [x, y, z]; the list index is `vertex_no`."""
    faces: list[RoofFace]
    """The list index is `face_no`."""
    pv_energy: float

    @property
    def id(self) -> str:
        return self.footprint.id
