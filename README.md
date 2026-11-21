# pv_potential_3d_app

Web application that shows buildings on an interactive 3D map with the solar (PV) potential of their roofs.
Roofs are reconstructed from LiDAR points and BDOT10k building outlines; sunlight data comes from PVGIS.
Architecture: design doc `Projekt_Systemu.pdf`.

| Folder | What it is | Design doc |
|---|---|---|
| `compute/` | compute module: data preparation in Python, roof reconstruction and PV calculation in C++, loading results into the database | 2 |
| `database/` | PostgreSQL + PostGIS schema and queries | 3 |
| `api/` | server API, the only path from the browser to the database | 1, 3.3, 4.6 |
| `frontend/` | interactive 3D map in the browser | 4 |
| `infra/` | deployment: Docker Compose, proxy, server, CI/CD | 5 |
