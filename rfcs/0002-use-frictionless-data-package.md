# RFC 0002: Use Frictionless Data Package as the manifest

- Status: **Accepted**
- Created: 2026-11-18
- Accepted: 2026-11-18
- Affects: SPEC.md sections 4, 5, 6.1, 8, 9, 10, and Appendix A; the JSON
  Schema; tools/ofa.py; the examples

## Summary

Replace `ofa.json` with a standard Frictionless Data Package descriptor,
`datapackage.json`, as published in Data Package v2. We don't change the
Data Package standard. OFA uses it as is, and adds what Data Package
leaves out:

- the single-file container;
- the `.ofa` file type and media type;
- per-file compression, roles, and integrity rules.

OFA keeps those additions in private `_ofa` properties, which Data Package
already allows.

The pitch becomes: **an OFA file is a Data Package in a single file.**

## Motivation

Draft 0.1 defined its own manifest. For each file it records a path, media
type, size, hash, and schema. Frictionless Data Package already records the
same things, and it has a community, a published standard, and libraries in
Python, JavaScript, R, and other languages.

Two descriptors for the same job split tools and users. If OFA uses Data
Package, every Frictionless tool can read an OFA manifest on day one. OFA
then only has to specify the parts that are new.

## Existing standards

We checked Data Package v2 (datapackage.org, "v2 (current)",
checked 2026-11-18). The rules OFA relies on:

- **Descriptor name and place.** "a descriptor MUST be named
  datapackage.json" and placed at the top level of the file structure.
- **Required content.** "The resources property is REQUIRED, with at least
  one resource."
- **Additional properties.** "A descriptor MAY include any number of
  properties in additional to those described".
- **Private properties.** The Private Properties recipe says properties
  that software generates "SHOULD be considered as 'private', and be
  prefixed by an underscore `_`".
- **Profiles.** A root-level `$schema` names a JSON Schema (draft-07) that
  the descriptor must be valid against. This is how Data Package declares
  a profile.
- **Paths.** Local paths "MUST be relative siblings or children of the
  descriptor". Absolute paths, `../` and hidden folders starting with a
  dot "MUST NOT be used".
- **Hashes.** The default algorithm is MD5. Other algorithms are written
  as a lowercase name prefix, such as `sha1:…`.
- **Schemas.** A tabular resource's `schema` is a Table Schema. The JSON
  Data Resource recipe uses the same `schema` property for a JSON Schema.

Data Package says nothing about zipped packages, file types, or media
types. OFA fills that gap.

## Proposal

### 1. The manifest

1. Every package MUST contain an entry named `datapackage.json` at the
   root. It MUST be the second entry in the ZIP, after `mimetype`. It
   replaces `ofa.json`.
2. `datapackage.json` MUST be a valid Data Package v2 descriptor.
3. It MUST have a root `$schema` naming the OFA profile:
   `https://ofa-format.org/profiles/0.2/datapackage.json`. The OFA profile
   is a JSON Schema that extends the Data Package v2 profile with the rules
   in this RFC. (`ofa-format.org` is a placeholder until the project has a
   domain.)
4. The descriptor MUST also follow the existing OFA manifest rules: I-JSON
   (RFC 7493), UTF-8 without a byte order mark, no duplicate member names,
   16 MiB at most.

### 2. Package-level fields

| Draft 0.1 (`ofa.json`) | This RFC (`datapackage.json`) |
|---|---|
| `ofa` (spec version) | `_ofa.version`, plus the version in the `$schema` URL |
| `streams` | `resources` |
| `id` | `id` (native) |
| `title`, `description` | `title`, `description` (native) |
| `created` | `created` (native) |
| `modified` | `_ofa.modified` |
| `generator` | `_ofa.generator` |
| `primary` | `_ofa.primary` (a resource `name`) |
| `lang` | `_ofa.lang` |
| `metadata.license` and similar | native fields where Data Package has them: `licenses`, `contributors`, `sources`, `keywords`, `homepage`, `version` |
| `extensions`, `requires` | `_ofa.extensions`, `_ofa.requires` |

### 3. Resource fields

| Draft 0.1 stream field | This RFC resource field |
|---|---|
| `id` | `name` (native). OFA requires the Data Package naming advice: lowercase letters, digits, `.`, `-`, and `_` only. |
| `path` | `path` (native). MUST be a single string naming a ZIP entry. Arrays, URLs, and inline `data` are not allowed. |
| `media_type` | `mediatype` (native). The media type of the decoded bytes. See open question 1. |
| `size` | `bytes` (native). Length of the stored bytes. |
| `digest` | `hash` (native). MUST use the `sha256:` prefix and 64 lowercase hex digits. |
| `content_encoding` | `_ofa.contentEncoding`. Same values and order as draft 0.1. |
| `role` | `_ofa.role`. Same registry as draft 0.1. Default `data`. |
| `describes` | `_ofa.describes`. A list of resource names. |
| `schema` | `schema` (native) when Data Package defines it. Otherwise `_ofa.schema`. See section 4. |
| `title`, `description` | `title`, `description` (native) |
| `lang` | `_ofa.lang` |
| `metadata`, `extensions` | native fields where they exist, else `_ofa.metadata`, `_ofa.extensions` |

Each resource MUST have `name`, `path`, `mediatype`, `bytes`, and `hash`.
Data Package makes only `name` and one of `path` or `data` required, so
OFA is stricter. Every OFA descriptor is still a valid Data Package.

### 4. Schemas

1. A tabular resource (`"type": "table"`) MUST put its Table Schema in the
   native `schema` property, as a path to a resource in the package.
