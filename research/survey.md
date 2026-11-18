# Survey of existing packaging and self-describing formats

Status: research note, November 2026. Informs [SPEC.md](../SPEC.md) and
[RFC 0001](../rfcs/0001-extension-and-media-type.md).

We want one container that any program can open and list, and that a program
can fully decode when the contents use common encodings. This note looks at
the formats that already solve parts of that problem and records what we
borrow from each.

## 1. ZIP plus a manifest

### OPC (Open Packaging Conventions, ECMA-376 Part 2 / ISO/IEC 29500-2)

Used by `.docx`, `.xlsx`, `.pptx`, `.3mf`, `.nupkg`, `.vsix`.

- **Does well.** `[Content_Types].xml` gives every part a media type.
  Relationship files (`_rels/*.rels`) form a typed graph between parts, so a
  reader can find the main document without guessing. Two decades of tooling.
- **Falls short.** XML everywhere. Media types default by file extension,
  which invites mismatch. Part names carry odd rules (percent-encoding, the
  bracketed `[Content_Types].xml` name). No per-part hashes outside the
  optional XML-DSig signature layer. The schema for a part is implied by its
  media type and lives outside the package.
- **Lesson.** Give every entry an explicit media type. Name a starting point.
  Keep relationships, but as a field on the entry, not as separate files.

### EPUB OCF 3.3 and ODF packages (OASIS ODF 1.3 Part 2)

- **Does well.** The first ZIP entry is a file named `mimetype`, stored
  uncompressed with no extra field. Its contents sit at a fixed byte offset,
  so `file(1)` and any sniffer can identify the package from the first 60-odd
  bytes. ODF's `META-INF/manifest.xml` lists every file with its media type.
  EPUB's `container.xml` points at one or more root files.
- **Falls short.** Domain-specific (books, office documents). XML. No content
  hashes. Encryption rules (`encryption.xml`) add complexity a general format
  does not need.
- **Lesson.** Copy the `mimetype` first-entry trick exactly. It costs nothing
  and gives reliable magic bytes on top of ZIP.

### Adobe UCF (Universal Container Format)

Adobe generalized OCF into UCF for AIR, IDML, and others.

- **Does well.** Proves the OCF pattern works outside e-books.
- **Falls short.** No living specification, no schema or codec declarations,
  no hashes. Adobe stopped developing it.
- **Lesson.** A generic ZIP container with no data semantics does not get
  adopted on its own. The value lies in the manifest vocabulary.

### JAR (`META-INF/MANIFEST.MF`)

- **Does well.** Per-entry digests (`SHA-256-Digest`) in the manifest, then a
  signature over the manifest. Signing one small file covers every entry.
- **Falls short.** A line-wrapped key-value syntax with a 72-byte limit.
  Built for executable code.
- **Lesson.** Put a digest for each entry in the manifest. Sign the manifest
  bytes, never the whole archive.

### RO-Crate 1.2

- **Does well.** JSON-LD metadata (`ro-crate-metadata.json`) with schema.org
  terms, strong uptake in research data management, and a zipped form.
- **Falls short.** It describes provenance and context, not how to decode a
  byte stream. JSON-LD processing pulls in a lot of machinery for a reader
  that only wants a file list.
- **Lesson.** Interoperate, do not compete. A package may carry an RO-Crate
  metadata file as one more stream with role `metadata`.

### Frictionless Data Package v2 and BagIt (RFC 8493)

- **Frictionless** has a JSON descriptor (`datapackage.json`) whose resources
  carry `path`, `mediatype`, `encoding`, `hash`, and a `schema` (Table
  Schema). This sits closest to what we want. It targets tabular data and does
  not define a single-file binary container or a codec story.
- **BagIt** gives libraries and archives a simple fixity model: payload files
  plus checksum manifests. No media types, no schemas.
- **Lesson.** Reuse Frictionless field names where they fit (`path`,
  `mediatype` style, `hash`), and accept Table Schema as a schema type. Take
  BagIt's rule that a checksum covers every payload file.

## 2. Single-stream self-describing formats

### Avro Object Container Files

