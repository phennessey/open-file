# Open File Archive (OFA)

- Version: **0.3.0-draft**
- Status: Working draft, **open for public comment**. Expect breaking changes
  before 1.0. Comment in [Discussions](https://github.com/phennessey/open-file/discussions) or
  [open an issue](https://github.com/phennessey/open-file/issues).
- Media type: `application/vnd.ofa+zip`
- Extension: `.ofa`
- License: [CC BY 4.0](LICENSE-SPEC.md)

Version 0.2 replaced the 0.1 manifest, `ofa.json`, with a standard
Frictionless Data Package descriptor, `datapackage.json`
([RFC 0002](rfcs/0002-use-frictionless-data-package.md)). Version 0.3 adopts
ideas from the Frictionless community's long-running discussion of
single-file Data Packages: Frictionless's `compression` property, a
compatibility mode for plain zipped Data Packages, an `adopt` operation, and
reading over HTTP ([RFC 0003](rfcs/0003-frictionless-bundling-ideas.md)).

## 1. Introduction

An OFA package is a ZIP file that holds one or more data files and a
manifest describing them. The manifest is a
[Frictionless Data Package](https://datapackage.org/) descriptor,
`datapackage.json`, used exactly as that standard defines it. For each file
it tells a reader what kind of bytes it holds (media type), what structure
they follow (schema), how the bytes were compressed (compression), and
what part the file plays in the package (role).

Data Package describes the data. OFA defines the single-file container
around it, plus the few properties Data Package leaves out, which OFA keeps
in private `_ofa` properties.

Any program with a ZIP library and a JSON parser can open an OFA package,
list its contents, check every hash, and extract every resource. Any
Frictionless tool can read its manifest. A program that also supports the
common media types and schema languages listed in
[Appendix A](#appendix-a-registries) can interpret the contents fully.

### 1.1 Goals

1. Open and list any package with only ZIP and JSON.
2. Fully decode common content without format-specific code.
3. Reuse existing standards for every concept they cover, starting with
   Data Package for the manifest.
4. Keep the manifest small enough to write by hand.

### 1.2 Non-goals

- Replacing Parquet, PNG, MCAP, SQLite, or any other data format. Those
  formats go *inside* a package.
- Encryption. Encrypt the whole file with an external tool such as `age` or
  OpenPGP.
- Append-while-recording workloads. ZIP writes its index last. A future
  profile may address this (see [NEXT_STEPS.md](NEXT_STEPS.md)).
- Executable content as part of the format. See section 13.

## 2. Conventions and terms

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as
described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in
all capitals.

| Term | Meaning |
|---|---|
| **Package** | A ZIP file that conforms to this specification. |
| **Entry** | One file inside the ZIP. |
| **Manifest** | The entry named `datapackage.json`. |
| **Data Package** | The Frictionless Data Package standard, version 2. |
| **Resource** | An entry described by a Data Resource in the manifest's `resources` array. |
| **`_ofa` properties** | The private properties this specification adds to Data Package descriptors. |
| **Stored bytes** | The bytes of an entry after ZIP decompression. What `unzip` writes to disk. |
| **Decoded bytes** | Stored bytes after undoing the resource's `compression`, if it has one. |
| **Writer** | Software that creates or modifies packages. |
| **Reader** | Software that opens packages. |

## 3. Design principles

1. **Listing never fails.** A reader that meets a package with an unknown
   version, unknown media types, or unknown extensions still lists every
   resource and verifies every hash.
2. **Declare, don't execute.** The manifest describes data. Nothing in a
   conforming package requires running code from the package.
3. **Borrow standards.** The manifest is a Data Package. Media types come
   from IANA. Compression uses Data Package's `compression` property. Schemas use existing schema languages. The spec defines new
   terms only where no standard exists (roles).
4. **Everything is a resource.** Schemas, thumbnails, licences, and READMEs
   are resources too. One descriptor shape covers them all.
5. **Unknown means ignore.** Readers ignore properties they do not
   recognise, unless the package lists them in `_ofa.requires`.
6. **Every byte is accounted for.** The manifest lists every entry with its
   size and a SHA-256 hash.

## 4. Container

A package is a set of named entries: an identification entry (`mimetype`),
a manifest (`datapackage.json`), the resources the manifest describes, and
optional signatures. Those rules don't depend on the archive format. This
version defines one way to write them down, a ZIP file, in sections 4.1 to
4.6. Following the approach of BagIt (RFC 8493, section 4), another
serialization, such as `tar` with Zstandard for files written while
recording, could be added later. It would need its own RFC and its own
media type.

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
   `compression` or an inherently compressed media type (PNG, JPEG, Parquet, zstd
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

Every package MUST contain exactly one entry named `datapackage.json` at the
root, as Data Package requires. Writers MUST place it second, directly after
`mimetype`, so that a reader streaming the file from the start meets the
manifest before the data.

### 4.4 Entry names

Entry names MUST:

- use `/` as the only separator;
- not start with `/`;
- not contain a segment equal to `.` or `..`;
- not contain a segment starting with `.` when the entry is a resource,
  because Data Package forbids hidden folders in paths;
- not contain backslash (`\`), colon (`:`), NUL, or any C0 control character;
- be in Unicode Normalization Form C;
- be unique within the package after case folding, so that the package
  extracts cleanly on case-insensitive file systems;
- be at most 255 bytes per segment and 1024 bytes in total.

Writers SHOULD use lowercase ASCII letters, digits, `-`, `_`, and `.` only.

### 4.5 Reserved names

The following root-level names are reserved. Writers MUST NOT use them for
resources.

| Name | Purpose |
|---|---|
| `mimetype` | Identification, section 4.2 |
| `datapackage.json` | Manifest, section 5 |
| `signatures/` | Detached signatures, section 9.3 |
| `META-INF/` | Reserved to avoid confusion with JAR, ODF, and EPUB tooling |
| `_ofa/` | Reserved for future versions of this specification |

### 4.6 Recommended layout

Writers MAY arrange resources in any directory structure. The following layout
is RECOMMENDED:

```
example.ofa
├── mimetype            identification (first entry, stored)
├── datapackage.json    manifest (second entry)
├── data/               primary and data resources
├── schemas/            schema resources
├── meta/               metadata, licence, provenance
├── preview/            thumbnails and previews
└── signatures/         optional detached signatures
```

### 4.7 Plain zipped Data Packages (compatibility mode)

Frictionless tools have read zipped Data Packages since 2016, and many
exist, including the archives GitHub produces for "Download ZIP". A **plain
zipped Data Package** is a ZIP file with no `mimetype` entry that holds
exactly one `datapackage.json`, either at the root or inside a single
top-level folder.

1. Readers MAY open a plain zipped Data Package in **compatibility mode**.
   In that mode a reader lists resources and extracts their bytes.
2. The reader MUST warn the user that the file is not an OFA package, and
   MUST NOT report hashes as verified unless the descriptor gives SHA-256
   hashes that match.
3. The reader MUST still apply every rule in section 14.
4. A plain zipped Data Package is never a conforming OFA package. Writers
   turn one into an OFA package by adopting it (4.8).

### 4.8 Adopting a Data Package

**Adopt** turns a plain zipped Data Package, or a folder holding a
`datapackage.json`, into an OFA package. An adopting writer MUST:

1. write `mimetype` first and `datapackage.json` second, at the root,
   removing any single top-level folder from paths;
2. add `$schema` and `_ofa.version`, and fill in `bytes` and `hash` for
   every resource;
3. describe every other file it keeps as a resource, with a media type
   guessed from the file extension and, where the name makes it clear, a
   role (`README` gets `documentation`, `LICENSE` gets `license`);
4. stop with a clear message on resources an OFA package can't carry: a URL
   in `path`, inline `data`, or a `path` array.

An adopting writer SHOULD keep every other property of the original
descriptor as it was, and SHOULD show the user the media types and roles it
guessed.

### 4.9 Reading over HTTP

The Frictionless community asked for a way to read data in a bundle
"without downloading the entire bundle". A reader can open a package on a
web server that supports HTTP range requests:

1. Fetch the end of the file to find the end of central directory record,
   then fetch the central directory.
2. Fetch the start of the file to check `mimetype` and read
   `datapackage.json`, which section 4 places first and second.
3. Fetch only the entries the user asks for.

Writers SHOULD store large resources with method 0 (Stored), aligned as
4.1 rule 10 allows, so that readers can fetch byte ranges inside them. A
URL that the user gives a reader counts as consent to fetch that URL. It
does not cover any other URL, including any found inside the package.

## 5. Manifest

### 5.1 A Data Package descriptor

The manifest is a Frictionless Data Package v2 descriptor. OFA uses Data
Package as published and does not change it. Every OFA manifest is a valid
Data Package. OFA adds stricter rules and a few private properties, all of
which Data Package allows.

1. `datapackage.json` MUST be valid against the Data Package v2 profile.
2. Its root `$schema` MUST name the OFA profile for the version it follows.
   For this draft: `https://ofa-format.org/profiles/0.3/datapackage.json`.
   The profile is a JSON Schema (draft-07) that extends the Data Package v2
   profile. It lives in this repository at
   [`profiles/0.3/datapackage.json`](profiles/0.3/datapackage.json).
   (`ofa-format.org` is a placeholder until the project has a domain.)
3. The manifest MUST also conform to I-JSON (RFC 7493): UTF-8 with no byte
   order mark, no duplicate member names, and integers within
   ±(2^53 − 1).
4. Readers MAY refuse manifests larger than 16 MiB or nested deeper than 64
   levels. Writers MUST stay within those limits.

### 5.2 Private `_ofa` properties

Data Package lets a descriptor carry extra properties, and its Private
Properties recipe says that properties generated by software start with an
underscore. OFA keeps everything it adds in one object named `_ofa`, on the
package and on each resource. Frictionless tools that don't know OFA ignore
it.

### 5.3 Package properties

Data Package properties OFA uses as defined there:

| Property | Req. | Notes |
|---|---|---|
| `$schema` | **yes** | The OFA profile URL (5.1). |
| `resources` | **yes** | Data Resources (5.4). At least one. |
| `id` | no | Stable identifier, for example `urn:uuid:…` (RFC 9562). Writers SHOULD keep it the same across revisions of the same logical package. |
| `title`, `description` | no | Human-readable name and summary. |
| `created` | no | RFC 3339 timestamp of creation. |
| `version`, `licenses`, `contributors`, `sources`, `keywords`, `homepage` | no | Descriptive metadata. See 5.7. |

Members of the package's `_ofa` object:

| Member | Type | Req. | Meaning |
|---|---|---|---|
| `version` | string | **yes** | OFA spec version, as `"MAJOR.MINOR"`. For this draft: `"0.3"`. |
| `modified` | string | no | RFC 3339 timestamp of last modification. |
| `generator` | object | no | `{ "name": string, "version": string, "uri": string }` identifying the writer software. |
| `primary` | string | no | Name of the resource a reader should open first. |
| `lang` | string | no | Default BCP 47 language tag for text resources. |
| `metadata` | object | no | Descriptive metadata that has no Data Package property. See 5.7. |
| `extensions` | object | no | Extension data keyed by extension ID. See 10.2. |
| `requires` | array of strings | no | Extension IDs a reader must understand to interpret the package correctly. See 10.3. |

### 5.4 Resources

Each element of `resources` is a Data Resource that describes exactly one
entry. OFA requires five properties that Data Package leaves optional:

| Property | Type | Req. | Meaning |
|---|---|---|---|
| `name` | string | **yes** | Unique within the package. Matches `^[a-z0-9][a-z0-9._-]{0,127}$`, which is Data Package's naming advice made mandatory. |
| `path` | string | **yes** | Entry name in the ZIP. A single string, unique across resources. |
| `mediatype` | string | **yes** | Media type of the **decoded bytes** (RFC 6838). |
| `bytes` | integer | **yes** | Length of the **stored bytes**. |
| `hash` | string | **yes** | `sha256:` followed by 64 lowercase hex digits: the SHA-256 of the stored bytes. |
| `encoding` | string | no | Character encoding of a text resource, as Data Package defines it. Default UTF-8. |
| `compression` | string | no | `gz`, `zst` or `br`, following Data Package's Compression of resources recipe. See 5.5. |
| `type` | string | no | `table` for tabular data, as Data Package defines it. |
| `schema` | string or object | no | Schema as Data Package defines it. See section 8. |
| `title`, `description` | string | no | Human-readable name and summary. |
| `licenses`, `sources` | array | no | As Data Package defines them. |

Members of each resource's `_ofa` object:

| Member | Type | Meaning |
|---|---|---|
| `role` | string | What the resource is for. See 5.6. Default `data`. |
| `schema` | object | Schema reference for schemas Data Package has no property for. See section 8. |
| `describes` | array of strings | Names of resources this resource is about. A thumbnail, index, or schema resource lists its targets here. |
| `lang` | string | BCP 47 language tag. Overrides the package default. |
| `metadata` | object | Free-form metadata for this resource. |
| `extensions` | object | Extension data for this resource. |

Rules:

1. Writers MUST describe every entry except `mimetype`, `datapackage.json`
   and entries under `signatures/` and `META-INF/`.
2. A resource MUST NOT use inline `data`, a `path` array, or a URL in
   `path`. Every resource is an entry in the ZIP.
3. Readers MUST report any undescribed entry as a warning and MUST NOT
   interpret it.
4. Readers MUST treat a resource whose `path` does not exist as an error
   for that resource only. The rest of the package stays readable.
5. Text resources are UTF-8 unless `encoding` says otherwise. Writers
   SHOULD use UTF-8.

### 5.5 Choosing `mediatype`

Writers MUST use a registered IANA media type when one exists. When none
exists, writers MUST use one listed in Appendix A.4, or a `vnd.` or
`prs.` type they control. Writers MUST NOT invent `x-` types beyond those
already in common use and listed in Appendix A.4.

`mediatype` names the decoded bytes. A gzipped NDJSON file has
`"mediatype": "application/x-ndjson"` and `"compression": "gz"`.

Compression follows the Data Package recipe
[Compression of resources](https://datapackage.org/recipes/compression-of-resources/):

1. A compressed resource MUST have a `compression` property with a value
   from Appendix A.3.
2. Its `path` MUST end with the matching extension (`.gz`, `.zst` or
   `.br`), so tools that infer compression from the file name also read it
   correctly.
3. `bytes` and `hash` describe the compressed file, as the recipe says.
4. A resource has at most one compression step.

Writers SHOULD use `application/octet-stream` for bytes with no meaningful
type, rather than guessing.

### 5.6 Roles

A role says what part a resource plays, independent of its media type. A
Parquet file can be the primary content or an index. A PNG can be the
content or a thumbnail.

The value is either a term from the role registry (Appendix A.1) or an
absolute URI for a custom role. Readers MUST treat an unknown role as `data`.

### 5.7 Metadata

Writers SHOULD use Data Package's own properties for descriptive metadata:
`licenses`, `contributors`, `sources`, `keywords`, `homepage`, and
`version`. For anything else, `_ofa.metadata` holds a JSON object whose
members this specification does not fix. Writers SHOULD use Dublin Core
Terms names without a prefix when one fits, and MAY use full URIs as member
names.

Writers that need rich, linked metadata SHOULD include an RO-Crate
`ro-crate-metadata.json` resource with role `metadata` instead of stretching
these properties.

## 6. Resources and addressing

### 6.1 Identity

A resource's `name` is its stable identifier. Its `path` is where the bytes
live. Tools and humans SHOULD refer to resources by `name`, so that writers
can reorganise paths without breaking references.

### 6.2 Inside the package

Members that point at other resources (`_ofa.primary`, `_ofa.describes`,
`_ofa.schema.resource`) hold resource names, never paths. Data Package's
native `schema` property holds a path, as Data Package defines it.

### 6.3 From outside the package

To refer to a resource from outside, append a fragment `#resource=<name>`
to the package URI:

```
https://example.org/runs/2026-11-01.ofa#resource=readings
file:///home/ana/survey.ofa#resource=responses
```

Selecting records or byte ranges within a resource lies outside this
specification. The resource's own media type governs any further fragment
syntax.

## 7. Decoding pipeline

To obtain a resource's content, a reader performs these steps in order:

1. **Locate.** Find the entry named by `path` in the central directory.
2. **Unzip.** Inflate (method 8) or copy (method 0) to get the stored bytes.
   Stop if the output exceeds `bytes`.
3. **Verify.** Compare the length with `bytes` and the SHA-256 with `hash`.
   On mismatch, the reader MUST NOT pass the bytes on as valid content. It
   MAY offer them to the user, marked as corrupt.
4. **Decompress.** If the resource has a `compression`, decompress the
   stored bytes. The result is the decoded bytes.
5. **Parse.** Interpret the decoded bytes according to `mediatype`.
6. **Validate** (optional). If the resource has a schema (section 8) and the
   reader supports its type, validate or interpret the parsed content with
   it.

A reader that cannot perform step 4, 5, or 6 for a resource MUST still list
it and MUST still offer the stored bytes for extraction.

## 8. Schemas

### 8.1 Where a schema goes

1. **Tables.** A tabular resource (`"type": "table"`) MUST give its Table
   Schema in Data Package's native `schema` property, as the path of a
   resource in the package.
2. **JSON.** A JSON resource MAY give a JSON Schema in the native `schema`
   property, as Data Package's JSON Data Resource recipe describes.
3. **Everything else** uses `_ofa.schema`: JSON Schema for each record of an
   NDJSON file, a JSON Schema with a `name`, Avro, Protobuf, XML Schema, and
   any other language in Appendix A.2.

A resource MUST NOT have both a native `schema` and `_ofa.schema`.

`_ofa.schema` is an object:

| Member | Type | Req. | Meaning |
|---|---|---|---|
| `type` | string | **yes** | Schema language, from Appendix A.2. |
| `resource` | string | one of three | Name of a resource in this package that holds the schema. |
| `inline` | any JSON | one of three | The schema itself, for schema languages expressed in JSON. |
| `uri` | string | one of three | An external schema. See 8.3. |
| `name` | string | no | The record, message, or definition inside the schema that applies, for example a Protobuf full message name `acme.v1.Reading`. |

Exactly one of `resource`, `inline`, or `uri` MUST be present.

A schema file is an ordinary resource with `_ofa.role` set to `schema` and
an `_ofa.describes` list naming the resources it covers.

### 8.2 Self-describing media types

Some media types carry their own schema: Parquet, Arrow IPC, Avro Object
Container Files, MCAP, SQLite. Writers SHOULD omit a schema for these
resources. If present, it adds information and does not replace the embedded
schema.

### 8.3 External schemas

A schema given by `uri` makes the package depend on the network. Writers
SHOULD embed schemas as resources instead. Readers MUST NOT fetch an external
schema without the user's consent or explicit configuration, and MUST NOT
resolve `$ref` values in JSON Schema to remote URIs by default.

### 8.4 Schema languages

Appendix A.2 lists the schema types readers can expect. A reader that does
not support a schema type still decodes the resource through step 5 of
section 7.

## 9. Integrity and signatures

### 9.1 Resource hashes

Every resource carries a SHA-256 hash of its stored bytes (section 5.4).
This detects corruption and, combined with a signature, tampering.

### 9.2 Package digest

The **package digest** is the SHA-256 of the exact stored bytes of
`datapackage.json`, written `sha256:<hex>`. Because the manifest holds the
hash of every resource, the package digest identifies the whole content. Two
packages with the same package digest hold the same resources with the same
descriptions, whatever their ZIP layout.

### 9.3 Signatures (optional)

A writer MAY sign a package by adding one or more entries named
`signatures/<name>.jws`. Each holds a JWS in compact serialization (RFC 7515)
with a **detached payload** (RFC 7515 Appendix F). The payload is the exact
stored bytes of `datapackage.json`.

To verify, a reader:

1. reads the stored bytes of `datapackage.json`;
2. reattaches them as the JWS payload and verifies the signature with a key
   it trusts;
3. verifies every resource hash.

Key distribution and trust policy lie outside this specification. Writers
MUST NOT use the JWS `none` algorithm. Readers MUST reject it.

Signature entries do not appear in `resources`, so adding a signature does
not change the package digest.

## 10. Extensibility

### 10.1 Unknown members

Readers MUST ignore manifest properties they do not recognise, at every
level, unless section 10.3 applies. That includes Data Package properties
this specification does not mention. Writers that modify a package SHOULD
preserve properties they do not recognise.

### 10.2 Extensions

An extension defines new members or behaviour. Each has an ID: either a
reverse domain name (`org.example.timeline`) or an absolute URI. Extension
data goes in `_ofa.extensions`, on the package or on a resource, keyed by
extension ID:

```json
"_ofa": {
  "extensions": {
    "org.example.timeline": { "start": "2026-11-01T00:00:00Z" }
  }
}
```

Writers MUST NOT add members to `_ofa` objects outside `extensions`.
Members that appear in future versions of this specification come only
through the RFC process. Writers SHOULD put application data in
`_ofa.extensions` rather than in new top-level properties.

### 10.3 Required extensions

If a reader would misinterpret the package without an extension, the writer
MUST list that extension's ID in the package's `_ofa.requires`. A reader
that does not support a listed extension:

- MUST still list resources, verify hashes, and extract stored bytes;
- MUST tell the user that it cannot fully interpret the package;
- MUST NOT write the package back while claiming to preserve it.

Writers SHOULD avoid `requires`. Use it when ignoring the extension would
produce wrong results, not merely incomplete ones.

## 11. Versioning

The package's `_ofa.version` holds `"MAJOR.MINOR"`. The OFA profile URL in
`$schema` carries the same version.

- **Minor** versions add optional members, roles, schema types, and registry
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
| **Inspect** | Read the ZIP profile (4.1) including ZIP64. Check the `mimetype` entry. Parse the manifest. List each resource's `name`, `path`, `mediatype`, role, and `bytes`. Verify hashes. Extract stored bytes. Report undescribed entries. Apply the security rules in section 14. |
| **Core** | Everything in Inspect, plus: decompress `gz` and `zst`; parse the Core media types in Appendix A.4; validate JSON, NDJSON, and CSV resources against `json-schema` and `table-schema` schemas. |
| **Extended** | Everything in Core, plus any further media types and schema types in Appendix A, as the implementation documents. |

A reader MUST state which level it implements. A conformance test suite will
accompany a later draft.

### 12.2 Writers

A conforming writer MUST produce packages that meet sections 4 and 5,
including a correct `bytes` and `hash` for every resource, and MUST produce
manifests that validate against the OFA profile.

## 13. Custom decoders (experimental)

Some data has no standard media type and no declarative schema can describe
it. For those cases a future version may allow a package to carry a
**sandboxed decoder**: a WebAssembly module that turns one resource's decoded
bytes into a standard media type (for example, a proprietary binary into
Arrow IPC or JSON).

Version 0.3 does not define the decoder interface. It sets these rules now so
that early experiments stay safe:

1. Decoders MUST be WebAssembly modules (W3C WebAssembly Core). No native
   code, scripts, or interpreters of other languages.
2. A decoder MUST be an ordinary resource with role `decoder`, with its own
   `hash`, and with `_ofa.describes` naming the resources it handles.
3. A decoder's output MUST be a media type from Appendix A.4, so the result
   is something a Core reader understands.
4. Readers MUST NOT run a decoder by default. Running one requires a user
   action or configuration naming that decoder's hash.
5. Readers MUST run decoders with no imports except linear memory and the
   input buffer: no file system, network, clock, or randomness. Readers MUST
   cap memory and execution time.
6. Every resource a decoder handles MUST remain listable and extractable
   without it.
7. Packages MUST NOT list a decoder in `_ofa.requires`.

Writers SHOULD prefer converting data to a standard format at write time
over shipping a decoder.

## 14. Security considerations

Readers MUST treat every package as untrusted input.

| Threat | Requirement |
|---|---|
| **Path traversal** ("zip slip") | Readers extracting to disk MUST reject names that break section 4.4 and MUST resolve every output path inside the target directory. Data Package's own path rules add to these checks. They don't replace them. |
| **Symbolic links** | Readers MUST ignore Unix mode bits and external attributes, and MUST NOT create symlinks, devices, or executables on extraction. |
| **Decompression bombs** | Readers MUST stop inflating an entry once output exceeds the resource's `bytes`, and MUST apply a configurable limit on total decoded size and on the ratio between decoded and stored size when decompressing. |
| **Overlapping entries** | Readers MUST reject packages whose central directory records overlap (4.1 rule 8). This blocks the "overlapping file" class of ZIP bombs. |
| **Header mismatch** | Readers MUST trust the central directory and SHOULD warn when a local header disagrees with it. |
| **Polyglot files** | Rule 7 of 4.1 forbids leading data, which stops a package from also being a valid executable or PDF. Readers SHOULD reject files with leading data. |
| **Duplicate names** | Readers MUST reject packages with two entries whose names match after case folding and NFC normalisation. |
| **Manifest parsing** | Readers MUST use a JSON parser with depth and size limits and MUST reject duplicate member names. |
| **Remote fetches** | Readers MUST NOT fetch any URI from a manifest (schemas, metadata links, the `$schema` profile) without user consent. A reader that validates against the OFA profile uses a bundled copy. |
| **Active content** | Readers that render resources (HTML, SVG, PDF, Markdown) MUST disable scripts and remote loads, as a browser does for an untrusted download. |
| **Spreadsheet export** | Tools that export CSV to spreadsheet programs SHOULD neutralise cells starting with `=`, `+`, `-`, or `@`. |
| **Decoders** | Section 13. |
| **Hash scope** | A matching hash proves integrity, not authenticity. Only a verified signature (9.3) ties content to a signer. |

## 15. Privacy considerations

Manifests often carry names, timestamps, generator versions, and free-form
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
├── datapackage.json
└── hello.txt
```

```json
{
  "$schema": "https://ofa-format.org/profiles/0.3/datapackage.json",
  "title": "Hello",
  "_ofa": { "version": "0.3", "primary": "hello" },
  "resources": [
    {
      "name": "hello",
      "path": "hello.txt",
      "mediatype": "text/plain",
      "encoding": "utf-8",
      "bytes": 14,
      "hash": "sha256:d9014c4624844aa5bac314773d6b689ad467fa4e1d1a50a1b8a99d5a95f72ff5"
    }
  ]
}
```

### 17.2 Sensor log with schemas and compression

```
sensor-log.ofa
├── mimetype
├── datapackage.json
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
  "$schema": "https://ofa-format.org/profiles/0.3/datapackage.json",
  "id": "urn:uuid:5f0c2b1e-8a0e-4d0b-9c55-6a3f6f1b2c10",
  "title": "Rooftop weather stations, 1 November 2026",
  "created": "2026-11-02T08:00:00Z",
  "licenses": [{ "name": "CC-BY-4.0" }],
  "contributors": [{ "title": "Example Weather Club", "roles": ["creator"] }],
  "_ofa": {
    "version": "0.3",
    "generator": { "name": "ofa.py", "version": "0.3.0" },
    "primary": "readings",
    "lang": "en"
  },
  "resources": [
    {
      "name": "readings",
      "path": "data/readings.ndjson.gz",
      "mediatype": "application/x-ndjson",
      "compression": "gz",
      "bytes": 214,
      "hash": "sha256:…",
      "_ofa": {
        "schema": { "type": "json-schema", "resource": "reading-schema" }
      }
    },
    {
      "name": "stations",
      "type": "table",
      "path": "data/stations.csv",
      "mediatype": "text/csv",
      "encoding": "utf-8",
      "bytes": 131,
      "hash": "sha256:…",
      "schema": "schemas/stations.table.json"
    },
    {
      "name": "reading-schema",
      "path": "schemas/reading.schema.json",
      "mediatype": "application/schema+json",
      "bytes": 626,
      "hash": "sha256:…",
      "_ofa": { "role": "schema", "describes": ["readings"] }
    },
    {
      "name": "stations-schema",
      "path": "schemas/stations.table.json",
      "mediatype": "application/json",
      "bytes": 393,
      "hash": "sha256:…",
      "_ofa": { "role": "schema", "describes": ["stations"] }
    },
    {
      "name": "readme",
      "path": "README.md",
      "mediatype": "text/markdown",
      "encoding": "utf-8",
      "bytes": 412,
      "hash": "sha256:…",
      "_ofa": { "role": "documentation" }
    },
    {
      "name": "license",
      "path": "meta/LICENSE.txt",
      "mediatype": "text/plain",
      "encoding": "utf-8",
      "bytes": 110,
      "hash": "sha256:…",
      "_ofa": { "role": "license" }
    }
  ]
}
```

Hashes are elided here. Built versions of 17.2 and 17.3, with real hashes,
live in [`examples/`](examples/).

### 17.3 An application save file

An AI-generated note-taking tool saves its state as an OFA package instead of
inventing a `.mynotes` format. Any other tool can list the notes, read them
as JSON and display the attached image.

```json
{
  "$schema": "https://ofa-format.org/profiles/0.3/datapackage.json",
  "title": "Kitchen renovation notes",
  "created": "2026-10-28T19:12:00Z",
  "_ofa": {
    "version": "0.3",
    "modified": "2026-10-30T08:41:00Z",
    "generator": { "name": "quicknotes", "version": "0.3.1" },
    "primary": "notes",
    "extensions": {
      "app.quicknotes.ui": { "last_open_note": "n2", "theme": "dark" }
    }
  },
  "resources": [
    {
      "name": "notes",
      "path": "data/notes.json",
      "mediatype": "application/json",
      "bytes": 502,
      "hash": "sha256:…",
      "_ofa": {
        "schema": { "type": "json-schema", "resource": "notes-schema", "name": "#/$defs/notebook" }
      }
    },
    {
      "name": "notes-schema",
      "path": "schemas/notes.schema.json",
      "mediatype": "application/schema+json",
      "bytes": 992,
      "hash": "sha256:…",
      "_ofa": { "role": "schema", "describes": ["notes"] }
    },
    {
      "name": "sketch",
      "path": "data/attachments/sketch.png",
      "mediatype": "image/png",
      "title": "Floor plan sketch",
      "bytes": 112,
      "hash": "sha256:…",
      "_ofa": { "role": "attachment", "describes": ["notes"] }
    },
    {
      "name": "thumb",
      "path": "preview/thumbnail.png",
      "mediatype": "image/png",
      "bytes": 87,
      "hash": "sha256:…",
      "_ofa": { "role": "thumbnail" }
    }
  ]
}
```

The `app.quicknotes.ui` extension holds application state that only
`quicknotes` needs. Every other reader ignores it.

### 17.4 Binary records with Protobuf and a columnar table

```json
{
  "$schema": "https://ofa-format.org/profiles/0.3/datapackage.json",
  "_ofa": { "version": "0.3" },
  "resources": [
    {
      "name": "events",
      "path": "data/events.binpb.zst",
      "mediatype": "application/vnd.ofa.protobuf-delimited",
      "compression": "zst",
      "bytes": 48213,
      "hash": "sha256:…",
      "_ofa": {
        "schema": { "type": "protobuf", "resource": "events-fds", "name": "acme.telemetry.v1.Event" }
      }
    },
    {
      "name": "events-fds",
      "path": "schemas/telemetry.fds.binpb",
      "mediatype": "application/x-protobuf",
      "bytes": 912,
      "hash": "sha256:…",
      "_ofa": {
        "role": "schema",
        "describes": ["events"],
        "metadata": { "note": "google.protobuf.FileDescriptorSet" }
      }
    },
    {
      "name": "summary",
      "path": "data/summary.parquet",
      "mediatype": "application/vnd.apache.parquet",
      "bytes": 20480,
      "hash": "sha256:…"
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
| `schema` | Describes the structure of the resources in `describes`. |
| `metadata` | Describes the package or the resources in `describes` (for example RO-Crate, DataCite, EXIF sidecars). |
| `documentation` | Human-readable explanation, such as a README. |
| `license` | Licence text that applies to the package or to the resources in `describes`. |
| `thumbnail` | Small image representing the package or the resources in `describes`. |
| `preview` | Rendered, lossy view of other resources (PDF of a document, PNG of a chart). |
| `index` | Lookup structure that speeds up access to the resources in `describes`. Readers MAY ignore it. |
| `attachment` | Supporting file referenced by other content. |
| `source` | Original input from which other resources were derived. |
| `provenance` | Record of how the package was produced (for example W3C PROV, an RO-Crate run). |
| `decoder` | Experimental sandboxed decoder. Section 13. |

The package's `_ofa.primary` member, not a role, marks the main resource.

### A.2 Schema types

| `type` | Schema language | Schema file media type | Applies to |
|---|---|---|---|
| `json-schema` | JSON Schema 2020-12 | `application/schema+json` | JSON, NDJSON, CBOR (via its JSON data model) |
| `table-schema` | Frictionless Table Schema v2 | `application/json` | CSV, TSV |
| `avro` | Apache Avro schema (JSON form) | `application/json` | Avro binary records outside an OCF |
| `protobuf` | Protocol Buffers `FileDescriptorSet` (binary) | `application/x-protobuf` | Protobuf messages |
| `xsd` | W3C XML Schema 1.1 | `application/xml` | XML |

### A.3 Compression

Values for the `compression` property. `gz` comes from Data Package's
Compression of resources recipe. `zst` and `br` follow its convention of
naming the file extension. The recipe's `zip` value is not allowed: a ZIP
inside a package is an archive, not a compressed resource.

| Value | Format | Extension | Core |
|---|---|---|---|
| `gz` | gzip, RFC 1952 | `.gz` | yes |
| `zst` | Zstandard, RFC 8878 | `.zst` | yes |
| `br` | Brotli, RFC 7932 | `.br` | no |

### A.4 Well-known media types

**Core.** A Core reader parses all of these.

| Media type | Notes |
|---|---|
| `text/plain` | UTF-8 unless `encoding` says otherwise. |
| `text/markdown` | CommonMark. |
| `text/csv` | RFC 4180. Describe headers and delimiters with a Table Schema and, if needed, a Data Package `dialect`. |
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
- RFC 1951 (Deflate), RFC 1952 (gzip), RFC 7932 (Brotli) and RFC 8878
  (Zstandard).
- FIPS 180-4, SHA-256.
- RFC 7515, JSON Web Signature.
- RFC 9562, UUIDs.
- JSON Schema 2020-12.
- Frictionless Data Package v2, Data Resource, and Table Schema
  (<https://datapackage.org/>), and its Compression of resources recipe.

### Informative

- [research/survey.md](research/survey.md), the survey behind this draft.
- [RFC 0002](rfcs/0002-use-frictionless-data-package.md), why the manifest
  is a Data Package.
- Apache Avro, Apache Parquet, Apache Arrow, Protocol Buffers.
- MCAP, Matroska (RFC 9559), EBML (RFC 8794).
- EPUB OCF 3.3, ODF 1.3 Part 2, ECMA-376 Part 2 (OPC).
- OCI Image Specification, descriptors.
- glTF 2.0, extensions mechanism.
- RO-Crate 1.2.
- BagIt, RFC 8493, section 4 (serialization).
- Frictionless discussion #911, "Data Package Bundling (and maybe
  compression)", <https://github.com/frictionlessdata/datapackage/discussions/911>.
- [RFC 0003](rfcs/0003-frictionless-bundling-ideas.md), the ideas OFA
  adopted from that discussion.
- W3C WebAssembly Core Specification 2.0.
