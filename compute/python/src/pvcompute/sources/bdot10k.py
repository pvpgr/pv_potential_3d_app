"""Reads building outlines from BDOT10k.

BDOT10k is the official Polish topographic database. This file opens its building layer (OT_BUBD_A),
keeps only the buildings in the chosen area and returns each one as a Footprint: the building ID
and its outline seen from above. Works with GML, GeoPackage and Shapefile files.

Design doc: 2.1, block "Wczytanie obrysów".
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd

from pvcompute.geo import TARGET_CRS, BoundingBox
from pvcompute.models import Footprint

log = logging.getLogger(__name__)


class Bdot10kReader:
    BUILDING_LAYER_HINT = "BUBD"

    def __init__(self, path: str | Path, layer: str | None = None, id_field: str | None = None):
        """`layer` and `id_field` are needed only when they cannot be detected (several layers, unusual column name)."""
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"BDOT10k file not found: {self.path}")
        self.layer = layer or self._find_building_layer()
        self.id_field = id_field

    def read(self, area: BoundingBox) -> list[Footprint]:
        """Footprints of the buildings belonging to `area` (EPSG:2180).

        A building belongs to the area when an interior point of its footprint lies inside it,
        so adjacent areas never share a building.
        """
        # GeoPandas converts a bbox given as a GeoSeries to the layer's own CRS.
        bbox = gpd.GeoSeries([area.to_polygon()], crs=TARGET_CRS)
        gdf = gpd.read_file(self.path, layer=self.layer, bbox=bbox)
        if gdf.crs is None:
            raise ValueError(f"{self.path}: layer has no coordinate reference system")
        if gdf.empty:
            return []
        gdf = gdf.to_crs(TARGET_CRS)
        id_field = self.id_field or self._detect_id_field(list(gdf.columns))

        area_polygon = area.to_polygon()
        footprints: list[Footprint] = []
        seen: set[str] = set()
        for raw_id, geometry in zip(gdf[id_field], gdf.geometry):
            building_id = "" if raw_id is None else str(raw_id).strip()
            if geometry is None or geometry.is_empty or building_id in ("", "nan"):
                continue
            footprint = Footprint.from_geometry(building_id, geometry)
            if footprint is None or not area_polygon.contains(footprint.polygon.representative_point()):
                continue
            if building_id in seen:
                log.warning("duplicate building id %s, keeping the first one", building_id)
                continue
            seen.add(building_id)
            footprints.append(footprint)
        return footprints

    def _find_building_layer(self) -> str | None:
        layers = [str(name) for name in gpd.list_layers(self.path)["name"]]
        if len(layers) <= 1:
            return None
        matches = [name for name in layers if self.BUILDING_LAYER_HINT in name.upper()]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"{self.path}: cannot choose the building layer from {layers}; pass it explicitly")

    @staticmethod
    def _detect_id_field(columns: list[str]) -> str:
        """BDOT10k identifies objects by `lokalnyId`; GML/SHP exports spell it differently."""
        candidates = [c for c in columns if c.lower().replace("_", "").endswith("lokalnyid")]
        if not candidates:
            raise ValueError(f"no BDOT10k id column (lokalnyId) among {columns}; pass it explicitly")
        return candidates[0]
