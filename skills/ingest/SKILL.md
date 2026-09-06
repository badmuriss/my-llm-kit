---
name: ingest
description: Extract content from documents when their format or layout prevents reliable direct reading. Verify reading order and tables before analysis.
---

# Ingest

Use direct reading for text, Markdown, CSV that preserves its structure, and
known source-code files. Do not convert or bundle a repository merely to inspect
one file. For editing a document, use its format-specific skill when available.

For PDF or Office extraction, prefer an available local converter such as
`anydoc`. For image or audio input, use a tool with the required OCR or
transcription capability; do not assume every installation has those extras.
Use a layout-aware converter for complex or scanned PDFs when ordinary extraction
scrambles the content. Install extra converters only when the task needs them.

Preserve the original. Write extracted content to a task-local directory and
verify headings, table structure, reading order and footnotes before citing it.
If extraction fails, try a suitable alternative or report which content could
not be read reliably. Never summarize scrambled extraction as established fact.

A conversion batch may be delegated when useful. A returned path or successful
process exit does not replace inspecting the output. Avoid loading an entire
long document when targeted passages are enough.

Adapted from [research-stack](https://github.com/nett0eth/research-stack), MIT.
