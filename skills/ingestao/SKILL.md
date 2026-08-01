---
name: ingestao
description: Converts documents into structured markdown before any analysis, routing each file type to the right converter. Use when the user uploads or points to a PDF, Word, Excel, PowerPoint, EPUB, image, audio file or code repository, when a scientific PDF needs formulas, tables and reading order preserved, or with Portuguese phrasings like "converte esse PDF", "lê essa planilha", "ingere esse documento". Also use before summarizing, analyzing or quoting any document.
---

# Ingestao (ingestion)

Convert before reading. Material that comes in destroyed produces destroyed conclusions, and the model does not warn you when that happens.

## Routing by type

| Situation | Tool | Command |
|---|---|---|
| common document: simple PDF, Word, Excel, PowerPoint, EPUB, image, audio | markitdown | `markitdown input.pdf > output.md` |
| scientific PDF, two columns, scanned, with formulas or complex tables that markitdown scrambled | MinerU (optional, install only when needed) | see the project's README |
| entire code repository | repomix | `npx repomix` |

Two-line decision rule: start with markitdown, which handles most cases and is already installed. If the output comes back with scrambled reading order, lost formulas or tables flattened into running text, the problem is layout and the answer is MinerU, a heavy dependency that is not installed by default.

## Procedure

1. Identify the type and pick the tool from the table
2. Convert into a `./fontes-md` folder, keeping the original file name
3. Open the output and check four things before moving on: the headings survived, the tables are still tables, the reading order makes sense, and the footnotes did not invade the body
4. If any of these fail, switch converters before analyzing

## Mandatory verification

Never declare ingestion done without opening the generated markdown. A silently wrong conversion is the most common cause of wrong analysis, and it is invisible if you trust the process without looking.

If the conversion failed and switching converters did not fix it, report the problem to the user instead of analyzing broken text.

When reporting to the user, say which converter was used and what was verified.

---

Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, @nett0eth), MIT license.
