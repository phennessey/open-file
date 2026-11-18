# Zipped Data Package

Draft recipe, written for the
[Data Package recipes](https://datapackage.org/recipes/) and offered to the
Frictionless community in
[discussion #911](https://github.com/frictionlessdata/datapackage/discussions/911).
It is not part of the Data Package standard.

## Overview

People often need to send a Data Package as one file: to email it, upload
it to a portal, or attach it to a paper. Many tools already read and write
zipped Data Packages, but nothing says what a zipped Data Package must look
like. Discussion #911 asked for exactly this in 2014, with these goals:

- a format that is widely supported in client systems;
- a way to read data in the bundle without downloading all of it;
- clear rules for compression, the file extension, and the MIME type.

This recipe sets the minimum rules a zipped Data Package should follow so
that any tool can open one.

## Specification

1. **Format.** A zipped Data Package is a ZIP file (PKWARE APPNOTE 6.3.10
   or later). Entries MUST use compression method 0 (Stored) or 8
   (Deflate). Entries MUST NOT be encrypted. ZIP64 MAY be used.
2. **Descriptor.** The file MUST contain exactly one `datapackage.json`.
   It SHOULD be at the root of the ZIP. Readers SHOULD also accept it
   inside a single top-level folder, which is what GitHub's "Download ZIP"
   produces.
3. **Paths.** Every resource `path` is relative to the folder that holds
   `datapackage.json`, as the Data Package standard already requires.
   Resources SHOULD be files inside the ZIP, not URLs.
4. **File names.** Entry names MUST be UTF-8, with the ZIP language
   encoding flag (general purpose bit 11) set on any name that isn't plain
   ASCII. This avoids the file name encoding problems raised in #911.
5. **Compressed resources** follow the
   [Compression of resources](https://datapackage.org/recipes/compression-of-resources/)
   recipe. Writers SHOULD store an already compressed file with method 0, so
   it isn't compressed twice.
6. **Integrity.** `bytes` and `hash` describe each file as stored in the
   ZIP, after any resource-level compression. Writers SHOULD give a hash
   for every resource.
7. **Extension and media type.** A zipped Data Package that follows only
   this recipe uses the `.zip` extension and `application/zip`.
8. **Reading over HTTP.** Writers SHOULD put `datapackage.json` early in
   the ZIP and store large files with method 0, so a reader can fetch the
   descriptor and single files with HTTP range requests.

## Profiles

A profile can add stricter rules, its own extension, and its own media type.
[Open File Archive (OFA)](https://github.com/phennessey/open-file) is one
such profile. It requires a `mimetype` entry first and `datapackage.json`
second, SHA-256 hashes on every resource, and the `.ofa` extension with
`application/vnd.ofa+zip`. Every OFA file is a valid zipped Data Package.

## Implementations

- `frictionless-py` reads and writes zipped Data Packages.
- `tools/ofa.py` in the OFA repository reads zipped Data Packages in a
  compatibility mode and converts them to OFA with its `adopt` command.

## Credits

This recipe collects ideas from discussion #911 and its participants. The
serialization approach follows BagIt (RFC 8493, section 4), which that
discussion pointed to.
