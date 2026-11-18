# Contributing

Thanks for helping. OFA succeeds only if many people can implement it, so
outside reviews matter as much as code.

The draft is open for public comment. You don't need to write code or an RFC
to take part. A question or an opinion in
[Discussions](https://github.com/phennessey/open-file/discussions) helps.

## Ways to help

- **Read the spec and file issues.** Ambiguities count as bugs. If two
  careful readers could implement a sentence differently, open an issue.
- **Write a reader or writer** in another language and report what was hard.
- **Try it on real data.** Package something you work with and tell us what
  the manifest could not express.
- **Propose a change** through an RFC (below).

## Small changes

Typos, broken links, clearer wording that does not change meaning, and fixes
to `tools/` go straight to a pull request.

## Normative changes: the RFC process

Anything that changes what a reader or writer must do needs an RFC. That
includes new manifest members, new registry entries (roles, schema types,
content codings, well-known media types) and changes to conformance levels.

1. Copy [`rfcs/0000-template.md`](rfcs/0000-template.md) to
   `rfcs/0000-short-name.md`.
2. Fill it in. Keep it short. Show a manifest example.
3. Open a pull request. A maintainer assigns the next number.
4. Discussion runs for at least 14 days.
5. Maintainers accept, reject or postpone, and record the reason in the RFC.
6. An accepted RFC lands in `SPEC.md` in a separate pull request that links
   to it.

Registry additions can use a short RFC: the name, a link to the external
specification, and one example.

## What we look for in proposals

- **Reuse first.** If an existing standard or registry covers it, point at
  that standard instead of defining something new.
- **Listing must keep working.** No change may stop an Inspect-level reader
  from listing and extracting a package.
- **Declarative over executable.**
- **Implementation evidence.** Proposals with a working prototype in
  `tools/` or elsewhere move faster.

## Style for spec text

- Use BCP 14 keywords (MUST, SHOULD, MAY) only for requirements, and name
  who must act: "Readers MUST", "Writers SHOULD".
- One requirement per sentence where possible.
- Every new requirement needs a test case once the conformance suite exists.

## Code

- `tools/ofa.py` uses the Python standard library only. Keep it that way so
  anyone can run it.
- Run the examples before submitting:

  ```bash
  for f in examples/*.ofa; do python3 tools/ofa.py verify "$f"; done
  ```

## Licensing of contributions

By contributing you agree to license specification text under CC BY 4.0 and
code under Apache 2.0, matching the files you change.

## Conduct

All participants follow the [Code of Conduct](CODE_OF_CONDUCT.md).
