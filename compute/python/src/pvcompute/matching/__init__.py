"""Giving each building the LiDAR points that belong to it, and thinning those points out.

point_matcher.py picks the ground and roof points of every building (design doc 2.1, block "Dopasowanie punktów");
point_thinner.py keeps at most one point per small square, so input.json is smaller (not in the design doc).
"""
