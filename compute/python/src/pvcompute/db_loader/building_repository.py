"""Saves buildings to the PostgreSQL/PostGIS database.

Every building is written into three tables (the tables themselves are created by the database module):
  building    - one row per building: ID, outline, ground height, yearly energy of the whole roof
  roof_vertex - one row per roof corner: its number and x, y, z
  roof_face   - one row per roof face: its corner numbers and solar data
A building that is already in the database is updated: its row is overwritten and its roof
corners and faces are replaced, because a new calculation can give a different roof.
Everything is saved in one transaction: either all buildings are saved or none.

Design doc: 2.5 "Zapis wyników do bazy"; 3.2.
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from pvcompute.data_models import BuildingResult


class BuildingRepository:
    """Writes BuildingResult objects to the tables building, roof_vertex and roof_face."""

    INSERT_OR_UPDATE_BUILDING = """
        INSERT INTO building (id, footprint, z_ground, pv_energy)
        VALUES (%s, ST_GeomFromText(%s, 2180), %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET footprint = EXCLUDED.footprint,
            z_ground = EXCLUDED.z_ground,
            pv_energy = EXCLUDED.pv_energy
    """
    DELETE_OLD_VERTICES = "DELETE FROM roof_vertex WHERE building_id = ANY(%s)"
    DELETE_OLD_FACES = "DELETE FROM roof_face WHERE building_id = ANY(%s)"
    INSERT_VERTEX = "INSERT INTO roof_vertex (building_id, vertex_no, x, y, z) VALUES (%s, %s, %s, %s, %s)"
    INSERT_FACE = """
        INSERT INTO roof_face (building_id, face_no, vertex_nos, area, slope, azimuth, irradiation, energy)
        VALUES (%s, %s, %s::int[], %s, %s, %s, %s, %s)
    """

    def __init__(self, connection: psycopg.Connection):
        """Use an open database connection (opening and closing it is the caller's job)."""
        self.connection = connection

    def save(self, buildings: Sequence[BuildingResult]) -> None:
        """Save all buildings in one transaction: either all of them are saved or none."""
        if not buildings:
            return
        building_ids = [b.footprint.building_id for b in buildings]
        building_rows = [
            (b.footprint.building_id, b.footprint.polygon.wkt, b.z_ground, b.pv_energy)
            for b in buildings
        ]
        vertex_rows = [
            (b.footprint.building_id, vertex_no, x, y, z)
            for b in buildings
            for vertex_no, (x, y, z) in enumerate(b.roof_vertices)
        ]
        face_rows = [
            (b.footprint.building_id, face_no, f.vertex_nos, f.area, f.slope, f.azimuth, f.irradiation, f.energy)
            for b in buildings
            for face_no, f in enumerate(b.roof_faces)
        ]
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.executemany(self.INSERT_OR_UPDATE_BUILDING, building_rows)
            cursor.execute(self.DELETE_OLD_VERTICES, (building_ids,))
            cursor.execute(self.DELETE_OLD_FACES, (building_ids,))
            if vertex_rows:
                cursor.executemany(self.INSERT_VERTEX, vertex_rows)
            if face_rows:
                cursor.executemany(self.INSERT_FACE, face_rows)
