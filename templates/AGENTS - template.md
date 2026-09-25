# AGENTS.md template (new vault)
This anchor is used two ways: `scripts\new-vault.ps1` reads it directly during automatic scaffolding,
and a human can copy the Markdown block below for the manual path. Replace every `<...>`. Delete the
`#` comments if you like (the parser ignores both).

Rules required for `index_sync.py` to harvest this file:

- The file must be `AGENTS.md` or `CLAUDE.md`, at the **vault root**, under `~/Projects/`.
  (Outside `~/Projects/` it is NOT auto-harvested - move the vault, or register it manually in `dormant-registry.md`.)
- Front matter = the first block, `---` on line 0, containing the string `blok routing`.
- Lists are written as **one-line brackets**: `route-when: [a, b, c]`. Multi-line YAML format (`- a`) is not read.
- `vault` must be unique. `loop` is the string `true`/`false`. `tier` is `active`/`dormant`/`archive`.
- `depends-on` is only written when a secondary vault genuinely exists. On automatic scaffolding, use
  `-DependsOn a,b`; when empty, the `depends-on` line is removed so the placeholder never reaches the registry.
- Different harnesses read different files: **AGENTS.md** is read by Codex + Antigravity + the harvester; **CLAUDE.md** is read by Claude Code.
  Use AGENTS.md as the multi-harness canonical file. If you need a CLAUDE.md too, keep it thin and point it at "Read AGENTS.md" (don't duplicate the rules).

Once filled in, run the checklist at the end.

---

<!-- ================= COPY STARTS HERE ================= -->

```markdown
---
# === routing block (blok routing) - harvested by /index-sync into ~/AI-INDEX.md. Do not remove. ===
# Lists MUST be one-line brackets: [a, b, c]. Not multi-line YAML.
vault: <unique-kebab-vault-name>
path: Projects/<vault-name>
domain: <one sentence: what this vault is for>
route-when: [<trigger 1>, <trigger 2>, <trigger 3>]      # <=5 phrases; task matches -> router lands here
not-when: [<exclusion 1>, <exclusion 2>]                  # <=4; rejects a match even if route-when hits
depends-on: [<secondary vault>]                        # optional; other vaults that must be opened for cross-domain tasks. remove the line if none
entry: "2. wiki/00 - Index <Vault>.md"                # the vault's opening file
tier: active
loop: true                                            # true if this vault uses raw -> wiki -> output
rules: [AGENTS.md]
skills: [<relevant skill>, obsidian-cli, humanizer, loop-engine] # obsidian-cli for 2. wiki; loop-engine only if loop: true.
---

> **Orchestration:** cross-project behavior lives in `~/AI-RULES.md`; cross-vault routing in `~/AI-INDEX.md`. Precedence: session instructions > this file > AI-RULES. This project's file wins on conflict.

# AGENTS.md - <Project Name>

<1-2 sentences: this vault's role in the system, and when the router should send tasks here.>

Before substantive work, read `entry`, then `2. wiki/01 - Project Context.md`. That context note is the project's distinguishing contract: problem, research/policy question, scope, assumptions, required sources, and the boundary with neighboring vaults. Don't compress the context note's content into AGENTS.md; AGENTS.md is the control plane, Project Context is the context plane.

## 1. Role in the loop

| Stage | Contents |
|---|---|
| `1. raw/` | Source evidence (PDFs, dumps, raw data). Don't edit/overwrite/rename/delete without permission. |
| `<.pageindex/ or .vector/ or graphify-out/>` | Derived index (auto-built). Can be rebuilt. Not canonical evidence. |
| `2. wiki/` | Sourced synthesis + return-leg (gaps, decisions, new questions). The thinking space. `01 - Project Context.md` holds the problem context and what makes this project distinct. |
| `3. output/` | Finished deliverables. One canonical deliverable per need. Assembled from wiki, not from raw or memory. |
| `.loop/` | Loop-phase artifacts (`plan.md`, `critique.md`, `verify.md`, `state.json`, `run.lock`). Derived, safe to delete. Deliberately outside `2. wiki` so it doesn't trigger `loop_check.py` provenance findings. |

## 2. How the harness uses this vault

<This vault's main retrieval/work commands. Answers to the user come from retrieval, not memory. Example:>

~~~powershell
cd "<vault-dir>"

.\rag.ps1 check                 # are both engines healthy?
.\rag.ps1 convert "x.pdf"       # Marker: PDF -> .md, original PDF parked under _source-pdf\
.\rag.ps1 ingest                # vcorpus: every .md in "1. raw"
.\rag.ps1 ingest -Page          # corpus/PageIndex: every PDF in "1. raw"
.\rag.ps1 ask "question"        # CROSS-document; prints only, writes no draft
.\rag.ps1 ask-file "x" "q"      # ONE file -> transit + wiki draft (append). -Page for PDF
.\rag.ps1 review-draft "x"      # flag candidate contradictions across draft entries
.\rag.ps1 synth                 # cross-document batch: tmp\ask-batch\*.md -> tmp\retrieval-packets\
.\rag.ps1 promote-terra "slug"  # LLM lane: verify + write note + gate
.\rag.ps1 terra-context "slug"  # mechanical lane: draft_to_note + gate, no Kimi
.\rag.ps1 terra-gate "slug" --note "title.md"  # lint a manual note
.\rag.ps1 status                # vault counts + loop_check
~~~

`rag.ps1` is the single entry point for retrieval. It resolves the Python paths internally, so don't hardcode a long launcher path and don't rely on `py` being on PATH. The raw engines (`corpus.py`, `vcorpus.py`) are called directly only when `rag.ps1` isn't enough.

## Citation and export

This contract applies to every vault type. `-Type` selects the domain skill and workflow, not the citation style.

### Citation contract

- Default: APA 7 via `3. output/csl/apa.csl`.
- Parenthetical: `[@citekey]` renders as `(Author, Year)` in APA.
- Narrative: `@citekey` renders as `Author (Year)` in APA.
- The citekey must match the BibTeX bibliography key exactly.
- The bibliography file lives at `3. output/refs.bib`; the generator does not create it.
- `source-refs` remains the internal audit trail. Formal citations don't replace it.

### Markdown -> Word/PDF

Run from the vault root once `3. output/refs.bib` exists:

```powershell
pandoc input.md -o output-apa.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/apa.csl"
pandoc input.md -o output-apa.pdf --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/apa.csl"
pandoc input.md -o output-ieee.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/ieee.csl"
pandoc input.md -o output-ieee.pdf --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/ieee.csl"
pandoc input.md -o output-chicago.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/chicago-author-date.csl"
pandoc input.md -o output-chicago.pdf --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/chicago-author-date.csl"
pandoc input.md -o output-chicago-notes.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/chicago-notes-bibliography.csl"
pandoc input.md -o output-chicago-notes.pdf --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/chicago-notes-bibliography.csl"
```

PDF export needs a local PDF engine, e.g. `xelatex`. Check before exporting:

```powershell
pandoc --version
Get-Command xelatex -ErrorAction SilentlyContinue
```

If `xelatex` isn't found, install a LaTeX engine or use DOCX output instead. Don't claim a PDF succeeded before the PDF file actually exists.

Changing `--csl` changes the output style without touching the Markdown citekeys. If a citation renders as `?`, compare the Markdown citekey against the BibTeX key and check the file name:

```powershell
Get-ChildItem "3. output\csl" -Filter "*.csl"
```

Steps:
1. Read `entry` and `2. wiki/01 - Project Context.md` to lock down the problem, scope, assumptions, and boundaries with other vaults.
2. Make sure the derived layers are current (ingest/index first if new files landed in `1. raw/`).
3. Synthesize per document via `ask-file`/`ask-essential`; results land automatically in transit + draft.
   For bulk work, `ask-essential --new` only processes files that don't have a draft yet, so sources
   added to `1. raw/` later can be caught up without re-running the whole corpus. Both engines apply:
   `.pdf` with `-Page` (the Q1-Q8 set), `.md` without `-Page` (the 10-query set, `vcorpus-essential-v1`).
3b. (optional, for drafts with 2+ entries) `.\rag.ps1 review-draft "name"` - Terra flags
    candidate contradictions between entries directly in the draft. A reading pointer, not a
    substitute for manual reading before promotion.
4. Promoting a draft to `2. wiki/`: you run `ingest` + `ask-essential --new` (which builds the draft). Then either **mechanical lane** `.\rag.ps1 terra-context "<slug>"` (or `--all`), which carries the draft into a clean note with no Kimi call, filling in front matter, the index, the C2 Log, and status, then runs the gate automatically; or **gap-fill lane** `.\rag.ps1 promote-terra "<slug>"` (or `--all`), which uses two-stage `kimi-k3` only for genuine `## Gap backlog` items, retrieving only from `source-refs`; a gap with no supporting passage is logged as a return-leg in `01 - Project Context.md` and `_C2 Log.md`. Set `MOONSHOT_API_KEY` before using the gap-fill lane. `terra-context` cleans up formatting, it does not verify substance.
5. Not in the sources = `[NEEDS SOURCE]`. Don't make it up.
6. Return-leg: write new gaps/decisions/questions to `2. wiki/`, not just to chat.

Minimum operator contract:
1. `.\rag.ps1 ingest` for new sources under `1. raw/`.
2. `.\rag.ps1 list` to confirm sources made it into the index.
3. `.\rag.ps1 ask-file "name" "..."` for a question locked to one source; results land automatically in transit + draft.
4. `.\rag.ps1 ask "..."` or `.\rag.ps1 synth` for CROSS-document questions; batch question files live in `tmp\ask-batch\*.md`. This wrapper calls `ask-batch.ps1` in the control plane; there is no second batch engine in the vault. Cross-document results don't get an automatic draft.
5. Promote drafts in `2. wiki/_terra-drafts/` to a note in `2. wiki` with `source-refs`: mechanical lane `terra-context` or gap-fill lane `promote-terra`. Transit files in `tmp\retrieval-packets/` and drafts are both raw evidence, not the final wiki.
6. `sync-wiki` is only an index inventory, not proof that synthesis is done.
7. For a `loop: true` vault, Claude runs `/loop-engine <name>` by default. On the explicit command
   `Codex, assemble output for <slug>`, Codex may take over the entire PLAN -> ACT -> REVIEW ->
   VERIFY -> FINISH sequence and write the canonical output directly to `3. output/`. Resume, lock, the
   return leg, independent REVIEW, VERIFY, and the three-iteration cap still apply.

Not sure where to start: run `.\rag.ps1 status`, then take the top line of **Gap backlog** in `2. wiki/01 - Project Context.md`. The gap backlog is this vault's only work queue; don't open a parallel queue in chat.

## 3. Choosing a retrieval path

| Need | Path |
|---|---|
| `*.pdf` in `1. raw/` | `corpus.py`/PageIndex (`-Page`). Always, no content judgment. |
| `*.md` in `1. raw/` | `vcorpus.py`/local vector. Always, including `rag.ps1 convert` output. |
| Confidential or unstructured PDF | `.\rag.ps1 convert "x.pdf"` first; the original PDF is parked in `1. raw/_source-pdf/`, the resulting `.md` goes to vector. |
| Wiki Markdown, cross-file relations | Obsidian search + backlinks + `[[wikilink]]` |
| Very large Markdown/code vault | graphify, opt-in |
| Statutory or regulatory basis | the relevant domain vault, not model memory |

### 3A. Synthesis: what's automatic, what isn't

1. `1. raw/` is canonical evidence. `.pageindex/`, `.vector/`, the transit log, and model drafts are just discovery tools.
2. **Per-document (automatic).** `ask-file` and `ask-essential` are locked to ONE source, so
   their results are written automatically to two places at once, both append-only:
   `tmp/retrieval-packets/<slug>.md` (raw Q&A log) and
   `2. wiki/_terra-drafts/<slug> (terra-draft).md` (formatted draft).
3. **Append-only, never overwritten.** Asking the same file again adds a dated section.
   Manual corrections on the draft survive. The consequence is that old sections can go stale
   with no marker, so before promotion read the WHOLE draft, not just the newest section.
   `.\rag.ps1 review-draft "name"` flags candidate contradictions, but that's an aid, not verification.
4. **Promotion is operator-controlled.** A draft becomes a `2. wiki/` note via the mechanical lane
   `terra-context` or the gap-fill lane `promote-terra`. The mechanical lane does not verify substance;
   use the gap-fill lane or a separate source review for material gaps. A draft is still not a note
   until one of the lanes writes it.
5. **Cross-document (not automatic).** `ask` and `.\rag.ps1 synth` answer questions that
   span multiple sources. Their results are deliberately not turned into drafts: cross-source
   claims are prone to misattribution, so a human builds that argument.
6. **Thematic synthesis is written when an output needs it, not ahead of time.** `2. wiki/` is a
   knowledge base for grounding, not a stockpile of finished conclusions. When assembling an output
   (a project outline, an interview question list, a final draft), cross-document reasoning
   happens then, from the per-document notes. A permanent thematic note is only written when
   its conclusion gets reused across many outputs.
7. Vector scores are an internal gate, not a comparison between methods: `strong` is a candidate,
   `weak` needs corroboration, `none` means `[NEEDS SOURCE]`.
8. If results conflict, check back against the file in `1. raw/`. Whatever can't be verified stays `[NEEDS SOURCE]`.

`ask-file` and `ask-essential` are the per-document synthesis path for both engines, sharing the same command names. `draft-wiki` is a deprecated alias for `ask-essential`. `promote-packet` exists only in `codex-review-harness/corpus.py`, not in this vault.

On the vector path, Terra assembles every `.md` in `1. raw/` EXCEPT those listed as confidential
in `1. raw/_terra-tolak.txt` (deny-list). As long as an `.md` file is in `1. raw/` and not on that
list, it's synthesized straight into a terra-draft and then verified by `kimi-k3` into the wiki. Confidential
files can still be queried, but the result is a verbatim passage plus `[NEEDS SOURCE]` with no API call, and
`promote-terra` rejects them (use the mechanical lane `terra-context`, which also never sends `.md` to an API). Backward compat:
if `_terra-tolak.txt` doesn't exist but `_terra-boleh.txt` does, the old allow-list behavior applies.

## 4. Delta rules (specific to this vault)

- Anti-fabrication, confidence tags, gap markers, file/PDF read limits, done-means-verified: **follow `~/AI-RULES.md`. Don't duplicate it here.**
- `2. wiki/01 - Project Context.md` is the working source for background, problem, research/policy question, scope, assumptions, required sources, output expectations, and the boundary with neighboring vaults. Update that note when the framing changes; don't keep detailed context only in chat, and don't duplicate it into AGENTS.md.
- <Add rules that ONLY apply to this vault. A delta adds to the AI-RULES floor, it never lowers it.>
- <Confidentiality boundary if relevant (e.g. internal documents: local embeddings only, no API).>
- Claude-Codex C2: defaults to AI-RULES (for non-loop work). The five-phase loop defaults to Claude, with
  a Codex fallback only on the explicit command `Codex, assemble output for <slug>`. The fallback uses
  the same checkpoint/resume, lock, canonical output, independent REVIEW, VERIFY, and three-iteration
  cap.
- Promoting `_terra-drafts/` -> `2. wiki/` goes through `terra-context` (mechanical, no API) or `promote-terra` (LLM `kimi-k3`, two-stage when a real gap exists). There is no autonomous agent lane. Basis: `AI-RULES.md` sec. 8.

## 5. Default skills

The harness should prefer the skills in the `skills` field for matching tasks, without a manual invoke every session (this file auto-loads per folder). It's a preference nudge, not a mandate; a skill still activates on its own when a task hits its trigger.

Defaults that apply across every type:

| Skill | When |
|---|---|
| `obsidian-cli` | Navigating `2. wiki` via search, backlinks, tags, and `[[wikilink]]`. Falls back to `rg` if the CLI isn't available. |
| `loop-engine` | Assembling `2. wiki` into a `3. output` deliverable in a `loop: true` vault. Claude by default; Codex can run all five phases after an explicit command and resume from a valid checkpoint. |
| `humanizer` | Prose floor for every deliverable. Domain-agnostic. |

The rest, per type:

> <e.g. paper: research/write -> academic-paper (+ deep-research). Review -> academic-paper-reviewer. app: brainstorm first, then TDD; bugs -> systematic-debugging; hold off on gstack until deploy.>

## Changelog

- <YYYY-MM-DD>: Vault created. <summarize contents + engine + registered in AI-INDEX via /index-sync.>
```

<!-- ================= COPY ENDS HERE ================= -->

---

## Checklist after creating AGENTS.md

`<kit-root>` below = your ai-research-orchestration clone (the folder containing `scripts\` and
`templates\`). `new-vault.ps1` does these steps for you; the checklist is for the manual path.

```powershell
# 1. Create the loop structure (if loop: true)
$v = "<vault-dir>"
New-Item -ItemType Directory -Force "$v\1. raw","$v\2. wiki","$v\3. output" | Out-Null

# 2. (If the vault needs PDF retrieval) copy the engine + wrapper to the vault root, edit the CONFIG block.
#    new-vault.ps1's automated path already copies: corpus.py, vcorpus.py, rag.ps1,
#    manifest.json, README.md, .loop/, and tmp\ask-batch\00-example-packet.md.
#    corpus.py = structured PDF (needs OPENAI_API_KEY); vcorpus.py = internal/local + every .md in 1. raw.
#    See templates/retrieval-per-vault/README.md. Drop PDFs in "$v\1. raw", then ingest.
#      copy "...\templates\retrieval-per-vault\vcorpus.py" "$v\vcorpus.py"

# 3. Create the required context note for what distinguishes this project:
#
#      2. wiki\01 - Project Context.md
#
#    Copy from `templates\Project Context - template.md`.
#    Minimum contents: problem, research/policy question, distinctive angle, scope,
#    required sources, neighbor vault boundary, and gap backlog.

# 4. Create the entry file pointed to by the `entry` front-matter field
#    (e.g. "2. wiki\00 - Index <Vault>.md") with at least 1 [[wikilink]].
#    Must link to [[01 - Project Context]].
#    MUST have `source-refs:` front matter - loop_check.py flags any "2. wiki" note
#    missing that field. The index note hasn't cited any raw source yet, so write an empty list:
#
#      ---
#      type: index
#      source-refs: []
#      confidence: Certain
#      updated: <YYYY-MM-DD>
#      ---

# 5. Create the Obsidian config at the vault root, not inside `2. wiki`, so raw/wiki/output stay one graph.
#
#      .obsidian\app.json
#      .obsidian\appearance.json
#      .obsidian\core-plugins.json
#      .obsidian\workspace.json
#
#    On the automated path, new-vault.ps1 already creates this folder and these files.

# 6. Create the C2 log linked from the entry and Project Context.
#    Copy from `templates\C2 Log - template.md` to:
#
#      2. wiki\_C2 Log.md
#
#    On the automated path, new-vault.ps1 already creates this file.

# 7. Register with the registry (regenerate AI-INDEX.md)
py -3.13 "<kit-root>\scripts\index_sync.py"

# 8. Validate the loop
py -3.13 "<kit-root>\scripts\loop_check.py" --vault <vault-name>
```

Confirm the vault appears under the **active** section of `AI-INDEX.md` after step 3. If it doesn't:
`route-when`/`not-when` isn't a one-line bracket, or the front matter is missing `blok routing`, or the vault is outside `~/Projects/`.
