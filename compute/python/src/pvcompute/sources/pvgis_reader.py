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
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pvcompute.area import Area
from pvcompute.data_models import PvgisTable


class PvgisError(RuntimeError):
    """PVGIS could not be reached or returned an error."""


class PvgisReader:
    """Downloads the PVGIS sunlight table for the center of an area.

    The design doc does not say for which slopes and azimuths the table is made (its example uses
    slopes 0, 30, 40 and azimuths 0, 90, 180, 270). Here: every 10° of slope and every 30° of azimuth,
    1 + 9 x 12 = 109 questions to PVGIS. Both lists are increasing, because C++ takes values
    between neighbouring entries.
    """

    URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
    SLOPES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    AZIMUTHS = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
    SYSTEM_LOSS_PERCENT = 14.0
    TIMEOUT_SECONDS = 60
    ATTEMPTS = 4
    RETRY_WAIT_SECONDS = 3
    RETRY_HTTP_CODES = (429, 500, 502, 503, 504, 529)

    def read(self, area: Area) -> PvgisTable:
        """Download the table for the center of `area`: one value per slope (row) and compass azimuth (column).

        A flat surface (slope 0) gets the same sun from every direction, so it is asked for only once.
        """
        lat, lon = area.center_lat_lon()
        irradiation: list[list[float]] = []
        yield_per_kwp: list[list[float]] = []
        for slope in self.SLOPES:
            if slope == 0:
                row = [self._ask_pvgis(lat, lon, slope=0, aspect=0)] * len(self.AZIMUTHS)
            else:
                row = [self._ask_pvgis(lat, lon, slope, self.compass_to_pvgis_aspect(a)) for a in self.AZIMUTHS]
            irradiation.append([sunlight for sunlight, _ in row])
            yield_per_kwp.append([energy for _, energy in row])
        return PvgisTable(lat, lon, list(self.SLOPES), list(self.AZIMUTHS), irradiation, yield_per_kwp)

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
        """Download `url` and return its JSON content; on failure raise PvgisError with the reason.

        PVGIS sometimes drops a connection or answers "busy" (HTTP 429, 5xx), so such a question
        is asked again, up to ATTEMPTS times, waiting a bit longer each time. Other errors,
        e.g. "Location over the sea", stop at once with the answer from PVGIS.
        """
        request = Request(url, headers={"User-Agent": "pvcompute/0.1"})
        for attempt in range(1, self.ATTEMPTS + 1):
            try:
                with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code not in self.RETRY_HTTP_CODES or attempt == self.ATTEMPTS:
                    raise PvgisError(f"PVGIS error {error.code}: {error.read().decode('utf-8', 'replace')}") from error
            except OSError as error:
                if attempt == self.ATTEMPTS:
                    raise PvgisError(f"PVGIS cannot be reached: {error}") from error
            time.sleep(self.RETRY_WAIT_SECONDS * attempt)
        raise PvgisError("PVGIS: no answer")
