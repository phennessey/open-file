# RFC 0001: File extension and media type

- Status: **Accepted**
- Created: 2026-11-17
- Accepted: 2026-11-18
- Affects: SPEC.md sections 4 and 16

## Summary

Name the format **Open File Archive (OFA)**. Use **`.ofa`** as the file
extension and **`application/vnd.ofa+zip`** as the media type.

## Requirements

The maintainers set these requirements while comparing names:

1. **Adoption first.** The name must be easy to say and spell, and must not
   read as weird or clever.
2. **Three letters.** Long extensions hurt usability, and every common
   format people know (`.zip`, `.pdf`, `.csv`, `.png`) has three.
3. **Starts with "Open".** "Open" tells people the format is open source and
   will keep evolving, which matters for adoption. We rejected "Universal"
   because it promises something no format can keep.
4. **Available.** No software has used the extension in the last 20 years
   (since about 2006).

## How we checked

For each candidate we searched three extension databases (fileinfo.com,
file-extensions.org and filext.com) and ran a GitHub code search for files
with that extension. The databases miss newer formats, so the GitHub search
decided close calls. Checks ran on 17 and 18 November 2026.

## Final candidates

| Extension | Full name | Earlier use | Result |
|---|---|---|---|
| **`.ofa`** | Open File Archive | Kodak OfotoNow data files. Kodak replaced Ofoto with EasyShare Gallery in 2005. Five minor GitHub repos, none of them a file format. | **Chosen** |
| `.ofz` | Open File Zip | None found. | Available. Clearest about ZIP, but harder to say. |
| `.ofc` | Open File Container | Open Financial Connectivity, read by Microsoft Money until about 2009 to 2011. | Fails the 20-year rule by about five years. |
| `.ofk` | Open File Kit | OpenFlowKit, an AI diagram tool launched in 2026, and SHARPpy weather data. | In active use. |

## Decision

**`.ofa`, Open File Archive.** "Archive" is the usual word for a ZIP-style
container, so the name tells people what kind of file it is before they open
it. "Open" carries the project's promise. The only earlier user is a photo
app that disappeared about 20 years ago.

The name gives every other identifier:

| Item | Value |
|---|---|
| Format name | Open File Archive (OFA) |
| Extension | `.ofa` |
| Media type | `application/vnd.ofa+zip` |
| Manifest entry | `ofa.json` |
| Manifest field holding the spec version | `"ofa"` |
| Reserved directory | `_ofa/` |
| macOS Uniform Type Identifier | `org.ofa-format.archive` (placeholder until the project has a domain), conforming to `public.zip-archive` and `public.data` |

"Artifact" also fits the letters and suits the project's story about files
made by AI-built tools. The README may use it that way, but the official name
stays "Open File Archive".

## Names we rejected

The search started from the working name Tote (`.tote`) and moved through
several rounds. The main reasons for dropping names:

- **Taken by an existing format:** `.off` (3D mesh), `.odf` (OpenDocument
  Formula and the OpenDocument Format standard), `.opf` (EPUB package
  files), `.oft` (Outlook templates), `.ocf`, `.ofp`, `.ofm`, `.ucf`,
  `.rof`, `.pkg`, `.upkg`, `.ubf`, `.ufp`, `.dof`.
- **Taken by an active project:** `.okf` (Google's Open Knowledge Format),
  `.ofk` (OpenFlowKit), `.oc`, `.oak`, `.odk`, `.uod`, `.ofe`, `.ofy`,
  `.ofi`, `.ofv`.
- **Failed the requirements:** `.tote` (four letters, and the maintainers
  did not like it), `.univ` and other "universal" names, `.stream`,
  `.parcel`, and all four-letter options.

## Aliases

- **`.ofa.zip`**: Writers MAY add `.zip` when a mail filter, upload form or
  operating system blocks unknown extensions. Readers MUST identify a package
  by its `mimetype` entry, so the extra suffix changes nothing.

## Media type registration

Comparable formats sit in both trees: `application/vnd.mcap` in the vendor
tree, `application/epub+zip` in the standards tree. We start in the vendor
tree because IANA expert review takes weeks, while a standards-tree
registration through a standards body takes years. The template:

```
Type name: application
Subtype name: vnd.ofa+zip
Required parameters: none
Optional parameters: version (the "ofa" manifest field, for example "0.1")
Encoding considerations: binary
Security considerations: see SPEC.md section 14
Interoperability considerations: see SPEC.md section 12
Published specification: SPEC.md in the project repository
Applications that use this media type: any program that reads or writes
  Open File Archive packages
Fragment identifier considerations: "#stream=<id>" selects one stream
  (SPEC.md section 6.3)
Magic number(s): "PK\x03\x04" at offset 0, the ASCII string "mimetype" at
  offset 30, and "application/vnd.ofa+zip" at offset 38
File extension(s): .ofa
Macintosh file type code(s): none
Person & email address to contact for further information: project maintainers
Intended usage: COMMON
Restrictions on usage: none
Change controller: the Open File Archive project maintainers
```

If the format moves to a standards body later, the project can register
`application/ofa+zip` in the standards tree and keep the vendor type as a
deprecated alias.

## Open questions

1. We have not yet run a trademark search for "Open File Archive" or "OFA"
   in software, or a broad web search for current `.ofa` use.
2. "OFA" is a common acronym, so web searches for it return unrelated
   results. Docs and listings should use the full name with the acronym.
3. Who holds change control for the IANA registration: an individual, a
   foundation, or a standards body?
4. Which domain should the project register, so the UTI and schema `$id`
   URIs point somewhere stable? The repo uses `ofa-format.org` as a
   placeholder.
