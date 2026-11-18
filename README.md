# Open File Archive (OFA)

**An open, self-describing package format.** One ZIP file, one JSON
manifest, any number of data streams. Any program can open an `.ofa` file
and list what is inside. A program that knows common formats such as JSON,
CSV and PNG can read all of it, without format-specific code.

Status: **draft 0.1**. The spec will change. Feedback welcome through issues
and [RFCs](rfcs/).

## Why this exists

You can now ask an AI assistant for a small tool and get one in minutes: a
note keeper, a lab logger, a budget tracker. Each tool needs to save
something, and each one invents a file format to do it. Some reach for JSON,
some for SQLite, some for a ZIP with an ad-hoc layout and a made-up
extension. A year later nobody remembers what `.qnotes` contains, the tool
that wrote it is gone, and the data is stuck.

The cost of writing software has dropped. The cost of a new file format has
not: every new format needs documentation, readers in other languages,
validation and a plan for old versions. Most tools skip all of that.

OFA gives those tools a default. Instead of inventing a format, a tool
writes an OFA package:

- Its data goes in as ordinary files: JSON, CSV, PNG, Parquet, whatever fits.
- A manifest, `ofa.json`, says what each file is, how it is compressed, and
  which schema describes it.
- The schemas go inside the package too.

Another program, or another AI-generated tool, or you with `unzip` and a text
editor, can open the package and understand it. The manifest holds what an
LLM or a human needs to write a reader: media types, schemas and roles,
in a form you can read on one screen.

## What it looks like

```
notes-app.ofa
├── mimetype                     "application/vnd.ofa+zip"
├── ofa.json                    the manifest
├── data/notes.json              the notes
├── schemas/notes.schema.json    JSON Schema for the notes
├── data/attachments/sketch.png
└── preview/thumbnail.png
```

```json
{
  "ofa": "0.1",
  "title": "Kitchen renovation notes",
  "primary": "notes",
  "streams": [
    {
      "id": "notes",
      "path": "data/notes.json",
      "media_type": "application/json",
      "schema": { "type": "json-schema", "stream": "notes-schema" },
      "size": 502,
      "digest": "sha256:…"
    },
    {
      "id": "notes-schema",
      "path": "schemas/notes.schema.json",
      "media_type": "application/schema+json",
      "role": "schema",
      "describes": ["notes"],
      "size": 992,
      "digest": "sha256:…"
    }
  ]
}
```

## Design in five rules

1. **Any program can list any package.** ZIP and JSON are all it takes.
2. **Describe, don't execute.** Schemas, never code. Optional sandboxed
   decoders stay out of the default path.
3. **Reuse what exists.** IANA media types, HTTP content codings, JSON
   Schema, Avro, Protobuf, Frictionless Table Schema, SHA-256.
4. **Every entry gets a digest.** Sign the manifest and you have signed the
   package.
5. **Ignore what you don't know**, unless the package says you must
   understand it.

## Quick start

The reference tool needs Python 3.10 or later and nothing else. zstd support
needs Python 3.14.

```bash
python3 tools/ofa.py ls examples/sensor-log.ofa
```

```bash
python3 tools/ofa.py verify examples/sensor-log.ofa
```

```bash
python3 tools/ofa.py cat examples/sensor-log.ofa readings
```

Build your own from a folder containing a `ofa.json` template:

```bash
python3 tools/ofa.py pack examples/src/sensor-log my-log.ofa
```

No tool at all? It is a ZIP file:

```bash
unzip -p examples/sensor-log.ofa ofa.json
```

## Repository layout

| Path | Contents |
|---|---|
| [`SPEC.md`](SPEC.md) | The living specification |
| [`schema/`](schema/) | JSON Schema for `ofa.json` |
| [`examples/`](examples/) | Sample packages and the folders they were built from |
| [`tools/ofa.py`](tools/ofa.py) | Reference inspector, verifier and packer |
| [`research/survey.md`](research/survey.md) | Survey of OPC, EPUB, JAR, RO-Crate, Avro, Matroska, MCAP, HDF5 and others |
| [`rfcs/`](rfcs/) | Proposals for changes, including [RFC 0001](rfcs/0001-extension-and-media-type.md) on the name and extension |
| [`NEXT_STEPS.md`](NEXT_STEPS.md) | Roadmap and open questions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to propose changes |

## How OFA relates to other formats

OFA does not replace Parquet, PNG, SQLite or MCAP. It carries them. If your
data already has a good self-describing format, put that file in a package
and let the manifest say what it is. OFA fills the gap for everything that
currently ends up as an undocumented ZIP or a bespoke binary.

The [survey](research/survey.md) explains what OFA borrows from each
existing format.

## License

- Specification text, schemas and examples: [CC BY 4.0](LICENSE-SPEC.md)
- Code in `tools/`: [Apache License 2.0](LICENSE)
