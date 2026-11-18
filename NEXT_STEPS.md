# Next steps

Ordered by what unblocks the most. Dates assume one or two part-time
maintainers.

## 1. Settle the name (weeks 1–2)

- [x] Decide on RFC 0001. The format is Open File Archive (`.ofa`).
- [ ] Run a trademark search for "Open File Archive" and "OFA" in software,
      and a web search for current `.ofa` use.
- [ ] Register a domain for the project (for schema `$id` URIs and the macOS
      UTI). The JSON Schema currently uses `ofa-format.org` as a
      placeholder.
- [x] Replace the `LICENSE` notice with the full Apache 2.0 text.
- [ ] Publish the repository on GitHub. Turn on Discussions and private
      vulnerability reporting.

## 2. Reference implementations (weeks 2–8)

Priority follows "who writes the most new tools".

1. **Python library** (`ofa` on PyPI). Turn `tools/ofa.py` into a package
   with a reading API (`open`, `streams`, `read_decoded`, `validate`) and a
   writing API that computes digests as it streams. Python is where data
   people and AI-generated scripts live.
2. **TypeScript library** (npm). Browser and Node. Lets web apps and
   Electron tools save `.ofa` files, and lets a web page inspect one with a
   drag and drop.
3. **Rust crate with a CLI** (`ofa ls/verify/cat/pack`). One static binary
   that people can install with a package manager. Fast enough for
   multi-gigabyte packages.
4. **Go library**, after the first three, for infrastructure tools.

Each implementation states its conformance level (Inspect, Core, Extended).

## 3. Conformance suite (weeks 4–10)

- [ ] `conformance/valid/`: packages every reader must accept, with the
      expected listing as JSON.
- [ ] `conformance/invalid/`: packages every reader must reject, one rule
      each: zip slip, overlapping entries, duplicate names after case
      folding, compressed `mimetype`, bad digest, duplicate JSON members,
      leading data, encrypted entry.
- [ ] `conformance/warn/`: undescribed entries, unknown major version,
      unknown required extension.
- [ ] A runner script that takes any implementation's CLI and reports
      pass/fail.

## 4. Make it easy to adopt (weeks 6–12)

- [ ] **An LLM-ready summary.** A single page (`docs/llms.txt` or similar)
      that an AI coding assistant can read to emit correct OFA writers.
      This directly targets the format-proliferation problem.
- [ ] **A web inspector.** Static page, runs locally in the browser, lists
      streams, renders JSON, CSV, Markdown and images, validates schemas.
- [ ] **`file(1)` / libmagic rule** and a **shared-mime-info** entry for
      Linux desktops, so `.ofa` files get an icon and a type.
- [ ] **IANA registration** of `application/vnd.ofa+zip`, using the
      template in RFC 0001.
- [ ] **Converters**: Frictionless Data Package to OFA and back, RO-Crate
      zip to OFA and back, folder plus heuristics to OFA.

## 5. Communities to engage

| Community | Why they care | First contact |
|---|---|---|
| Frictionless Data / Open Knowledge Foundation | Closest existing descriptor. Alignment avoids a competing standard. | Propose a mapping doc and ask for review. |
| RO-Crate and research data managers | Need a single-file, verifiable package. | Show RO-Crate metadata carried as a stream. |
| Library of Congress Sustainability of Digital Formats, UK National Archives (PRONOM), Digital Preservation Coalition | Format registries and preservation guidance. | Submit a PRONOM signature once the magic bytes are final. |
| MCAP / Foxglove, Apache Arrow and Parquet maintainers | Their formats become OFA streams. Agree on media type names. | Ask about `application/avro` and Protobuf delimited naming. |
| AI coding assistant and agent-framework builders | They decide what format a generated tool writes. | Ship the LLM-ready summary and a one-line "save as OFA" snippet per language. |
| Local-first software community (Ink & Switch, Automerge users) | Care about data that outlives apps. | Talk at a meetup, ask what OFA misses for app save files. |
| Jupyter and notebook tool authors | Notebooks plus data plus outputs fit the package model. | Prototype "export notebook with data as OFA". |

## 6. Possible early adopters

- Small AI-generated or no-code tools that need a save format today.
- Citizen science and field-data projects that ship CSV plus photos plus
  metadata.
- Lab instrument exports that currently produce a folder of mixed files.
- Data journalism teams publishing a dataset with its documentation.
- Game modding and level editors that bundle JSON plus assets.

## 7. Open questions

1. **Streaming and append.** ZIP writes its central directory last. Do we
   need a second profile for append-while-recording (EBML or an MCAP-style
   chunked layout), or is "put an MCAP stream inside" enough?
2. **Large packages.** Should streams split across several entries
   (`parts`) for parallel writes and resumable uploads, or does ZIP64 cover
   real needs?
3. **CBOR manifests.** Is a binary manifest worth a second parsing path? The
   draft says no.
4. **NDJSON media type.** Keep `application/x-ndjson`, switch to
   `application/jsonl`, or adopt RFC 7464 `application/json-seq`?
5. **Avro and Protobuf media types.** Register `vnd.` names, or push the
   Apache and Google projects to register their own?
6. **Signatures.** JWS only, or also COSE and Sigstore bundles?
7. **Decoder interface.** If sandboxed decoders go ahead, should they use
   the WebAssembly Component Model and WIT, or a minimal core-module ABI?
8. **Governance.** Stay an independent project, or move under a foundation
   (Linux Foundation, OKFN, or a W3C Community Group) once there are three
   independent implementations?
9. **Patent policy.** Adopt a royalty-free commitment for contributors to
   the spec, as W3C does, before accepting outside RFCs.
10. **Mutable packages.** Should the spec say how an application updates a
    package in place (rewrite versus append a new central directory), or
    leave that to libraries?

## 8. Milestones

| Version | Exit criteria |
|---|---|
| 0.2 | Name settled, conformance suite v1, Python and TypeScript libraries at Core level. |
| 0.3 | Rust CLI, web inspector, IANA registration filed, two outside projects writing packages. |
| 1.0 | Three independent implementations pass the conformance suite. No breaking change for six months. Governance and patent policy in place. |
