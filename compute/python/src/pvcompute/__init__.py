"""The Python part of the compute module.

It prepares the data for the C++ program (reads BDOT10k, LiDAR and PVGIS and writes input.json)
and, after the C++ program has run, saves its results (output.json) to the database.

Design doc: chapter 2.
"""
