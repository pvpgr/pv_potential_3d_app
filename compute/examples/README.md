# compute/examples — sample files

`input.json` is a real example of the file that the Python part writes and the C++ part reads
(design doc 2.3, example 2.6). It holds the PVGIS table and two houses from Gdańsk-Osowa:
a simple rectangle (4 corners) and a house with a more complex outline (10 corners).

It was made with `python -m pvcompute.input_builder` for the area `465640 729060 465770 729190` (EPSG:2180)
with the default settings: PVGIS table every 10° of slope and 30° of azimuth, ground ring 3 m,
points thinned to one per 25 × 25 cm. Sources: BDOT10k and LiDAR 2024 from GUGiK (open data) and PVGIS.

The program writes input.json in one line; this copy is formatted like the design doc example, for reading.
