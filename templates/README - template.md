<!-- Vault README template. new-vault.ps1 uses it whole (not a fenced block):
     tokens __TITLE__, __VAULT__, __VAULTDIR__, __DOMAIN__, __ENTRY__ are replaced during scaffolding.
     This comment line is stripped by the scaffold too. -->
# __TITLE__
__DOMAIN__

## Starting from zero

Before following the workflow, install these tools once on your machine:

1. [Zotero](https://www.zotero.org/download/).
2. Better BibTeX for Zotero, from its [official install guide](https://retorque.re/zotero-better-bibtex/installation/). Make sure Zotero is open and Better BibTeX is enabled under `Tools > Plugins`.
3. [Pandoc](https://pandoc.org/installing.html). Close and reopen PowerShell, then check `pandoc --version`.

In Zotero, export or copy the bibliography with Better BibTeX and save it as `3. output/refs.bib`. The scaffold already ships CSL presets in `3. output/csl/`; `refs.bib` still has to be created by the operator.

## Anchor

- Canonical agent rules: `AGENTS.md`
- Claude pointer: `CLAUDE.md`
- Wiki entry: `__ENTRY__`
- Research context: `2. wiki/01 - Project Context.md`
- Claude-Codex handoff: `2. wiki/_C2 Log.md`
- Loop executor: Claude by default; Codex fallback via the explicit command `Codex, assemble output for <slug>`

## Workflow

1. Put source evidence in `1. raw/`. Confidential or unstructured PDF: `.\rag.ps1 convert "name.pdf"` first.
2. Ingest: `.\rag.ps1 ingest` for `.md`, `.\rag.ps1 ingest -Page` for PDF.
3. Per-document synthesis: `.\rag.ps1 ask-file "name" "question"` (add `-Page` for PDF),
   or `.\rag.ps1 ask-essential "name.pdf" -Page` for Q1-Q8, or `.\rag.ps1 ask-essential "name.md"`
   for the vector path's essential set. Results land in transit + draft automatically. In bulk, add
   `--new` to process only files that don't have a draft yet.
4. (optional, for drafts with 2+ entries) `.\rag.ps1 review-draft "name"` flags candidate contradictions
   between entries. A reading pointer, not a substitute for manual reading.
5. Promote a draft to `2. wiki/`: `.\rag.ps1 terra-context "<slug>"` carries it over and cleans it up
   without Kimi; `.\rag.ps1 promote-terra "<slug>"` uses Kimi only for genuine gaps.
6. Cross-document questions: `.\rag.ps1 ask "..."` or `.\rag.ps1 synth`. Results are raw evidence;
   the claim itself is written by a human.
7. Assemble the deliverable in `3. output/` from wiki notes. Claude: `/loop-engine <name>`. Codex fallback:
   `Codex, assemble output for <slug>`. Codex resumes from the last valid phase and writes to the
   same canonical file, once the checkpoint and lock check pass.
8. Log gaps, decisions, and handoffs in `2. wiki/01 - Project Context.md` or `_C2 Log.md`.

## Citation and export

This section is included for every vault type. Markdown uses `[@citekey]` for parenthetical citations and `@citekey` for narrative citations. The default is APA 7. Save the bibliography you export from Zotero as `3. output/refs.bib`; the scaffold does not create this file automatically.

Export to Word or PDF from the vault root with `pandoc`, always including `--citeproc`, `--bibliography`, and `--csl` (PDF also needs a LaTeX engine such as `pdflatex`):

```powershell
pandoc input.md -o output.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/apa.csl"
pandoc input.md -o "3. output/output.pdf" --pdf-engine=pdflatex --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/apa.csl"
```

Swap in `ieee.csl`, `chicago-author-date.csl`, or `chicago-notes-bibliography.csl` for `--csl` to use a different style. If a citekey isn't found, check that the Markdown key matches the key in `refs.bib`.

## Commands

Everything goes through `rag.ps1`. It resolves the Python paths internally, so you don't need to
hardcode a long launcher path, and it doesn't depend on `py` being on PATH.

```powershell
Set-Location -LiteralPath "__VAULTDIR__"

.\rag.ps1 check                 # are both engines healthy?
.\rag.ps1 convert "x.pdf"       # Marker: PDF -> .md in "1. raw", original PDF parked
.\rag.ps1 ingest                # vcorpus: every .md in "1. raw"
.\rag.ps1 ingest -Page          # corpus/PageIndex: every PDF in "1. raw"
.\rag.ps1 list                  # contents of the vector index
.\rag.ps1 list -Page            # contents of the PageIndex index
.\rag.ps1 ask "question"        # CROSS-document, vector index; prints only
.\rag.ps1 ask "question" -Page
.\rag.ps1 ask-file "x.md" "q"   # ONE file -> transit + wiki draft (append)
.\rag.ps1 ask-file "x.pdf" "q" -Page
.\rag.ps1 ask-essential "x.md"  # essential set of 10 queries, one .md file
.\rag.ps1 ask-essential --new   # only files without a draft yet (both engines)
.\rag.ps1 ask-essential --all   # every indexed file
.\rag.ps1 review-draft "x.md"   # flag candidate contradictions across draft entries
.\rag.ps1 synth                 # cross-document batch: tmp\ask-batch\*.md -> tmp\retrieval-packets\
.\rag.ps1 status                # vault counts + loop_check
```

For the Codex fallback, the chat command that authorizes the takeover is:

```text
Codex, assemble output for <slug>
```

That command does not auto-detect a Claude limit. Codex checks
`.loop\<slug>\state.json`, the phase artifacts, and `.loop\<slug>\run.lock`, then runs only the
next valid phase. `ACT` reads the wiki notes per `plan.md`, `REVIEW` stays independent,
`VERIFY` still runs `loop_check.py`, and output still goes straight to `3. output/`.

### What `rag.ps1` is

`rag.ps1` isn't a third engine. It's a thin wrapper over `corpus.py` (PageIndex) and `vcorpus.py`
(vector), which stay at this vault's root, unchanged. All it does is resolve the Python launcher path
and call one of the two with the right arguments. Without the raw engines, `rag.ps1`
does nothing.

By default `rag.ps1 <command>` calls `vcorpus.py`. Add `-Page` to call `corpus.py` instead.

| Short command | Long command it replaces |
|---|---|
| `.\rag.ps1 check` | `vcorpus.py check` + `corpus.py check` |
| `.\rag.ps1 ingest` | `py -3.13 .\vcorpus.py ingest` |
| `.\rag.ps1 ingest -Page` | `py -3.13 .\corpus.py ingest` |
| `.\rag.ps1 ask "..."` | `py -3.13 .\vcorpus.py ask "..."` |
| `.\rag.ps1 ask "..." -Page` | `py -3.13 .\corpus.py ask "..."` |
| `.\rag.ps1 ask-file "x" "q"` | `py -3.13 .\vcorpus.py ask-file "x" "q"` |
| `.\rag.ps1 convert "x.pdf"` | `pdf2md.ps1` + promote the `.md` + park the PDF under `1. raw\_source-pdf\` |
| `.\rag.ps1 review-draft "x"` | `py -3.13 scripts\review-draft.py <vault> "x"` (control plane) |
| `.\rag.ps1 synth` | calls `ask-batch.ps1` (control plane) with `-Vault` set to this vault |
| `.\rag.ps1 status` | counts `1. raw`/`2. wiki`/`3. output` + calls `loop_check.py` |

`rag.ps1` builds no new index. `.pageindex\` and `.vector\` are still created by `corpus.py`/`vcorpus.py`
as usual; `rag.ps1` just removes the need to hardcode a long launcher path for every command.

## Retrieval: flat rules

File extension decides, not a judgment call on content.

| File in `1. raw/` | Engine | Command |
|---|---|---|
| `*.pdf` | `corpus.py` / PageIndex | `.\rag.ps1 ingest -Page`, `.\rag.ps1 ask-file "x.pdf" "..." -Page` |
| `*.md` | `vcorpus.py` / local vector | `.\rag.ps1 ingest`, `.\rag.ps1 ask-file "x.md" "..."` |

No file enters both indexes: `vcorpus` only sweeps `.md`, `corpus` only `.pdf`,
and neither is recursive. The risk of one source getting synthesized twice with no cross-check
is removed mechanically, not by writing discipline.

**Confidential or unstructured PDFs** get converted first:

```powershell
.\rag.ps1 convert "name.pdf"   # Marker -> "1. raw\name.md"; original PDF moves to "1. raw\_source-pdf\"
.\rag.ps1 ingest               # that .md now enters vector, the original PDF is not swept
```

Conversion is a deliberate choice, not a mandatory gate: most structured PDFs
go straight to PageIndex with no conversion. The same `convert` path is also used when
PageIndex extraction turns out weak on a particular structured PDF; it's the last fallback
left once `vcorpus` stops sweeping PDFs.

**Terra deny-list for the vector path.** As long as an `.md` file is in `1. raw/` and not
listed in `1. raw/_terra-tolak.txt`, `ask-file` assembles it through Terra and the result can
be promoted to the wiki by `kimi-k3`. `_terra-tolak.txt` holds only the names of CONFIDENTIAL `.md`
files; a listed file comes out as a verbatim passage plus `[NEEDS SOURCE]` with no API call, and
`promote-terra` rejects it - use the mechanical lane `terra-context`, which writes a
clean note automatically and runs the gate. Backward compat: if
`_terra-tolak.txt` doesn't exist but `_terra-boleh.txt` does, the old allow-list still applies.

## Batch synthesis

Files in `tmp\ask-batch\*.md` are for **cross-document** questions. A question locked
to one source uses `.\rag.ps1 ask-file`, not this batch path.

Format: a `# ...` line becomes the packet title, a `tool:` line picks the engine, other lines become questions.
Run `.\rag.ps1 synth` (wraps `ask-batch.ps1` in the control plane); add `-DryRun` to preview
the plan. Results land in `tmp\retrieval-packets/` as raw evidence, not wiki. The follow-up is
`promote-vpacket.py` for vector packets.

Cross-source claims are deliberately not drafted automatically: the risk of misattribution across
documents is higher, so a human builds the argument. A permanent thematic note is only written when
its conclusion gets reused across many outputs; otherwise thematic reasoning happens
while assembling `3. output/`.

## Terra promotion without Kimi

The `terra-context` lane makes no API call. The script reads the unreviewed draft, fills in front matter,
turns `###` outline headings into `##`, strips the draft banner/status, the negative test, `## Gap backlog`,
and any unanswered-question subsection, then writes the note to `2. wiki/`. The index, `_C2 Log`,
draft status, and gate are updated automatically.

```powershell
.\rag.ps1 terra-context "<slug>"
.\rag.ps1 terra-context --all
```

Front matter uses `method: "terra-context (mechanical)"`, inherits `type`/`source-refs`, and
downgrades `confidence: Certain` to `Likely`. This result is clean in format, not verified in
substance. For material gaps, use the Kimi lane:

```powershell
.\rag.ps1 promote-terra "<slug>"
```

An existing target note is never overwritten without `--force`. Only re-run `terra-gate` when
a manual audit of an already-written note is needed.

## Derived files (safe to delete, can be rebuilt)

- `.pageindex/`, `.vector/`, `manifest.json` - retrieval index and catalog.
- `tmp/retrieval-packets/` - the per-file transit log (`ask-file`/`ask-essential`) and batch evidence packets. `tmp/ask-batch/` holds the question files themselves (not derived; keep it).
- `2. wiki/_terra-drafts/` - per-file drafts, append-only, `status: terra-draft-unreviewed`. Not a wiki note until promoted: `.\rag.ps1 terra-context "<slug>"` (mechanical, no API) or `.\rag.ps1 promote-terra "<slug>"` (Kimi gap-fill, needs `MOONSHOT_API_KEY` if there's a real backlog).
- `.loop/` - loop-phase artifacts (`plan.md`, `critique.md`, `verify.md`, `state.json`, `run.lock`).

Canonical evidence lives only in `1. raw/`. Canonical synthesis lives only in `2. wiki/`.
