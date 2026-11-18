# Rooftop weather stations, 1 November 2026

Two masts on one roof, sampled every six hours.

- `data/readings.ndjson.gz`: one JSON object per reading, gzip-compressed.
  The schema is `schemas/reading.schema.json`.
- `data/stations.csv`: station locations. The schema is
  `schemas/stations.table.json` (Frictionless Table Schema).

The south mast lost power at 18:00, so its temperature and humidity are null.
