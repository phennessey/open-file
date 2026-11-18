# Open File Archive (OFA)

- Version: **0.1.0-draft**
- Status: Working draft. Expect breaking changes before 1.0.
- Media type: `application/vnd.ofa+zip`
- Extension: `.ofa`
- License: [CC BY 4.0](LICENSE-SPEC.md)

## 1. Introduction

An OFA package is a ZIP file that holds one or more data streams and a JSON
manifest describing them. The manifest tells a reader, for each stream, what
kind of bytes it holds (media type), how those bytes were compressed (content
coding), what structure they follow (schema), and what part the stream plays
in the package (role).

Any program with a ZIP library and a JSON parser can open an OFA package,
list its contents, check every digest and extract every stream. A program
that also supports the common media types and schema languages listed in
[Appendix A](#appendix-a-registries) can interpret the contents fully.

### 1.1 Goals

1. Open and list any package with only ZIP and JSON.
2. Fully decode common content without format-specific code.
3. Reuse existing registries and standards for every concept they cover.
4. Keep the manifest small enough to write by hand.

### 1.2 Non-goals

- Replacing Parquet, PNG, MCAP, SQLite or any other stream format. Those
  formats go *inside* a package.
- Encryption. Encrypt the whole file with an external tool such as `age` or
  OpenPGP.
- Append-while-recording workloads. ZIP writes its index last. A future
  profile may address this (see [NEXT_STEPS.md](NEXT_STEPS.md)).
- Executable content as part of the format. See section 13.

## 2. Conventions and terms

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL in this document are to be interpreted as
described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in
all capitals.

| Term | Meaning |
|---|---|
| **Package** | A ZIP file that conforms to this specification. |
| **Entry** | One file inside the ZIP. |
| **Manifest** | The entry named `ofa.json`. |
| **Stream** | An entry described by a stream descriptor in the manifest. |
| **Stored bytes** | The bytes of an entry after ZIP decompression. What `unzip` writes to disk. |
| **Decoded bytes** | Stored bytes after reversing every content coding the descriptor lists. |
| **Writer** | Software that creates or modifies packages. |
| **Reader** | Software that opens packages. |

## 3. Design principles

1. **Listing never fails.** A reader that meets a package with an unknown
   version, unknown media types or unknown extensions still lists every stream
   and verifies every digest.
2. **Declare, don't execute.** The manifest describes data. Nothing in a
   conforming package requires running code from the package.
3. **Borrow vocabularies.** Media types come from IANA. Content codings come
   from the IANA HTTP Content Coding registry. Schemas use existing schema
   languages. The spec defines new terms only where no registry exists
   (roles).
4. **Everything is a stream.** Schemas, thumbnails, licences and READMEs are
   streams too. One descriptor shape covers them all.
5. **Unknown means ignore.** Readers ignore fields they do not recognise,
   unless the package lists them in `requires`.
6. **Every byte is accounted for.** The manifest lists every entry with a
   size and a SHA-256 digest.

## 4. Container

### 4.1 ZIP profile

A package MUST be a valid ZIP file as defined by the PKWARE APPNOTE (version
6.3.10 or later), restricted as follows. The restrictions follow ISO/IEC
21320-1, with ZIP64 added.

1. Writers MUST use compression method 0 (Stored) or 8 (Deflate) for every
   entry. Readers MUST support both.
2. Writers MUST NOT use ZIP encryption, including traditional PKWARE
   encryption and AES extensions.
3. Writers MUST NOT split or span a package across files.
4. Writers MAY use ZIP64 extensions. Readers MUST support ZIP64.
5. Writers MUST encode entry names as UTF-8. Writers MUST set general
   purpose bit 11 on any entry whose name contains non-ASCII characters.
6. Writers MUST NOT create entries for directories. Readers MUST ignore
   entries whose names end in `/`.
7. Writers MUST NOT put data before the first local file header or after the
   end of central directory record, apart from a ZIP file comment.
8. Readers MUST use the central directory to locate entries. Readers MUST
   reject a package in which two central directory records point at
   overlapping byte ranges.
9. Writers SHOULD store (method 0) any entry that already has a content
   coding or an inherently compressed media type (PNG, JPEG, Parquet, zstd
   data). Compressing those twice wastes time.
10. Writers MAY pad the extra field of Stored entries so that entry data
    starts on a 64-byte boundary. This lets readers memory-map those entries.

### 4.2 The `mimetype` entry

The first entry in the ZIP MUST be named `mimetype`. Its stored bytes MUST
be the ASCII string `application/vnd.ofa+zip` with no trailing newline. The
writer MUST store it with method 0 and MUST NOT give it an extra field.

This places fixed bytes at fixed offsets, the same technique EPUB and ODF
use:

| Offset | Bytes |
|---|---|
| 0 | `50 4B 03 04` (`PK\x03\x04`) |
| 30 | `mimetype` |
| 38 | `application/vnd.ofa+zip` |

Readers SHOULD check these bytes before trusting a file. A reader that finds
a valid ZIP whose `mimetype` entry is missing or wrong MUST NOT treat the
file as an OFA package, though it MAY still list the ZIP.

### 4.3 The manifest entry

Every package MUST contain exactly one entry named `ofa.json` at the root.
Writers SHOULD place it second, directly after `mimetype`, so that a reader
streaming the file from the start meets the manifest before the data. Writers
that cannot know digests in advance MAY place it last.

### 4.4 Entry names

Entry names MUST:

- use `/` as the only separator;
- not start with `/`;
- not contain a segment equal to `.` or `..`;
- not contain backslash (`\`), colon (`:`), NUL or any C0 control character;
- be in Unicode Normalization Form C;
- be unique within the package after case folding, so that the package
  extracts cleanly on case-insensitive file systems;
- be at most 255 bytes per segment and 1024 bytes in total.

Writers SHOULD use lowercase ASCII letters, digits, `-`, `_` and `.` only.

### 4.5 Reserved names

The following root-level names are reserved. Writers MUST NOT use them for
streams.

| Name | Purpose |
|---|---|
| `mimetype` | Identification, section 4.2 |
| `ofa.json` | Manifest, section 5 |
| `signatures/` | Detached signatures, section 9.3 |
| `META-INF/` | Reserved to avoid confusion with JAR, ODF and EPUB tooling |
| `_ofa/` | Reserved for future versions of this specification |

### 4.6 Recommended layout

Writers MAY arrange streams in any directory structure. The following layout
is RECOMMENDED:

```
example.ofa
├── mimetype            identification (first entry, stored)
├── ofa.json           manifest (second entry)
├── data/               primary and data streams
├── schemas/            schema streams
├── meta/               metadata, licence, provenance
├── preview/            thumbnails and previews
└── signatures/         optional detached signatures
```

## 5. Manifest

### 5.1 Syntax

The manifest MUST be a JSON object (RFC 8259) that also conforms to I-JSON
(RFC 7493). In particular:

- UTF-8 encoding with no byte order mark;
- no duplicate member names;
- integers within ±(2^53 − 1).

Readers MAY refuse manifests larger than 16 MiB or nested deeper than 64
levels. Writers MUST stay within those limits.

A JSON Schema for the manifest lives at
[`schema/ofa-manifest.schema.json`](schema/ofa-manifest.schema.json).

### 5.2 Top-level members

| Member | Type | Req. | Meaning |
|---|---|---|---|
| `ofa` | string | **yes** | Spec version this manifest follows, as `"MAJOR.MINOR"`. For this draft: `"0.1"`. |
| `streams` | array | **yes** | Stream descriptors (5.3). At least one. |
| `id` | string | no | Stable identifier for the package as a URI, for example `urn:uuid:…` (RFC 9562). Writers SHOULD keep it the same across revisions of the same logical package. |
| `title` | string | no | Human-readable name. |
| `description` | string | no | Human-readable summary. Plain text or CommonMark. |
| `created` | string | no | RFC 3339 timestamp of creation. |
| `modified` | string | no | RFC 3339 timestamp of last modification. |
| `generator` | object | no | `{ "name": string, "version": string, "uri": string }` identifying the writer software. |
| `primary` | string | no | ID of the stream a reader should open first. |
| `lang` | string | no | Default BCP 47 language tag for text streams. |
| `metadata` | object | no | Free-form descriptive metadata. See 5.6. |
| `extensions` | object | no | Extension data keyed by extension ID. See 10.2. |
| `requires` | array of strings | no | Extension IDs a reader must understand to interpret the package correctly. See 10.3. |

### 5.3 Stream descriptors

Each element of `streams` describes exactly one entry.

| Member | Type | Req. | Meaning |
|---|---|---|---|
| `id` | string | **yes** | Unique within the package. Matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`. |
| `path` | string | **yes** | Entry name in the ZIP. Unique across descriptors. |
| `media_type` | string | **yes** | Media type of the **decoded bytes** (RFC 6838), with optional parameters, for example `text/csv; header=present`. |
| `size` | integer | **yes** | Length of the **stored bytes**. |
| `digest` | string | **yes** | `sha256:` followed by 64 lowercase hex digits: the SHA-256 of the stored bytes. |
| `content_encoding` | array of strings | no | Content codings applied to the decoded bytes, in the order the writer applied them. Values come from Appendix A.3. Absent or empty means none. |
| `role` | string | no | What the stream is for. See 5.5. Default `data`. |
| `schema` | object | no | Schema reference. See section 8. |
| `describes` | array of strings | no | IDs of streams this stream is about. A thumbnail, index or schema stream lists its targets here. |
| `title` | string | no | Human-readable name. |
| `description` | string | no | Human-readable summary. |
| `lang` | string | no | BCP 47 language tag. Overrides the package default. |
| `metadata` | object | no | Free-form metadata for this stream. |
| `extensions` | object | no | Extension data for this stream. |

Rules:

1. Writers MUST describe every entry except `mimetype`, `ofa.json` and
   entries under `signatures/`.
2. Readers MUST report any undescribed entry as a warning and MUST NOT
   interpret it.
3. Readers MUST treat a descriptor whose `path` does not exist as an error
   for that stream only. The rest of the package stays readable.
4. For any `text/*` media type, the decoded bytes are UTF-8 unless the
   media type carries a `charset` parameter. Writers SHOULD use UTF-8.

### 5.4 Choosing `media_type`

Writers MUST use a registered IANA media type when one exists. When none
exists, writers MUST use one listed in Appendix A.4, or a `vnd.` or
`prs.` type they control. Writers MUST NOT invent `x-` types beyond those
already in common use and listed in Appendix A.4.

Writers SHOULD use `application/octet-stream` for bytes with no meaningful
type, rather than guessing.

### 5.5 Roles

A role says what part a stream plays, independent of its media type. A
Parquet file can be the primary content or an index. A PNG can be the
content or a thumbnail.

The value is either a term from the role registry (Appendix A.1) or an
absolute URI for a custom role. Readers MUST treat an unknown role as `data`.

### 5.6 Metadata

`metadata` holds descriptive information as a JSON object. This
specification does not fix its members. Writers SHOULD use Dublin Core
Terms names without a prefix (`creator`, `license`, `subject`, `rights`,
`source`) when one fits, and MAY use full URIs as member names for anything
else.

Writers that need rich, linked metadata SHOULD include an RO-Crate
`ro-crate-metadata.json` stream with role `metadata` instead of stretching
this object.

`license` SHOULD be an SPDX license expression or a URI.

## 6. Streams and addressing

### 6.1 Identity

A stream's `id` is its stable name. Its `path` is where the bytes live. Tools
and humans SHOULD refer to streams by `id`, so that writers can reorganise
paths without breaking references.

### 6.2 Inside the package

Members that point at other streams (`primary`, `describes`, `schema.stream`)
hold stream IDs, never paths.

### 6.3 From outside the package

To refer to a stream from outside, append a fragment `#stream=<id>` to the
package URI:

```
https://example.org/runs/2026-11-01.ofa#stream=readings
file:///home/ana/survey.ofa#stream=responses
```

Selecting records or byte ranges within a stream lies outside this
specification. The stream's own media type governs any further fragment
syntax.

## 7. Decoding pipeline

To obtain a stream's content, a reader performs these steps in order:

1. **Locate.** Find the entry named by `path` in the central directory.
2. **Unzip.** Inflate (method 8) or copy (method 0) to get the stored bytes.
   Stop if the output exceeds `size`.
3. **Verify.** Compare the length with `size` and the SHA-256 with `digest`.
   On mismatch, the reader MUST NOT pass the bytes on as valid content. It
   MAY offer them to the user, marked as corrupt.
4. **Undo content codings.** Apply the inverse of each entry in
   `content_encoding`, last entry first. The result is the decoded bytes.
5. **Parse.** Interpret the decoded bytes according to `media_type`.
6. **Validate** (optional). If `schema` is present and the reader supports
   its type, validate or interpret the parsed content with it.

A reader that cannot perform step 4, 5 or 6 for a stream MUST still list it
and MUST still offer the stored bytes for extraction.

## 8. Schemas

### 8.1 Schema reference

A stream's `schema` member is an object:

| Member | Type | Req. | Meaning |
|---|---|---|---|
| `type` | string | **yes** | Schema language, from Appendix A.2. |
| `stream` | string | one of three | ID of a stream in this package that holds the schema. |
| `inline` | any JSON | one of three | The schema itself, for schema languages expressed in JSON. |
| `uri` | string | one of three | An external schema. See 8.3. |
| `name` | string | no | The record, message or definition inside the schema that applies, for example a Protobuf full message name `acme.v1.Reading`. |

Exactly one of `stream`, `inline` or `uri` MUST be present.

The schema stream itself is an ordinary stream with role `schema` and
a `describes` list naming the streams it covers.

### 8.2 Self-describing media types

Some media types carry their own schema: Parquet, Arrow IPC, Avro Object
Container Files, MCAP, SQLite. Writers SHOULD omit `schema` for these
streams. If present, it adds information and does not replace the embedded
schema.

### 8.3 External schemas

A schema given by `uri` makes the package depend on the network. Writers
SHOULD embed schemas as streams instead. Readers MUST NOT fetch an external
schema without the user's consent or explicit configuration, and MUST NOT
resolve `$ref` values in JSON Schema to remote URIs by default.

### 8.4 Schema languages

Appendix A.2 lists the schema types readers can expect. A reader that does
not support a schema type still decodes the stream through step 5 of
section 7.

## 9. Integrity and signatures

### 9.1 Stream digests

Every stream carries a SHA-256 digest of its stored bytes (section 5.3). This
detects corruption and, combined with a signature, tampering.

### 9.2 Package digest

The **package digest** is the SHA-256 of the exact stored bytes of
`ofa.json`, written `sha256:<hex>`. Because the manifest holds the digest of
every stream, the package digest identifies the whole content. Two packages
with the same package digest hold the same streams with the same
descriptions, whatever their ZIP layout.

### 9.3 Signatures (optional)

A writer MAY sign a package by adding one or more entries named
`signatures/<name>.jws`. Each holds a JWS in compact serialization (RFC 7515)
with a **detached payload** (RFC 7515 Appendix F). The payload is the exact
stored bytes of `ofa.json`.

To verify, a reader:

1. reads `ofa.json` stored bytes;
2. reattaches them as the JWS payload and verifies the signature with a key
   it trusts;
3. verifies every stream digest.

Key distribution and trust policy lie outside this specification. Writers
MUST NOT use the JWS `none` algorithm. Readers MUST reject it.

Signature entries do not appear in `streams`, so adding a signature does not
change the package digest.

## 10. Extensibility

### 10.1 Unknown members

Readers MUST ignore manifest members they do not recognise, at every level,
unless section 10.3 applies. Writers that modify a package SHOULD preserve
members they do not recognise.

### 10.2 Extensions

An extension defines new members or behaviour. Each has an ID: either a
reverse domain name (`org.example.timeline`) or an absolute URI. Extension
data goes in an `extensions` object, at the top level or on a stream, keyed
by extension ID:

```json
"extensions": {
  "org.example.timeline": { "start": "2026-11-01T00:00:00Z" }
}
```

Writers MUST NOT add new top-level or descriptor members outside
`extensions`. Members that appear in future versions of this specification
come only through the RFC process.

### 10.3 Required extensions

If a reader would misinterpret the package without an extension, the writer
MUST list that extension's ID in top-level `requires`. A reader that does not
support a listed extension:

- MUST still list streams, verify digests and extract stored bytes;
- MUST tell the user that it cannot fully interpret the package;
- MUST NOT write the package back while claiming to preserve it.

Writers SHOULD avoid `requires`. Use it when ignoring the extension would
produce wrong results, not merely incomplete ones.

## 11. Versioning

The `ofa` member holds `"MAJOR.MINOR"`.

- **Minor** versions add optional members, roles, schema types and registry
  entries. A reader for version 1.2 reads a 1.5 package and ignores what it
  does not know.
- **Major** versions may change meaning. A reader that does not know the
  major version MUST still perform the Inspect operations of section 12.1 and
  MUST warn that it cannot interpret the package.
- Before 1.0, each `0.MINOR` counts as a major version.
- The `mimetype` entry does not change between versions. Section 4 stays
  stable across major versions so that listing keeps working.

Registries (Appendix A) evolve faster than the spec. Adding a registry entry
needs an RFC but no version change.

## 12. Conformance

### 12.1 Readers

| Level | A reader at this level MUST |
|---|---|
| **Inspect** | Read the ZIP profile (4.1) including ZIP64. Check the `mimetype` entry. Parse the manifest. List each stream's `id`, `path`, `media_type`, `role`, `size`. Verify digests. Extract stored bytes. Report undescribed entries. Apply the security rules in section 14. |
| **Core** | Everything in Inspect, plus: undo the content codings `gzip`, `deflate` and `zstd`; parse the Core media types in Appendix A.4; validate JSON, NDJSON and CSV streams against `json-schema` and `table-schema` schemas. |
| **Extended** | Everything in Core, plus any further media types and schema types in Appendix A, as the implementation documents. |

A reader MUST state which level it implements. A conformance test suite will
accompany 0.2.

### 12.2 Writers

A conforming writer MUST produce packages that meet sections 4 and 5,
including a correct `size` and `digest` for every stream, and MUST produce
manifests that validate against the manifest JSON Schema.

## 13. Custom decoders (experimental)

Some data has no standard media type and no declarative schema can describe
it. For those cases a future version may allow a package to carry a
**sandboxed decoder**: a WebAssembly module that turns one stream's decoded
bytes into a standard media type (for example, a proprietary binary into
Arrow IPC or JSON).

Version 0.1 does not define the decoder interface. It sets these rules now so
that early experiments stay safe:

1. Decoders MUST be WebAssembly modules (W3C WebAssembly Core). No native
   code, scripts or interpreters of other languages.
2. A decoder MUST be an ordinary stream with role `decoder`, with its own
   `digest`, and with `describes` naming the streams it handles.
3. A decoder's output MUST be a media type from Appendix A.4, so the result
   is something a Core reader understands.
4. Readers MUST NOT run a decoder by default. Running one requires a user
   action or configuration naming that decoder's digest.
5. Readers MUST run decoders with no imports except linear memory and the
   input buffer: no file system, network, clock or randomness. Readers MUST
   cap memory and execution time.
6. Every stream a decoder handles MUST remain listable and extractable
   without it.
7. Packages MUST NOT list a decoder in `requires`.

Writers SHOULD prefer converting data to a standard format at write time
over shipping a decoder.

## 14. Security considerations

Readers MUST treat every package as untrusted input.

| Threat | Requirement |
|---|---|
| **Path traversal** ("zip slip") | Readers extracting to disk MUST reject names that break section 4.4 and MUST resolve every output path inside the target directory. |
| **Symbolic links** | Readers MUST ignore Unix mode bits and external attributes, and MUST NOT create symlinks, devices or executables on extraction. |
| **Decompression bombs** | Readers MUST stop inflating an entry once output exceeds the descriptor's `size`, and MUST apply a configurable limit on total decoded size and on the ratio between decoded and stored size for each content coding step. |
| **Overlapping entries** | Readers MUST reject packages whose central directory records overlap (4.1 rule 8). This blocks the "overlapping file" class of ZIP bombs. |
| **Header mismatch** | Readers MUST trust the central directory and SHOULD warn when a local header disagrees with it. |
| **Polyglot files** | Rule 7 of 4.1 forbids leading data, which stops a package from also being a valid executable or PDF. Readers SHOULD reject files with leading data. |
| **Duplicate names** | Readers MUST reject packages with two entries whose names match after case folding and NFC normalisation. |
| **Manifest parsing** | Readers MUST use a JSON parser with depth and size limits and MUST reject duplicate member names. |
| **Remote fetches** | Readers MUST NOT fetch any URI from a manifest (schemas, metadata links) without user consent. |
| **Active content** | Readers that render streams (HTML, SVG, PDF, Markdown) MUST disable scripts and remote loads, as a browser does for an untrusted download. |
| **Spreadsheet export** | Tools that export CSV to spreadsheet programs SHOULD neutralise cells starting with `=`, `+`, `-` or `@`. |
| **Decoders** | Section 13. |
| **Digest scope** | A matching digest proves integrity, not authenticity. Only a verified signature (9.3) ties content to a signer. |

## 15. Privacy considerations

Manifests often carry names, timestamps, generator versions and free-form
metadata. Writers SHOULD let users review and remove these before sharing.
ZIP entries carry modification times. Writers SHOULD set them to a fixed
value (1980-01-01 00:00:00) unless the user asks to keep them; this also
makes packages reproducible.

## 16. IANA considerations

The project will register `application/vnd.ofa+zip` in the IANA vendor tree.
[RFC 0001](rfcs/0001-extension-and-media-type.md) holds the registration
template.

## 17. Examples

### 17.1 Minimal package

```
hello.ofa
├── mimetype
├── ofa.json
└── hello.txt
```

```json
{
  "ofa": "0.1",
  "title": "Hello",
  "primary": "hello",
  "streams": [
    {
      "id": "hello",
      "path": "hello.txt",
      "media_type": "text/plain; charset=utf-8",
      "size": 14,
      "digest": "sha256:d9014c4624844aa5bac314773d6b689ad467fa4e1d1a50a1b8a99d5a95f72ff5"
    }
  ]
}
```

### 17.2 Sensor log with schemas and compression

```
sensor-log.ofa
├── mimetype
├── ofa.json
├── data/
│   ├── stations.csv
│   └── readings.ndjson.gz
├── schemas/
│   ├── stations.table.json
│   └── reading.schema.json
├── meta/
│   └── LICENSE.txt
└── README.md
```

```json
{
  "ofa": "0.1",
  "id": "urn:uuid:5f0c2b1e-8a0e-4d0b-9c55-6a3f6f1b2c10",
  "title": "Rooftop weather stations, 1 November 2026",
  "created": "2026-11-02T08:00:00Z",
  "generator": { "name": "ofa.py", "version": "0.1.0" },
  "primary": "readings",
  "metadata": { "creator": "Example Weather Club", "license": "CC-BY-4.0" },
  "streams": [
    {
      "id": "readings",
      "path": "data/readings.ndjson.gz",
      "media_type": "application/x-ndjson",
      "content_encoding": ["gzip"],
      "schema": { "type": "json-schema", "stream": "reading-schema" },
      "size": 214,
      "digest": "sha256:…"
    },
    {
      "id": "stations",
      "path": "data/stations.csv",
      "media_type": "text/csv; header=present",
      "schema": { "type": "table-schema", "stream": "stations-schema" },
      "size": 131,
      "digest": "sha256:…"
    },
    {
      "id": "reading-schema",
      "path": "schemas/reading.schema.json",
      "media_type": "application/schema+json",
      "role": "schema",
      "describes": ["readings"],
      "size": 626,
      "digest": "sha256:…"
    },
    {
      "id": "stations-schema",
      "path": "schemas/stations.table.json",
      "media_type": "application/json",
      "role": "schema",
      "describes": ["stations"],
      "size": 393,
      "digest": "sha256:…"
    },
    {
      "id": "readme",
      "path": "README.md",
      "media_type": "text/markdown; charset=utf-8",
      "role": "documentation",
      "size": 412,
      "digest": "sha256:…"
    },
    {
      "id": "license",
      "path": "meta/LICENSE.txt",
      "media_type": "text/plain; charset=utf-8",
      "role": "license",
      "size": 111,
      "digest": "sha256:…"
    }
  ]
}
```

Digests are elided here. Built versions of 17.2 and 17.3, with real
digests, live in [`examples/`](examples/).

### 17.3 An application save file

An AI-generated note-taking tool saves its state as an OFA package instead of
inventing a `.mynotes` format. Any other tool can list the notes, read them
as JSON and display the attached image.

```json
{
  "ofa": "0.1",
  "title": "Kitchen renovation notes",
  "generator": { "name": "quicknotes", "version": "0.3.1" },
  "primary": "notes",
  "streams": [
    {
      "id": "notes",
      "path": "data/notes.json",
      "media_type": "application/json",
      "schema": { "type": "json-schema", "stream": "notes-schema", "name": "#/$defs/notebook" },
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
    },
    {
      "id": "sketch",
      "path": "data/attachments/sketch.png",
      "media_type": "image/png",
      "role": "attachment",
      "describes": ["notes"],
      "size": 112,
      "digest": "sha256:…"
    },
    {
      "id": "thumb",
      "path": "preview/thumbnail.png",
      "media_type": "image/png",
      "role": "thumbnail",
      "size": 87,
      "digest": "sha256:…"
    }
  ],
  "extensions": {
    "app.quicknotes.ui": { "last_open_note": "n2", "theme": "dark" }
  }
}
```

The `extensions` block holds application state that only `quicknotes`
needs. Every other reader ignores it.

### 17.4 Binary records with Protobuf and a columnar table

```json
{
  "ofa": "0.1",
  "streams": [
    {
      "id": "events",
      "path": "data/events.binpb.zst",
      "media_type": "application/vnd.ofa.protobuf-delimited",
      "content_encoding": ["zstd"],
      "schema": { "type": "protobuf", "stream": "events-fds", "name": "acme.telemetry.v1.Event" },
      "size": 48213,
      "digest": "sha256:…"
    },
    {
      "id": "events-fds",
      "path": "schemas/telemetry.fds.binpb",
      "media_type": "application/x-protobuf",
      "role": "schema",
      "describes": ["events"],
      "metadata": { "note": "google.protobuf.FileDescriptorSet" },
      "size": 912,
      "digest": "sha256:…"
    },
    {
      "id": "summary",
      "path": "data/summary.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size": 20480,
      "digest": "sha256:…"
    }
  ]
}
```

## Appendix A. Registries

Each registry lives in this appendix until it outgrows it. Adding an entry
takes an RFC (see [CONTRIBUTING.md](CONTRIBUTING.md)).

### A.1 Roles

| Role | Meaning |
|---|---|
| `data` | Content. The default. |
| `schema` | Describes the structure of the streams in `describes`. |
| `metadata` | Describes the package or the streams in `describes` (for example RO-Crate, DataCite, EXIF sidecars). |
| `documentation` | Human-readable explanation, such as a README. |
| `license` | Licence text that applies to the package or to the streams in `describes`. |
| `thumbnail` | Small image representing the package or the streams in `describes`. |
| `preview` | Rendered, lossy view of other streams (PDF of a document, PNG of a chart). |
| `index` | Lookup structure that speeds up access to the streams in `describes`. Readers MAY ignore it. |
| `attachment` | Supporting file referenced by other content. |
| `source` | Original input from which other streams were derived. |
| `provenance` | Record of how the package was produced (for example W3C PROV, an RO-Crate run). |
| `decoder` | Experimental sandboxed decoder. Section 13. |

The package's `primary` member, not a role, marks the main stream.

### A.2 Schema types

| `type` | Schema language | Stream media type | Applies to |
|---|---|---|---|
| `json-schema` | JSON Schema 2020-12 | `application/schema+json` | JSON, NDJSON, CBOR (via its JSON data model) |
| `table-schema` | Frictionless Table Schema v2 | `application/json` | CSV, TSV |
| `avro` | Apache Avro schema (JSON form) | `application/json` | Avro binary records outside an OCF |
| `protobuf` | Protocol Buffers `FileDescriptorSet` (binary) | `application/x-protobuf` | Protobuf messages |
| `xsd` | W3C XML Schema 1.1 | `application/xml` | XML |

### A.3 Content codings

Values come from the IANA HTTP Content Coding registry.

| Coding | Specification | Core |
|---|---|---|
| `gzip` | RFC 1952 | yes |
| `deflate` | RFC 1950 (zlib wrapper, as in HTTP) | yes |
| `zstd` | RFC 8878 | yes |
| `br` | RFC 7932 | no |

Writers MUST NOT use codings that encrypt or that need a shared dictionary
(`aes128gcm`, `dcb`, `dcz`) in version 0.1.

### A.4 Well-known media types

**Core.** A Core reader parses all of these.

| Media type | Notes |
|---|---|
| `text/plain` | UTF-8 unless `charset` says otherwise. |
| `text/markdown` | CommonMark. |
| `text/csv` | RFC 4180. `header=present` or `header=absent` parameter RECOMMENDED. |
| `text/tab-separated-values` | IANA TSV. |
| `application/json` | RFC 8259. |
| `application/schema+json` | JSON Schema documents. |
| `application/x-ndjson` | One JSON value per line, LF separated. Not IANA registered but in wide use. Listed here so writers converge on one name. |
| `application/cbor` | RFC 8949. |
| `image/png` | |
| `image/jpeg` | |
| `application/octet-stream` | Opaque bytes. Listed and extracted, never interpreted. |

**Extended.** Common, and Extended readers SHOULD support as many as they
can.

| Media type | Notes |
|---|---|
| `application/vnd.apache.parquet` | Self-describing. |
| `application/vnd.apache.arrow.file` | Arrow IPC file format. Self-describing. |
| `application/vnd.apache.arrow.stream` | Arrow IPC stream format. Self-describing. |
| `application/avro` | Avro Object Container File. Not IANA registered. Open question whether to register a `vnd.` name. |
| `application/vnd.mcap` | Self-describing message log. |
| `application/vnd.sqlite3` | Self-describing database. |
| `application/x-protobuf` | Single Protobuf message or `FileDescriptorSet`. |
| `application/vnd.ofa.protobuf-delimited` | Sequence of Protobuf messages, each prefixed by its length as a varint. Defined here because no registered type exists. |
| `application/xml` | |
| `application/pdf` | Render with scripts disabled. |
| `image/webp`, `image/avif`, `image/svg+xml` | SVG: render with scripts disabled. |
| `audio/*`, `video/*` | Any registered type. |
| `application/x-npy` | NumPy array file. |
| `application/geo+json` | RFC 7946. |

## Appendix B. References

### Normative

- PKWARE, APPNOTE.TXT, .ZIP File Format Specification, version 6.3.10.
- ISO/IEC 21320-1:2015, Document Container File, Part 1: Core.
- RFC 2119 and RFC 8174, requirement levels (BCP 14).
- RFC 3339, timestamps. RFC 3986, URIs. BCP 47, language tags.
- RFC 6838, media type specifications. RFC 6839, structured syntax suffixes.
- RFC 7493, I-JSON. RFC 8259, JSON.
- RFC 1950, RFC 1951, RFC 1952, RFC 7932, RFC 8878, content codings.
- FIPS 180-4, SHA-256.
- RFC 7515, JSON Web Signature.
- RFC 9562, UUIDs.
- JSON Schema 2020-12.

### Informative

- [research/survey.md](research/survey.md), the survey behind this draft.
- Frictionless Data Package v2 and Table Schema.
- Apache Avro, Apache Parquet, Apache Arrow, Protocol Buffers.
- MCAP, Matroska (RFC 9559), EBML (RFC 8794).
- EPUB OCF 3.3, ODF 1.3 Part 2, ECMA-376 Part 2 (OPC).
- OCI Image Specification, descriptors.
- glTF 2.0, extensions mechanism.
- RO-Crate 1.2.
- W3C WebAssembly Core Specification 2.0.
