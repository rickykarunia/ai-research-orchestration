# Project Context Contract Template

This anchor is used by `scripts\new-vault.ps1` and the manual path. Copy the contents of this Markdown block
into `2. wiki/01 - Project Context.md` on a new vault if you're not using the automated scaffold.
This file is not a replacement for `AGENTS.md`: `AGENTS.md` governs the harness/routing, while this file
locks down the project's substantive context so the agent doesn't mix up framing across vaults.

Don't compress this file's content into `AGENTS.md`. When framing changes, update Project Context; when
harness rules change, update `AGENTS.md`.

---

```markdown
---
type: interpretasi
source-refs: []
confidence: Guessing
updated: <YYYY-MM-DD>
---

# 01 - Project Context

This context note must be read after the entry index and before substantive work. Update it when framing, scope, required sources, neighbor vault boundaries, or research decisions change.

## Project Purpose

**Project:** <project name>

**Objective:**  
<Main goal of the project, in 1-3 sentences.>

**Success means:**  
<The end result you're trying to reach.>

## Problem / Background

[NEEDS SOURCE] <The problem being raised and why it's worth a project/paper.>

## Research Or Policy Question

- [NEEDS USER DECISION] <Main question this project wants to answer.>
- [NEEDS USER DECISION] <Sub-question, if any.>

## Distinctive Angle

<What sets this project apart from similar vaults. Explain the contribution, angle, or mechanism that keeps it from being confused with another vault.>

## Scope

**In scope:**
- <...>
- <...>

**Out of scope:**
- <...>
- <...>

## Core Context

- <Facts/inferences about context the agent always needs to know. Mark it if not yet sourced.>
- [Certain] Flat routing by extension: `.pdf` to `corpus.py`/PageIndex, `.md` to `vcorpus.py`. No content judgment; no file in two indexes.
- [Certain] Confidential or unstructured PDFs are converted via `.\rag.ps1 convert`; the original PDF is parked in `1. raw/_source-pdf/`, outside both engines' sweep.
- [Certain] `ask-file`/`ask-essential` write automatically to `tmp/retrieval-packets/` and `2. wiki/_terra-drafts/`, append-only. Promotion to a wiki note uses `terra-context` (no API) or `promote-terra` for Kimi gap-fill; the script fills in front matter and note wiring.
- [Certain] Cross-document synthesis (`ask`, `synth`) writes no draft; cross-source claims are written by a human. A thematic note is written when an output needs it, not ahead of time.
- [Certain] Terra assembles the vector result for every `.md` in `1. raw/` EXCEPT those listed as confidential in `1. raw/_terra-tolak.txt` (deny-list). Confidential files: mechanical path with no API, `promote-terra` rejects them.

## Key Terms / Definitions

- `<term>` = <working definition>
- `<term>` = <working definition>

## Source Priority

Use sources in this priority order:

1. <primary source / regulation / core data>
2. <supporting literature or policy paper>
3. <internal notes / interviews / secondary source, if relevant>

## Assumptions

- [NEEDS VERIFICATION] <Initial assumption used until a source is available.>

## Decisions Already Made

- [NEEDS USER DECISION] <Substantive decision already made or that needs confirmation.>
- [Certain] Flat routing by extension: `.pdf` to `corpus.py`/PageIndex and `.md` to `vcorpus.py`; one file never enters both indexes.
- [Certain] Confidential or unstructured PDFs are converted via `.\rag.ps1 convert`; the original PDF is parked in `1. raw/_source-pdf/`.
- [Certain] Terra assembles any `.md` in `1. raw/` not listed in `1. raw/_terra-tolak.txt` (deny-list); listed confidential files exit through the mechanical path with no API.

## Open Questions

- [NEEDS SOURCE] <Question the current corpus can't answer yet.>

## Neighbor Vault Boundary

| Neighbor vault | Distinguishing boundary |
|---|---|
| `<vault>` | <When to switch to, or pull a depends-on from, that vault.> |

If a neighbor vault must always be opened alongside this project, also sync the
`depends-on` front-matter field in `AGENTS.md`, or run the scaffold with `-DependsOn`.

## Output Expectations

**Language:** <...>  
**Tone:** <...>  
**Default depth:** <...>

**Canonical source:** Markdown in `3. output/`.

**Derived formats:** <pick if needed: DOCX, PDF>. Export uses Pandoc with `3. output/refs.bib` and a preset from `3. output/csl/`. PDF needs a local PDF engine such as `xelatex`.

## Links

- [[00 - Index <Vault>]]
- [[_C2 Log]]

## Gap backlog

| Gap | Type | Next action |
|---|---|---|
| G-001 | NEEDS SOURCE | Add an initial primary source to `1. raw/` before writing a substantive claim as fact. |
```