- **Does well.** The header stores the writer's schema as JSON plus the codec
  name (`null`, `deflate`, `snappy`, `zstandard`, `bzip2`, `xz`). Sync markers
  make files splittable. Any Avro reader decodes any Avro file.
- **Falls short.** One file holds one record stream with one schema. No place
  for images, documents, or a second table.
- **Lesson.** Embed the schema with the data. Declare the codec by name from
  a short list.

### Parquet and Arrow IPC

Both carry their own schemas and both have registered media types
(`application/vnd.apache.parquet`, `application/vnd.apache.arrow.file`).

- **Lesson.** Do not reinvent columnar storage. A package stream can be a
  Parquet file. The package manifest only needs to say so.

## 3. Multi-stream binary containers

### Matroska / EBML (RFC 8794, RFC 9559)

- **Does well.** Every element carries an ID and a length, so a reader skips
  unknown elements safely. Tracks declare a `CodecID`. Attachments and tags
  sit next to the media. Append-friendly and streamable.
- **Falls short.** EBML parsers exist mostly in media stacks. Codec IDs mean
  audio and video codecs, not data schemas. A general tool cannot list an
  EBML file without an EBML library, while every language ships ZIP support.
- **Lesson.** The skip-unknown rule. We keep EBML as a candidate for a future
  streaming profile, not for version 0.1.

### MCAP

- **Does well.** Separates schema encoding (`jsonschema`, `protobuf`,
  `ros2msg`, `flatbuffer`) from message encoding, and keeps a public registry
  of well-known encoding strings. Schemas live in the file. Chunked, indexed,
  compressed with LZ4 or Zstandard. Registered media type
  `application/vnd.mcap`.
- **Falls short.** It models timestamped message channels. A spreadsheet, a
  photo set or an application save file fits badly.
- **Lesson.** Two separate fields for "what schema language" and "what bytes
  on disk", each drawn from a published registry of short strings. If a
  package needs time-series logs, the stream should be an MCAP file.

### HDF5 and Zarr v3

- **HDF5** offers groups, typed n-dimensional datasets, attributes, and
  chunking with registered filter IDs. In practice one C library defines the
  format, the spec runs to hundreds of pages, and filter plugins are native
  code loaded at read time. That plugin model is the security problem we want
  to avoid.
- **Zarr v3** stores arrays as JSON metadata plus chunk files, and declares
  codecs as an ordered pipeline in JSON. Zarr can live inside a ZIP.
- **Lesson.** Declare transformations as an ordered list of named codecs. Keep
  the list short and the names registered.

## 4. Other relevant prior art

| Format | What we take |
|---|---|
| **OCI image layout and descriptors** | The descriptor triple `{mediaType, digest, size}`, with digests written `sha256:<hex>`. Content addressing that every container tool already understands. |
| **glTF 2.0 / GLB** | `extensionsUsed` and `extensionsRequired`. A reader ignores an unknown extension unless the file lists it as required. We copy this as `extensions` and `requires`. |
| **ISO/IEC 21320-1 (Document Container File)** | A published ZIP subset: Stored and Deflate only, no encryption, UTF-8 names. Our ZIP profile starts from it. |
| **USDZ** | Uncompressed entries aligned to 64 bytes so readers can memory-map them. We allow this as an optional writer practice. |
| **NumPy `.npz`** | A ZIP of self-describing `.npy` arrays. Proof that "ZIP of typed files" works for numeric data. |
| **SQLite** (a Library of Congress recommended format) | A strong single-file store, but one implementation defines it and it does not stream. Fine as a stream inside a package (`application/vnd.sqlite3`), wrong as the container. |
| **tar** | No central index, so listing means reading the whole file. Rejected as the container. |

## 5. Where existing formats fall short as a universal package

1. **No common manifest.** Each ZIP-based format invents its own (XML,
   key-value, JSON-LD) and its own name for it.
2. **Schemas live elsewhere.** OPC, OCF, and UCF tell you a media type and
   stop. A program that meets an unfamiliar JSON or binary entry has no
   machine-readable description of it.
3. **Integrity is optional or absent.** Only JAR and BagIt put a digest on
   every entry by default.
