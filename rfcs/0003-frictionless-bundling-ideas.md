# RFC 0003: Adopt the Frictionless community's bundling ideas

- Status: **Accepted**
- Created: 2026-11-18
- Accepted: 2026-11-18
- Affects: SPEC.md sections 4, 5, 7, 12, and Appendix A; the OFA profile;
  tools/ofa.py; the examples; a new draft recipe for Frictionless

## Summary

The Frictionless community has wanted a single-file Data Package since 2014
([datapackage discussion #911](https://github.com/frictionlessdata/datapackage/discussions/911)).
That thread, and the discussions around it, set out requirements and ideas
that nobody turned into a spec. This RFC adopts the best of them:

1. **Use Frictionless's compression property.** Compressed resources use the
   `compression` property from the Data Package "Compression of resources"
   recipe, not OFA's own `_ofa.contentEncoding`.
2. **Open existing zipped Data Packages.** Readers may open a plain zipped
   Data Package, including the "Download ZIP" layout GitHub produces, in a
   read-only compatibility mode. A new `adopt` operation upgrades one into
   an OFA package.
3. **Read without downloading everything.** The spec describes how to read
   the manifest and single resources over HTTP with range requests.
4. **Keep the bundle rules separate from ZIP.** Following the BagIt
   approach that Rufus Pollock endorsed in #911, the spec separates what a
   package is from how it is serialized. ZIP stays the only serialization
   in this version.
5. **Offer the container rules back to Frictionless.** We publish a draft
   "Zipped Data Package" recipe written for the Data Package site, with OFA
   as one stricter profile of it.

The manifest change in point 1 breaks 0.2 packages, so the spec moves to
0.3.

## Motivation

The #911 thread asked for:

- a bundle that is "widely supported in client systems";
- the "ability to access data within the bundle easily and without
  downloading the entire bundle";
- a compression algorithm, a file extension, and a MIME type;
- `datapackage.json` at the base of the ZIP, with one participant asking to
  also accept a single top-level folder, because of GitHub's ZIP downloads.

It stalled because nobody took on the drafting. OFA already answers most
of it. Adopting the rest, and giving the container rules back as a recipe,
makes OFA the continuation of that work rather than a separate project.

## Existing standards

- **Compression of resources recipe**
  (<https://datapackage.org/recipes/compression-of-resources/>):
  "the compression property MUST be used to specify the compression". It
  lists `gz` and `zip`. "All compressed resources MUST have a path that
  allows the compression property to be inferred." And "bytes, hash etc
  apply to the compressed object — not to the original uncompressed
  object", which is what OFA already does.
- **Discussion #1023** (2024) proposed promoting that recipe into the Data
  Resource spec. Maintainers of frictionless-r said they infer compression
  from the file extension and ignore the property. OFA requires both, so
  either kind of tool reads the file correctly.
- **Issue #137** asked for links to resources inside a ZIP. The maintainers
  closed it as too complex for the core spec and suggested a pattern. OFA's
  `#resource=<name>` fragment is that pattern, kept inside OFA.
- **BagIt (RFC 8493), section 4**, defines serialization rules that apply
  to any archive format. Rufus Pollock wrote in #911 that BagIt "got it
  pretty much right".

## Proposal

### 1. Compression

1. A compressed resource MUST have a `compression` property, as the
   Compression of resources recipe defines.
2. Its value MUST be one of `gz` (gzip, RFC 1952), `zst` (Zstandard,
   RFC 8878) or `br` (Brotli, RFC 7932). `gz` comes from the recipe. `zst`
   and `br` follow the recipe's convention of naming the file extension.
   The recipe's `zip` value is not allowed, because a ZIP inside an OFA
   package is an archive, not a compressed resource.
3. The resource's `path` MUST end with the matching extension: `.gz`,
   `.zst` or `.br`.
4. A resource has at most one compression step. `_ofa.contentEncoding` is
   removed.
5. `mediatype` names the decoded bytes, as before. `bytes` and `hash`
   apply to the stored, compressed bytes, as the recipe says.
6. Core readers MUST support `gz` and `zst`.

### 2. Compatibility mode and `adopt`

A **plain zipped Data Package** is a ZIP file that holds exactly one
`datapackage.json`, either at the root or inside a single top-level folder,
and has no `mimetype` entry.

1. Readers MAY open a plain zipped Data Package in **compatibility mode**.
   In that mode a reader lists resources and extracts their bytes, MUST
   warn that the file is not an OFA package, and MUST NOT report hashes as
   verified unless the descriptor provides SHA-256 hashes that match.
2. Readers MUST still apply every security rule in section 14.
3. **Adopt** turns a plain zipped Data Package or a folder into an OFA
   package. An adopting writer MUST:
   - write `mimetype` first and `datapackage.json` second, at the root;
   - drop the top-level folder from paths, if there was one;
   - add `$schema` and `_ofa.version`, and fill in `bytes` and `hash`;
   - describe every other file it keeps as a resource, with a media type
     guessed from the extension and a role guessed from the name (for
     example `README` gets `documentation`, `LICENSE` gets `license`);
   - fail, with a clear message, on resources it cannot carry: URLs in
     `path`, inline `data`, and multipart `path` arrays.
   It SHOULD keep every other property of the original descriptor as it
   was.

### 3. Reading over HTTP

A new SPEC section says how a reader can open a package on a web server
that supports HTTP range requests, without downloading all of it:

1. Fetch the end of the file to find the end of central directory record,
   then fetch the central directory.
2. Fetch the start of the file to read `mimetype` and `datapackage.json`,
   which OFA places first and second.
3. Fetch only the entries the user asks for.

Writers SHOULD store large resources uncompressed at the ZIP level (method
0, with the 64-byte alignment that 4.1 already allows), so that readers can
fetch byte ranges inside them. A URL the user gives to a reader counts as
consent to fetch it.

### 4. Package model and serialization

SPEC section 4 is split into:

- **4.1 Package model.** A package is a set of named entries: an
  identification entry, a manifest, and the resources it describes, plus
  optional signatures. These rules don't depend on the archive format.
- **4.2 onwards: ZIP serialization.** The current rules, unchanged.

Another serialization, such as `tar` with Zstandard for files written while
recording, needs its own RFC and its own media type. This RFC adds none.

### 5. A recipe for Frictionless

`recipes/zipped-data-package.md` is a draft written in the style of the
Data Package recipes. It defines the minimum any zipped Data Package should
follow, so that every Frictionless tool can open one. OFA is a stricter
profile of it. We'll offer it in #911 and ask the maintainers whether
they'd like it as a recipe on their site.

## Compatibility

- **0.2 packages** that use `_ofa.contentEncoding` become invalid. Nobody
  outside this repository writes them, so we take the break now. The
  version moves to 0.3, and the profile moves to `profiles/0.3/`.
- **Frictionless tools** gain: compressed OFA resources now use the
  property frictionless-py already supports.
- **Plain zipped Data Packages** can now be read by OFA tools and upgraded
  into OFA packages.

## Security and privacy

- Compatibility mode opens files without the `mimetype` check, so readers
  rely on the ZIP and path rules in section 14 alone. They MUST apply all
  of them.
- HTTP range reading fetches data from the network. Readers do it only for
  a URL the user gave them, and MUST NOT follow URLs found inside the
  package.
- `adopt` guesses media types and roles. Writers SHOULD show the user what
  they guessed.

## Alternatives considered

1. **Keep `_ofa.contentEncoding`.** It allows chains of codings and HTTP
   names, but no Frictionless tool reads it. Alignment matters more.
2. **Allow `datapackage.json` in a top-level folder in OFA packages too.**
   That would break the fixed-offset `mimetype` check and make two layouts
   valid. Compatibility mode covers the real need, which is reading
   GitHub ZIPs.
3. **Wait for Frictionless to publish a recipe first.** #911 has waited
   since 2014. A concrete draft is the most useful contribution.

## Open questions

1. Will the Frictionless maintainers want `zst` and `br` added to the
   compression recipe?
2. Should compatibility mode also accept a ZIP with several
   `datapackage.json` files, opening one chosen by the user?
