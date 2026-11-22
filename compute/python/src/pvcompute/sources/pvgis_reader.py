"""Downloads the sunlight table from PVGIS.

PVGIS is a free web service of the European Commission. For a place, a roof slope and a roof
direction it says how much sun the surface gets in a year (kWh/m²) and how much energy
1 kWp of panels produces in a year (kWh). A small area has practically the same climate
everywhere, so the table is downloaded once, for the center of the area, for every chosen
slope and direction - not separately for each building. The table then goes into input.json.

Watch out: PVGIS counts direction from south (0 = south, -90 = east, 90 = west), while the project
uses compass directions (0 = north, 90 = east, 180 = south, 270 = west). This file converts between them.

Design doc: 2.1, block "Pobranie danych PVGIS"; 2.4 "Dane z PVGIS".
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pvcompute.area import Area
from pvcompute.data_models import PvgisTable


class PvgisError(RuntimeError):
    """PVGIS could not be reached or returned an error."""


class PvgisReader:
    """Downloads the PVGIS sunlight table for the center of an area."""

    URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
    SYSTEM_LOSS_PERCENT = 14.0
    TIMEOUT_SECONDS = 60

    def read(self, area: Area, slopes: list[float], azimuths: list[float]) -> PvgisTable:
        """Download the table for the center of `area`: one value per slope and compass azimuth.

        Both lists must be increasing, because C++ takes values between neighbouring entries.
        A flat surface (slope 0) gets the same sun from every direction, so it is asked for only once.
        """
        self._check_increasing("slopes", slopes)
        self._check_increasing("azimuths", azimuths)
        lat, lon = area.center_lat_lon()
        irradiation: list[list[float]] = []
        yield_per_kwp: list[list[float]] = []
        for slope in slopes:
            if slope == 0:
                flat_result = self._ask_pvgis(lat, lon, slope=0, aspect=0)
                row = [flat_result] * len(azimuths)
            else:
                row = [self._ask_pvgis(lat, lon, slope, self.compass_to_pvgis_aspect(a)) for a in azimuths]
            irradiation.append([sunlight for sunlight, _ in row])
            yield_per_kwp.append([energy for _, energy in row])
        return PvgisTable(lat, lon, list(slopes), list(azimuths), irradiation, yield_per_kwp)

    @staticmethod
    def compass_to_pvgis_aspect(azimuth: float) -> float:
        """Convert a compass direction (0 = north, 90 = east) to the PVGIS one (0 = south, -90 = east, 90 = west)."""
        aspect = (azimuth - 180) % 360
        return aspect - 360 if aspect >= 180 else aspect

    def _ask_pvgis(self, lat: float, lon: float, slope: float, aspect: float) -> tuple[float, float]:
        """Ask PVGIS about one surface; return (yearly sunlight in kWh/m², yearly energy of 1 kWp in kWh).

        System losses (cables, inverter etc.) are set to 14%, the PVGIS default; the design doc does not set them.
        """
        query = {
            "lat": lat,
            "lon": lon,
            "peakpower": 1,
            "loss": self.SYSTEM_LOSS_PERCENT,
            "angle": slope,
            "aspect": aspect,
            "outputformat": "json",
        }
        answer = self._download_json(f"{self.URL}?{urlencode(query)}")
        try:
            yearly = answer["outputs"]["totals"]["fixed"]
            return round(float(yearly["H(i)_y"]), 1), round(float(yearly["E_y"]), 1)
        except (KeyError, TypeError, ValueError) as error:
            raise PvgisError(f"unexpected PVGIS answer for slope={slope}, aspect={aspect}") from error

    def _download_json(self, url: str) -> dict:
        """Download `url` and return its JSON content; on failure raise PvgisError with the PVGIS message."""
        request = Request(url, headers={"User-Agent": "pvcompute/0.1"})
        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                return json.load(response)
        except HTTPError as error:
            raise PvgisError(f"PVGIS error {error.code}: {self._error_message(error)}") from error
        except URLError as error:
            raise PvgisError(f"PVGIS cannot be reached: {error.reason}") from error

    @staticmethod
    def _error_message(error: HTTPError) -> str:
        """Return the explanation PVGIS sends with an error (e.g. "Location over the sea")."""
        body = error.read().decode("utf-8", "replace")
        try:
            return json.loads(body)["message"]
        except (ValueError, KeyError, TypeError):
            return body[:300]

    @staticmethod
    def _check_increasing(name: str, values: list[float]) -> None:
        """Raise ValueError when `values` is empty or not strictly increasing."""
        if not values or any(next_value <= value for value, next_value in zip(values, values[1:])):
            raise ValueError(f"{name} must be a non-empty, increasing list: {values}")
