"""Reads building outlines from BDOT10k.

BDOT10k is the official Polish topographic database. This file opens its building layer (OT_BUBD_A),
keeps only the buildings in the chosen area and returns each one as a Footprint: the building ID
(`lokalnyId`) and its outline seen from above. Works with GML, GeoPackage and Shapefile files.

Design doc: 2.1, block "Wczytanie obrysów"; 2.4 (GeoPandas reads BDOT10k and converts coordinates).
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

from pvcompute.area import PROJECT_CRS, Area
from pvcompute.data_models import Footprint

log = logging.getLogger(__name__)


class Bdot10kReader:
    """Reads the building outlines of one area from a BDOT10k file."""

    BUILDING_LAYER_MARK = "BUBD"

    def __init__(self, path: str | Path, layer: str | None = None, id_column: str | None = None):
        """Open a BDOT10k file.

        `layer` and `id_column` are found automatically; pass them only when that fails
        (a file with several building layers, an unusual name of the ID column).
        """
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"BDOT10k file not found: {self.path}")
        self.layer = layer or self._find_building_layer()
        self.id_column = id_column

    def read(self, area: Area) -> list[Footprint]:
        """Return the outlines of all buildings that belong to `area`.

        A building belongs to the area when a point inside its outline lies in the area.
        So a building on the edge between two areas goes to exactly one of them.
        The file may use another coordinate system; GeoPandas converts the area to it
        for reading and the outlines back to EPSG:2180.
        """
        area_shape = gpd.GeoSeries([area.to_polygon()], crs=PROJECT_CRS)
        buildings = gpd.read_file(self.path, layer=self.layer, bbox=area_shape)
        if buildings.crs is None:
            raise ValueError(f"{self.path}: the file does not say which coordinate system it uses")
        if buildings.empty:
            return []
        buildings = buildings.to_crs(PROJECT_CRS)
        id_column = self.id_column or self._find_id_column(list(buildings.columns))

        area_polygon = area.to_polygon()
        footprints: list[Footprint] = []
        used_ids: set[str] = set()
        for raw_id, geometry in zip(buildings[id_column], buildings.geometry):
            if pd.isna(raw_id) or geometry is None:
                continue
            building_id = str(raw_id).strip()
            polygon = self._to_single_polygon(geometry)
            if polygon is None:
                log.warning("building %s has no area, skipped", building_id)
                continue
            if not area_polygon.contains(polygon.representative_point()):
                continue
            if building_id in used_ids:
                log.warning("building ID %s appears twice, keeping the first one", building_id)
                continue
            used_ids.add(building_id)
            footprints.append(Footprint(building_id, polygon))
        return footprints

    def _find_building_layer(self) -> str | None:
        """Return the name of the building layer (the one with "BUBD" in its name); None when the file has one layer."""
        layer_names = [str(name) for name in gpd.list_layers(self.path)["name"]]
        if len(layer_names) <= 1:
            return None
        building_layers = [name for name in layer_names if self.BUILDING_LAYER_MARK in name.upper()]
        if len(building_layers) != 1:
            raise ValueError(f"{self.path}: cannot tell which layer holds buildings: {layer_names}; pass `layer`")
        return building_layers[0]

    @staticmethod
    def _find_id_column(column_names: list[str]) -> str:
        """Return the column with the BDOT10k ID (`lokalnyId`; exports spell it e.g. `LOKALNYID`, `lokalny_id`)."""
        for name in column_names:
            if name.lower().replace("_", "").endswith("lokalnyid"):
                return name
        raise ValueError(f"no BDOT10k ID column (lokalnyId) among {column_names}; pass `id_column`")

    @classmethod
    def _to_single_polygon(cls, geometry: BaseGeometry) -> Polygon | None:
        """Turn a raw BDOT10k outline into one simple polygon; None when it has no area.

        input.json describes an outline as one list of corners, so: heights are removed,
        broken shapes are repaired, from an outline made of several parts the largest part is kept,
        holes are dropped, and the corners go counter-clockwise (as in the design doc example).
        """
        geometry = shapely.make_valid(shapely.force_2d(geometry))
        polygons = cls._polygons_in(geometry)
        if not polygons:
            return None
        largest = max(polygons, key=lambda polygon: polygon.area)
        return orient(Polygon(largest.exterior), sign=1.0)

    @classmethod
    def _polygons_in(cls, geometry: BaseGeometry) -> list[Polygon]:
        """Return all polygons with a non-zero area found in `geometry`, also inside collections of shapes."""
        if isinstance(geometry, Polygon):
            return [geometry] if geometry.area > 0 else []
        parts = getattr(geometry, "geoms", [])
        return [polygon for part in parts for polygon in cls._polygons_in(part)]