4. **Executable decoding.** HDF5 filter plugins and some media pipelines load
   native code to read data. A universal format has to keep that out of the
   default path.
5. **Single-purpose binary containers** (Avro, MCAP, Matroska) each serve one
   data shape well. None packages heterogeneous files.

## 6. Minimal set of standards to build on

| Concern | Standard | Why |
|---|---|---|
| Container | ZIP (PKWARE APPNOTE 6.3.10), profiled by ISO/IEC 21320-1, plus ZIP64 | Every OS and language reads it. Central directory gives random access. |
| Identification | First entry `mimetype` (OCF pattern) | Fixed-offset magic bytes. |
| Manifest syntax | JSON, RFC 8259, restricted by I-JSON (RFC 7493) | Universal parser support. Readable in any text editor. |
| Media types | IANA Media Types registry (RFC 6838), `+zip` suffix (RFC 6839) | Existing vocabulary for "what is this file". |
| Byte codecs | IANA HTTP Content Coding registry: `gzip` (RFC 1952), `deflate` (RFC 1951), `br` (RFC 7932), `zstd` (RFC 8878) | Names already registered and implemented in every browser and HTTP stack. |
| Digests | SHA-256 (FIPS 180-4), written as in OCI descriptors | One algorithm, universal support. |
| Schemas | JSON Schema 2020-12, Apache Avro, Protocol Buffers (`FileDescriptorSet`), Frictionless Table Schema | Declarative, widely implemented, cover JSON, tabular, and binary records. |
| Identifiers and times | UUID (RFC 9562), RFC 3339 timestamps, BCP 47 language tags, URIs (RFC 3986) | Standard building blocks. |
| Signatures (optional) | JWS with detached payload (RFC 7515, Appendix F) | Libraries exist in every language. COSE (RFC 9052) as a later option. |
| Sandboxed decoders (experimental) | WebAssembly Core 2.0 (W3C) | The only widely deployed sandbox with a formal spec. |

## 7. Decisions this survey supports

- ZIP, not EBML, for version 0.1. Revisit EBML or MCAP-style chunking through
  an RFC if append-while-recording becomes a requirement.
- JSON for the manifest. CBOR stays allowed as a stream encoding, but one
  manifest syntax keeps every reader simple.
- Every entry appears in the manifest with media type, size, and digest.
- Two vocabularies drawn from existing registries: media type for "what the
  bytes are", content coding for "how they were compressed". One new
  vocabulary of our own: `role`.
- Schemas are ordinary streams inside the package, referenced by ID.
- Executable decoders sit outside conformance, behind explicit user consent.

## Sources

- ECMA-376 Part 2, Open Packaging Conventions: <https://ecma-international.org/publications-and-standards/standards/ecma-376/>
- EPUB Open Container Format 3.3: <https://www.w3.org/TR/epub-33/#sec-ocf>
- OASIS ODF 1.3 Part 2, Packages: <https://docs.oasis-open.org/office/OpenDocument/v1.3/>
- JAR File Specification: <https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html>
- RO-Crate 1.2: <https://www.researchobject.org/ro-crate/specification/1.2/>
- Frictionless Data Package v2: <https://datapackage.org/standard/data-package/>
- BagIt, RFC 8493: <https://www.rfc-editor.org/rfc/rfc8493>
- Apache Avro specification, Object Container Files: <https://avro.apache.org/docs/1.12.0/specification/>
- EBML, RFC 8794: <https://www.rfc-editor.org/rfc/rfc8794>; Matroska, RFC 9559: <https://www.rfc-editor.org/rfc/rfc9559>
- MCAP format specification and registry: <https://mcap.dev/spec>, <https://mcap.dev/spec/registry>
- Zarr v3 core specification: <https://zarr-specs.readthedocs.io/en/latest/v3/core/>
- OCI Image Spec, descriptors: <https://github.com/opencontainers/image-spec/blob/main/descriptor.md>
- glTF 2.0 specification: <https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html>
- PKWARE APPNOTE: <https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT>
- IANA HTTP Content Coding Registry: <https://www.iana.org/assignments/http-parameters/>
