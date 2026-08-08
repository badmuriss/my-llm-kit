---
name: ingest
description: "Converts PDF, Office, EPUB, image, audio or repo into structured markdown before analysis. use_when: a document is uploaded or referenced, or before summarizing, quoting or analyzing one (\"converte esse PDF\", \"le essa planilha\"). do_not_use_when: the text is already markdown in the repo."
---

# Ingestao (ingestion)

Convert before reading. Material that comes in destroyed produces destroyed conclusions, and the model does not warn you when that happens.

## Routing by type

| Situation | Tool | Command |
|---|---|---|
| office and pdf documents: PDF, Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV | anydoc | `npx -y @firecrawl/anydoc input.pdf -o output.md` |
| image or audio | markitdown | `markitdown input.png > output.md` |
| scientific PDF, two columns, scanned, with formulas or complex tables that anydoc scrambled | MinerU (optional, install only when needed) | see the project's README |
| entire code repository | repomix | `npx repomix` |

anydoc is the first choice for office and pdf formats. It is pure Rust, runs locally, needs no API key, and is roughly a hundred times faster than markitdown on PDF. On a measured 453 KB PDF, anydoc emitted 23 headings and 13 table rows, while markitdown emitted zero markdown headings and zero table rows, flattening both into running text. anydoc does not handle images or audio, so markitdown stays for those, since it does OCR and transcription. anydoc is young and releases often, so set npm's `min-release-age` rather than chasing the newest build. A converter that silently changes its output between runs is how a bad conversion reaches a conclusion unnoticed. Neither tool fixes reading order on a hard two-column PDF. That is still what MinerU is for.

## Procedure

1. Identify the type and pick the tool from the table
2. Convert into a `./fontes-md` folder, keeping the original file name
3. Open the output and check four things before moving on: the headings survived, the tables are still tables, the reading order makes sense, and the footnotes did not invade the body
4. If any of these fail, switch converters before analyzing

## Delegation

Conversion is mechanical, so run it in a fast, cheap subagent rather than in the main context. A converted document can be hundreds of pages, and loading it into the orchestrator's context is the real cost of ingestion, not the converter.

The subagent returns only: the path of each generated file, which converter it used, and the result of the four verification checks. It never returns the document's content, and it never returns a summary, a paraphrase, or a quoted passage.

Any number, monetary value, quote or citation that reaches the final answer is read by the orchestrator from the generated file, never taken from the subagent's report. A cheap model reporting "verified" is not evidence that it verified anything, and a fabricated figure that passes through a summary is indistinguishable from a real one downstream.

## Mandatory verification

Never declare ingestion done without opening the generated markdown. A silently wrong conversion is the most common cause of wrong analysis, and it is invisible if you trust the process without looking.

If the conversion failed and switching converters did not fix it, report the problem to the user instead of analyzing broken text.

When reporting to the user, say which converter was used and what was verified.

---

Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, @nett0eth), MIT license.
