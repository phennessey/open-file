# Name candidates

Status: decided on 18 November 2026. The format is Open File Archive
(`.ofa`). See [RFC 0001](../rfcs/0001-extension-and-media-type.md). This file
records the last round of the search.

Current scope: 3-letter extensions starting with `.of`. The 4-letter options
have been dropped.

"Available" means no software has used the extension in the last 20 years
(since about 2006).

Sources checked on 17 and 18 November 2026: fileinfo.com,
file-extensions.org, filext.com and GitHub code search. None of these has had
a web or trademark check yet.

## Candidates

| Extension | Full name | Earlier uses | Verdict |
|---|---|---|---|
| `.ofz` | Open File Zip | None found. | Available. |
| `.ofa` | Open File Archive | Kodak OfotoNow data files. Ofoto became Kodak EasyShare Gallery in 2005 and the OfotoNow app went with it. 5 minor GitHub repos, none of them a format. | Available. |
| `.ofc` | Open File Container | Open Financial Connectivity, Microsoft's bank-statement format for Microsoft Money. OFX replaced it from 1997, but Money kept reading `.ofc` until Microsoft dropped Money in 2009 to 2011. A few GitHub repos still handle it, for example a personal-finance tool. | Borderline. Last real use was about 15 years ago, not 20. "ofc" is also common internet slang for "of course". |

## Ruled out

- `.ofk`: OpenFlowKit, an AI diagram tool launched in 2026, uses it. The
  SHARPpy weather tool also uses it for sounding data.
- `.odf`: OpenDocument Formula, and "ODF" is the OpenDocument Format standard.
- `.okf`: Google's Open Knowledge Format.
- `.off`, `.opf`, `.oft`, `.ocf`, `.ofm`, `.oc`: existing formats or active
  projects.

## Before choosing

1. Run a web search for "<ext> file" and the full name.
2. Check trademarks for the name in software and file formats.
3. Check that no operating system already associates the extension with an
   app.