2. A JSON resource MAY put a JSON Schema in the native `schema` property,
   as the JSON Data Resource recipe describes.
3. Any other schema, such as JSON Schema for each record of an NDJSON
   file, or Avro, Protobuf, or Parquet, goes in `_ofa.schema`. It uses the
   draft 0.1 schema reference, with `resource` in place of `stream`:
   `{ "type": "json-schema", "resource": "reading-schema" }`.
4. Schema files remain resources of their own, with
   `"_ofa": { "role": "schema", "describes": [...] }`.

### 5. Unchanged rules

The rest of draft 0.1 stays as written:

- the container profile (section 4), including the `mimetype` entry and
  `application/vnd.ofa+zip`;
- the decoding pipeline (section 7);
- detached JWS signatures (section 9), now computed over the bytes of
  `datapackage.json`;
- the security rules (section 14);
- the rule that writers describe every entry. The exemptions become
  `mimetype`, `datapackage.json`, `signatures/`, and `META-INF/`.

The reserved directory `_ofa/` stays. It doesn't start with a dot, so Data
Package's ban on hidden folders doesn't affect it.

### Example

The `sensor-log` example under this RFC:

```json
{
  "$schema": "https://ofa-format.org/profiles/0.2/datapackage.json",
  "id": "urn:uuid:5f0c2b1e-8a0e-4d0b-9c55-6a3f6f1b2c10",
  "title": "Rooftop weather stations, 1 November 2026",
  "created": "2026-11-02T08:00:00Z",
  "licenses": [{ "name": "CC-BY-4.0" }],
  "contributors": [{ "title": "Example Weather Club", "roles": ["creator"] }],
  "_ofa": {
    "version": "0.2",
    "generator": { "name": "ofa.py", "version": "0.2.0" },
    "primary": "readings",
    "lang": "en"
  },
  "resources": [
    {
      "name": "readings",
      "path": "data/readings.ndjson.gz",
      "mediatype": "application/x-ndjson",
      "bytes": 214,
      "hash": "sha256:…",
      "_ofa": {
        "contentEncoding": ["gzip"],
        "schema": { "type": "json-schema", "resource": "reading-schema" }
      }
    },
    {
      "name": "stations",
      "type": "table",
      "path": "data/stations.csv",
      "mediatype": "text/csv",
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
      "bytes": 412,
      "hash": "sha256:…",
      "_ofa": { "role": "documentation" }
    },
    {
      "name": "license",
      "path": "meta/LICENSE.txt",
      "mediatype": "text/plain",
      "bytes": 110,
      "hash": "sha256:…",
      "_ofa": { "role": "license" }
    }
  ]
}
```

## Compatibility

- **Existing packages.** Draft 0.1 packages become invalid. Nobody outside
  this repository writes them yet, so we accept the break now rather than
  after 1.0. We will rebuild the three examples.
- **Frictionless tools.** They can read the manifest of any OFA package
  once someone unzips it. They ignore `_ofa` properties, so they see the
  files, media types, sizes, hashes, and Table Schemas. They don't know
  about content codings, so they may misread a compressed file (open
  question 1).
- **Draft 0.1 readers.** They won't find `ofa.json` and will reject the
  package. Inspect-level readers can still list the ZIP.

## Security and privacy

- Readers now parse a Data Package descriptor. The OFA rules on size,
  duplicate keys and byte order marks still apply before parsing.
- Data Package allows URLs in `path`. OFA forbids them, so a reader never
  fetches a resource from the network.
- Data Package's path rules (no absolute paths, no `../`, no hidden
  folders) add to OFA's existing ZIP path checks. They don't replace them.
- Readers MUST NOT fetch the `$schema` profile URL by default. A reader
  that validates against the profile uses a bundled copy.

## Alternatives considered

1. **Keep `ofa.json` and use Data Package field names.** Converters would
   be simple, but users would still see two descriptors, and Frictionless
   tools couldn't read OFA manifests directly.
2. **Keep `ofa.json` and carry a `datapackage.json` as an extra stream.**
   Packages would carry two manifests that could disagree.
3. **Propose OFA's fields to Frictionless as a new Data Package profile
   upstream.** That could follow later. This RFC needs nothing from the
   Frictionless project except its published standard.

## Decisions on the open questions

When we accepted this RFC we settled questions 1 to 3 as follows. We still
want the Frictionless community's view on question 1.

- **Question 1:** `mediatype` names the decoded bytes, and writers SHOULD
  give compressed files the usual extension of their coding (`.gz`, `.zst`,
  `.br`). SPEC section 5.5.
- **Question 2:** one `_ofa` object per descriptor.
- **Question 3:** no inline `data`. Every resource is a ZIP entry.

## Open questions

1. **Media type of compressed resources.** OFA's `mediatype` names the
   decoded bytes (`application/x-ndjson`), while the file at `path` is
   gzip. A Frictionless tool that ignores `_ofa.contentEncoding` might treat
   the gzip bytes as NDJSON. Options: name the decoded type and rely on the
   `.gz` extension, which the Frictionless framework uses to detect
   compression; or name the stored type (`application/gzip`) and put the
   decoded type in `_ofa`. We should ask the Frictionless community which
   one their tools handle.
2. **One `_ofa` object or separate `_ofa…` properties.** This RFC uses one
   object per descriptor. The Private Properties recipe shows
   single properties such as `_platformVersion`. Both follow the underscore
   rule.
3. **Inline `data`.** Should OFA allow small resources inline in the
   descriptor, as Data Package does? This RFC says no, so every resource is
   a ZIP entry with a hash.
4. **Profile hosting.** The `$schema` URL needs a stable home before the
   profile can be published.
