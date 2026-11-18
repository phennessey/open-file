# Examples

Each `.ofa` file here was built from the folder of the same name in `src/`
with `tools/ofa.py pack`. The builds are reproducible: packing the same
folder twice gives byte-identical files.

| Package | Shows |
|---|---|
| [`hello.ofa`](hello.ofa) | The smallest useful package: one text resource. |
| [`sensor-log.ofa`](sensor-log.ofa) | gzip-encoded NDJSON with a JSON Schema, CSV with a Frictionless Table Schema, README and licence resources, package metadata. |
| [`notes-app.ofa`](notes-app.ofa) | An application save file: JSON state with a schema, an image attachment, a thumbnail, and app-private data under `extensions`. |

Rebuild all three:

```bash
for n in hello sensor-log notes-app; do python3 tools/ofa.py pack examples/src/$n examples/$n.ofa; done
```

In `src/sensor-log/datapackage.json`, the `readings` resource has a
`source` member.
That member belongs to the packer's template format, not to the spec: it
tells `pack` to read `raw/readings.ndjson`, gzip it, and store the result at
`path`.
