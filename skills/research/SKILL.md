---
name: research
description: "Research with verifiable grounding, primary sources to an auditable markdown finding. use_when: researching a topic, fact-checking, comparing sources, or before publishing any number, value or superlative (\"pesquisa isso\", \"de onde vem esse numero\"). do_not_use_when: the answer already lives in this repo."
---

# Research

Run the research in stations, in order. Do not skip ingestion or memory.

## The four non-negotiable rules

Apply to every research task, without exception and without waiting for the user to ask.

1. **Primary sources first.** Trust order: official documentation and the project repository, then the primary publication or paper, then third-party analysis, and last the aggregator blog, which only serves as a lead to confirm elsewhere. Never stop at an aggregator blog.
2. **Disagreement is reported, never silently resolved.** When two sources disagree, present both with the date of each and say which one is primary. Picking the convenient one without saying so is a serious failure.
3. **Weak samples are flagged.** A pattern observed in fewer than five cases goes in as "weak sample", never as a conclusion.
4. **Auditable output.** Every number, monetary value or superlative carries the URL and access date next to it. Without that, the data point does not leave the draft.

## Delegation

Stations 1 and 2, source discovery and ingestion, are collection work. Run them in a fast, cheap subagent. Stations 3 to 6, the protocol, the cross-checking, the disagreements and the trial by fire, are judgement and stay with the orchestrator.

The collecting subagent returns a list of sources with URL, access date and the local path of each converted file. It does not return conclusions, and it does not return paraphrased claims.

Rule 4 (auditable output) survives delegation only if the orchestrator opens the file. Every number, monetary value and superlative that enters the finding is read from the source by whoever writes the finding. A claim that exists only inside a subagent's report has no source, whatever the report says about having checked it.

## Station 1: sources

**Papers and scientific literature**: use the `paper-search` MCP to find material on arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex and Unpaywall. Always ask for the DOI along with the title, because the DOI survives a broken link.

**General web**: follow the stack's fallback order.
1. ScrapingDog (the `scrapingdog` skill) is the mandatory first attempt when `SCRAPINGDOG_API_KEY` exists in the environment. Pick its dedicated endpoint before generic `/scrape`.
2. Firecrawl (the `firecrawl-search` and `firecrawl-scrape` skills) is the fallback only when the key is absent or a bounded ScrapingDog attempt fails. Record that reason in the research trail before continuing.
3. Whatever web search the host gives you natively comes last, only when the two above do not solve it.

Never choose Firecrawl first merely because it is already authenticated or more
convenient. Never retry an invalid ScrapingDog credential indefinitely, expose
the credential, or hide the fallback from the audit file.

**Technology or product**: when the topic is technology rather than science, the primary source is the project's repository, official documentation and changelog. Star counts, version numbers and prices must be read on the project's own page, never in a third-party article that cites the project.

**Community pulse (last 30 days)**: when the question involves current sentiment, launch reception, the reputation of a person or company, or "what are people saying right now", run the `/last30days` plugin (Reddit, Hacker News, X, Polymarket, GitHub, arXiv, Techmeme, scored by real engagement). Two caveats: engagement measures relevance, not truth, so a factual claim found there still needs a primary source; and every data point that makes it into the report follows the four rules (URL + date next to it). Reddit, HN, Polymarket, GitHub and arXiv work without keys; X, YouTube and TikTok are opt-in with your own keys.

## Station 2: readable ingestion

Before reading any document, convert it. Delegate to the `ingest` skill, which routes each file type to the right converter.

Never analyze a two-column PDF without converting first. Scrambled reading order produces scrambled conclusions.

The ingest skill runs delegated. What comes back is file paths plus verification status, never the document's content.

## Station 3: protocol

Before investigating, write in the output file:

- the exact question, in one sentence
- the criterion that decides the answer, fixed now and not later
- what would falsify the hypothesis

## Station 4: investigation

Cross-check the converted sources. Record each claim with its source in the file while researching, not at the end. Reconstructing origins afterwards is where the trail gets lost.

## Station 5: memory

Save the finding as markdown in the current project's `research/` folder, or wherever the user asks. Standard structure:

- question and criterion, fixed before the investigation
- findings, each with source and date
- disagreements found, with both versions
- what remains open
- sources consulted, with URL and access date

Durable insight about the business, worth reusing in future research, goes into whatever persistent memory the host offers, not into the research file. The agent already knows when and how to record it there. On a host without a memory system, skip this and keep the insight in the finding.

## Station 6: trial by fire

When done, list explicitly for the user:

- which claims came from primary sources
- which ones rest only on secondary sources
- which numbers deserve reconfirmation because they are volatile, such as star counts, prices and job titles

For high-stakes decisions, suggest loading the same set of sources into a Gemini notebook via the `notebooklm` skill as a second read.

## Anti-patterns

- answering from memory without opening a source, even when the answer seems obvious
- citing a round number without a date
- presenting consensus when the sources diverge
- letting the finding die in the chat without becoming a file

---

Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, @nett0eth), MIT license.
