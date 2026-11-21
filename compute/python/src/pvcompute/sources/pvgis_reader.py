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
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pvcompute.coordinates import BoundingBox
from pvcompute.data_models import PvgisAxes, PvgisTable

log = logging.getLogger(__name__)


class PvgisError(RuntimeError):
    pass


class PvgisHttpClient:
    """GET returning parsed JSON, with retries on rate limiting and server errors."""

    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, attempts: int = 3, timeout: float = 60):
        self.attempts = attempts
        self.timeout = timeout

    def get(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": "pvcompute/0.1"})
        for attempt in range(1, self.attempts + 1):
            last = attempt == self.attempts
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                if exc.code not in self.RETRY_STATUS or last:
                    raise PvgisError(f"PVGIS HTTP {exc.code}: {self._error_message(body)}") from exc
            except URLError as exc:
                if last:
                    raise PvgisError(f"PVGIS unreachable: {exc.reason}") from exc
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    @staticmethod
    def _error_message(body: str) -> str:
        try:
            return json.loads(body)["message"]
        except (ValueError, KeyError, TypeError):
            return body[:300]


class PvgisReader:
    """Fetches the PVGIS table from the PVcalc service."""

    URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
    LOSS = 14.0
    """System losses in %, the PVGIS default (the design doc does not set it)."""

    def __init__(self, http: PvgisHttpClient | None = None):
        self.http = http or PvgisHttpClient()

    def read(self, area: BoundingBox, axes: PvgisAxes) -> PvgisTable:
        """Table for the center of `area` (EPSG:2180)."""
        lat, lon = area.center_wgs84()
        log.info("fetching PVGIS table for lat=%s lon=%s (%d requests)", lat, lon, axes.request_count)
        width = len(axes.azimuths)
        irradiation: list[list[float]] = []
        yield_: list[list[float]] = []
        for slope in axes.slopes:
            if slope == 0:
                h, e = self._query(lat, lon, 0, 0)
                row_h, row_e = [h] * width, [e] * width
            else:
                values = [self._query(lat, lon, slope, self.azimuth_to_aspect(a)) for a in axes.azimuths]
                row_h, row_e = [v[0] for v in values], [v[1] for v in values]
            irradiation.append(row_h)
            yield_.append(row_e)
        return PvgisTable(lat, lon, axes, irradiation, yield_)

    @staticmethod
    def azimuth_to_aspect(azimuth: float) -> float:
        """Compass azimuth (0 = N, clockwise) to PVGIS aspect (0 = S, -90 = E, 90 = W)."""
        aspect = (azimuth - 180) % 360
        return aspect - 360 if aspect >= 180 else aspect

    def _query(self, lat: float, lon: float, slope: float, aspect: float) -> tuple[float, float]:
        params = {
            "lat": lat,
            "lon": lon,
            "peakpower": 1,
            "loss": self.LOSS,
            "angle": slope,
            "aspect": aspect,
            "outputformat": "json",
        }
        data = self.http.get(f"{self.URL}?{urlencode(params)}")
        try:
            fixed = data["outputs"]["totals"]["fixed"]
            return round(float(fixed["H(i)_y"]), 1), round(float(fixed["E_y"]), 1)
        except (KeyError, TypeError, ValueError) as exc:
            raise PvgisError(f"unexpected PVGIS response for slope={slope}, aspect={aspect}") from exc
