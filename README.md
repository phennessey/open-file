# Open File Archive (OFA)

**A universal file format for the AI programming age.** OFA is an
open-source, self-describing package format. Any program can open an `.ofa`
file and read what's inside it.

## Built on Frictionless Data Package

OFA stands on the work of the [Frictionless Data](https://frictionlessdata.io/)
project at the Open Knowledge Foundation. The manifest inside every `.ofa`
file is a standard [Frictionless Data Package](https://datapackage.org/)
descriptor, `datapackage.json`, used exactly as their spec defines it.
Frictionless had already solved how to describe a set of data files, so we
didn't reinvent it. Any Frictionless tool can read an OFA manifest.

What OFA adds is the part Data Package leaves open: one file that holds
everything. The Frictionless community has asked for that since 2014, in
[discussion #911](https://github.com/frictionlessdata/datapackage/discussions/911),
and OFA builds on the ideas raised there:

- OFA defines the ZIP container, the `.ofa` file type, and its media type.
- It uses Frictionless's own `compression` property for compressed files.
- It opens existing zipped Data Packages, including GitHub's "Download ZIP"
  archives, and converts them to OFA with one command.
- It reads a package over HTTP without downloading the whole file.

OFA's few extras, such as roles and links between files, live in private
`_ofa` properties that Data Package allows.
[RFC 0002](rfcs/0002-use-frictionless-data-package.md) and
[RFC 0003](rfcs/0003-frictionless-bundling-ideas.md) have the details. We've
also drafted a [Zipped Data Package recipe](recipes/zipped-data-package.md)
to offer back to Frictionless.

## Why this exists

We're seeing an explosion of AI-assisted apps and tools, and each one invents
its own file format. Without a universal standard, we'll be buried in
incompatible file types.

OFA is a new philosophy. Instead of inventing a format, a tool writes an OFA
package:

- Its data goes in as ordinary files: JSON, CSV, PNG, Parquet, whatever fits.
- A Frictionless manifest, `datapackage.json`, says what each file is, how
  it's compressed, and which schema describes it.
- The schemas go inside the package too.

Another AI-built tool can open the package and understand it. So can any
other program, or a person with `unzip` and a text editor. The manifest holds
what an LLM or a human needs to write a reader: media types, schemas, and
roles, all in digestible form.

## What it looks like

```
notes-app.ofa
├── mimetype                     "application/vnd.ofa+zip"
├── datapackage.json             the manifest
├── data/notes.json              the notes
├── schemas/notes.schema.json    JSON Schema for the notes
├── data/attachments/sketch.png
└── preview/thumbnail.png
```

```json
{
  "$schema": "https://ofa-format.org/profiles/0.3/datapackage.json",
  "title": "Kitchen renovation notes",
  "_ofa": { "version": "0.3", "primary": "notes" },
  "resources": [
    {
      "name": "notes",
      "path": "data/notes.json",
      "mediatype": "application/json",
      "bytes": 502,
      "hash": "sha256:…",
      "_ofa": { "schema": { "type": "json-schema", "resource": "notes-schema" } }
    },
    {
      "name": "notes-schema",
      "path": "schemas/notes.schema.json",
      "mediatype": "application/schema+json",
      "bytes": 992,
      "hash": "sha256:…",
      "_ofa": { "role": "schema", "describes": ["notes"] }
    }
  ]
}
```

Everything outside `_ofa` is plain Data Package. The `_ofa` objects hold what
OFA adds: roles, links between files, and the spec version.

## Design in five rules

1. **Any program can list any package.** ZIP and JSON are all it takes.
2. **Describe, don't execute.** Schemas, never code. Optional sandboxed
   decoders stay out of the default path.
3. **Reuse what exists.** Frictionless Data Package, IANA media types, HTTP
   content codings, JSON Schema, Avro, Protobuf, Table Schema, SHA-256.
4. **Every entry gets a hash.** Sign the manifest and you have signed the
   package.
5. **Ignore what you don't know**, unless the package says you must
   understand it.

## Quick start

The reference tool needs Python 3.10 or later and nothing else. `zst`
compression needs Python 3.14.

```bash
python3 tools/ofa.py ls examples/sensor-log.ofa
```

```bash
python3 tools/ofa.py verify examples/sensor-log.ofa
```

```bash
python3 tools/ofa.py cat examples/sensor-log.ofa readings
```

Build your own from a folder containing a `datapackage.json` template:

```bash
python3 tools/ofa.py pack examples/src/sensor-log my-log.ofa
```

Already have a Data Package, as a folder or a ZIP? Turn it into an OFA file:

```bash
python3 tools/ofa.py adopt my-datapackage.zip my-data.ofa
```

List a package on the web without downloading all of it:

```bash
python3 tools/ofa.py ls https://raw.githubusercontent.com/phennessey/open-file/main/examples/sensor-log.ofa
```

No tool at all? Not a problem — it's just a ZIP file:

```bash
unzip -p examples/sensor-log.ofa datapackage.json
```

## Repository layout

| Path | Contents |
|---|---|
| [`SPEC.md`](SPEC.md) | The living specification |
| [`profiles/`](profiles/) | The OFA profile: a JSON Schema that extends the Data Package profile |
| [`examples/`](examples/) | Sample packages and the folders they were built from |
| [`tools/ofa.py`](tools/ofa.py) | Reference inspector, verifier, and packer |
| [`research/survey.md`](research/survey.md) | Survey of OPC, EPUB, JAR, RO-Crate, Avro, Matroska, MCAP, HDF5, and others |
| [`rfcs/`](rfcs/) | Proposals for changes, including [RFC 0001](rfcs/0001-extension-and-media-type.md) on the name, [RFC 0002](rfcs/0002-use-frictionless-data-package.md) on using Data Package, and [RFC 0003](rfcs/0003-frictionless-bundling-ideas.md) on ideas from the Frictionless community |
| [`recipes/`](recipes/) | A draft Zipped Data Package recipe, written for the Frictionless site |
| [`NEXT_STEPS.md`](NEXT_STEPS.md) | Roadmap and open questions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to propose changes |

## How OFA relates to other formats

OFA does not replace Parquet, PNG, SQLite, or MCAP. It carries them. If your
data already has a good self-describing format, put that file in a package
and let the manifest say what it is. OFA fills the gap for everything that
currently ends up as an undocumented ZIP or a bespoke binary.

### Frictionless and RO-Crate

**Frictionless Data Package** is OFA's foundation. See
[Built on Frictionless Data Package](#built-on-frictionless-data-package).

**[RO-Crate](https://www.researchobject.org/ro-crate/)** describes research
data: who made it, how, and why, in JSON-LD. It doesn't tell a reader how to
decode the bytes in each file. OFA handles decoding. If you need RO-Crate's
richer metadata, put `ro-crate-metadata.json` inside the package as a
resource with the `metadata` role.

The [survey](research/survey.md) explains what OFA borrows from each
existing format.

## Open for public comment

Draft 0.3 is open for public comment. Nothing is final, and we'll change the
spec based on what you tell us. We want to hear from anyone who might read,
write or build on OFA files.

- **Questions, ideas, and general feedback:** start a thread in
  [Discussions](https://github.com/phennessey/open-file/discussions).
- **Something wrong, missing, or unclear in the spec:** [open an
  issue](https://github.com/phennessey/open-file/issues).
- **A specific change to the spec:** propose it as an [RFC](rfcs/).

## License

- Specification text, schemas, and examples: [CC BY 4.0](LICENSE-SPEC.md)
- Code in `tools/`: [Apache License 2.0](LICENSE)
