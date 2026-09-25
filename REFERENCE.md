# REFERENCE

Command, file, and token reference for ai-research-orchestration. Read `README.md` first for the
overall shape; this file is the dictionary.

## Kit folder layout

```
ai-research-orchestration/
  install.ps1              # installer: pip deps, skill junctions (-SkipSkills to skip), ~/AI-RULES.md
  RULES.template.md        # behavior floor, copied to ~/AI-RULES.md on install
  dormant-registry.md      # manual routing entries for vaults outside ~/Projects/
  requirements.txt         # fastembed, numpy, openai, pageindex, pypdf
  LICENSE                  # MIT (templates/csl/ keeps CC BY-SA 3.0)
  .claude-plugin/          # Claude Code plugin + marketplace manifests (skills only)
  .codex-plugin/           # Codex plugin manifest (skills only)
  .agents/plugins/         # Codex marketplace manifest
  scripts/                 # control-plane scripts (see "Scripts" below)
  retrieval/               # shared retrieval contract + eval harness
  skills/                  # Claude Code skills (index-sync, loop-*)
  templates/               # files new-vault.ps1 fills in and copies
    AGENTS - template.md
    CLAUDE - template.md
    "C2 Log - template.md"
    "Project Context - template.md"
    "README - template.md"
    "Issue - template.md"
    csl/                    # apa.csl, ieee.csl, chicago-author-date.csl, chicago-notes-bibliography.csl
    retrieval-per-vault/    # corpus.py, vcorpus.py, rag.ps1, README.md, ask-batch-starter.md
  tests/
    new-vault-citations.ps1
```

## Vault folder layout

Created by `scripts\new-vault.ps1` under `~/Projects/<name>/` (or another `-Root`):

| Path | Role |
|---|---|
| `AGENTS.md` | Control plane: routing front matter, retrieval commands, delta rules. Read by Codex/Antigravity and the `index_sync.py` harvester. |
| `CLAUDE.md` | Thin pointer read by Claude Code; says "read AGENTS.md" rather than duplicating it. Skipped with `-NoClaude`. |
| `1. raw/` | Verbatim source evidence. Immutable once added. |
| `1. raw/_source-pdf/` | Original PDFs parked here after `rag.ps1 convert`, out of both engines' ingest sweep. |
| `1. raw/_terra-tolak.txt` | Deny-list of confidential `.md` file names in `1. raw/` that must never reach an API. |
| `2. wiki/` | Sourced synthesis, one claim-cluster per note, wikilinked. |
| `2. wiki/01 - Project Context.md` | Problem, research question, scope, required sources, neighbor-vault boundary. |
| `2. wiki/_C2 Log.md` | Append-only handoff log between agent roles. |
| `2. wiki/_terra-drafts/` | Per-document synthesis drafts awaiting promotion to a real wiki note. |
| `3. output/` | Deliverables assembled from `2. wiki/` only. |
| `3. output/csl/` | CSL style files copied in at vault creation (apa, ieee, chicago-author-date, chicago-notes-bibliography). |
| `.loop/` | Loop-phase artifacts (`plan.md`, `critique.md`, `verify.md`, `state.json`, `run.lock`). Derived, safe to delete. |
| `.obsidian/` | Vault-root Obsidian config so raw/wiki/output stay one graph. |
| `corpus.py`, `vcorpus.py`, `rag.ps1` | Per-vault retrieval, copied from `templates/retrieval-per-vault/` (skipped with `-NoRetrieval` or `-NoLoop`). |
| `manifest.json` | PageIndex ingest catalog, built by `corpus.py`. |
| `tmp/ask-batch/` | Batch question files for `ask-batch.ps1` / `rag.ps1 synth`. |
| `tmp/retrieval-packets/` | Raw Q&A evidence packets written by `ask-file`/`ask-essential`/batch synthesis. |

## Vault front matter / routing keys

Written in the first YAML block of `AGENTS.md` (or `CLAUDE.md`), which must contain the marker
string `blok routing` for the harvester to read it (see Protocol tokens, below).

| Key | Meaning |
|---|---|
| `vault` | Unique kebab-case vault name. |
| `path` | Vault path, relative to `~` when under `~/Projects/`. |
| `domain` | One-sentence description of what the vault is for. |
| `route-when` | One-line bracket list of up to 5 trigger phrases, e.g. `[a, b, c]`. |
| `not-when` | One-line bracket list of up to 4 exclusion phrases. |
| `depends-on` | Optional bracket list of other vaults a cross-domain task must also open. Omitted, not left empty, when there is none. |
| `entry` | The vault's opening file, e.g. `"2. wiki/00 - Index <Vault>.md"`. |
| `tier` | `active`, `dormant`, or `archive`. Only `active` vaults are considered by default routing. |
| `loop` | `true` if the vault uses the raw -> wiki -> output loop, else `false`. |
| `rules` | Bracket list of rule files, typically `[AGENTS.md]`. |
| `skills` | Bracket list of skills the harness should prefer for this vault. |

Lists must be one-line brackets (`[a, b, c]`); multi-line YAML list syntax is not parsed.

## Scripts (`scripts/`)

### `new-vault.ps1`

Scaffolds a new vault: loop folders, `AGENTS.md`/`CLAUDE.md`, entry note, Project Context note,
C2 log, Obsidian config, and (unless skipped) the retrieval wrapper, then regenerates the
routing index.

```
new-vault.ps1 <Name> [-Domain <text>] [-RouteWhen "a, b, c"] [-DependsOn "vault-a,vault-b"]
              [-Root <path>] [-Type paper|kajian|regulasi|app|saas|ideation|equity|oped|generic]
              [-Skills <name[]>] [-NoRetrieval] [-NoLoop] [-NoClaude] [-DryRun]
```

- `-Name` (positional, required): kebab-case vault name.
- `-Domain` / `-RouteWhen` / `-DependsOn`: fill the matching routing front-matter fields;
  left as placeholders if omitted.
- `-Root`: parent folder for the vault. Default `~/Projects`.
- `-Type`: selects the default skill set and the `AGENTS.md` command-notes text. `kajian` =
  study/analysis vault, `regulasi` = regulation-review vault (Indonesian names, kept for
  compatibility with existing vaults).
- `-Skills`: overrides the type's default skill list.
- `-NoRetrieval`: skip copying `corpus.py`/`vcorpus.py`/`rag.ps1`.
- `-NoLoop`: skip `1. raw`/`3. output`/`.loop/` and the retrieval wrapper (no output stage to
  retrieve for); keeps `2. wiki/`.
- `-NoClaude`: skip writing `CLAUDE.md`.
- `-DryRun`: print every file it would write, write nothing.

A vault created outside `~/Projects/` is not auto-harvested by `index_sync.py`; register it in
`dormant-registry.md` if it needs routing.

### `index_sync.py`

Harvests the routing front matter from every `AGENTS.md`/`CLAUDE.md` under `~/Projects/` (or
`AIO_PROJECTS`) and regenerates `~/AI-INDEX.md`.

```
py -3.13 index_sync.py            # write ~/AI-INDEX.md
py -3.13 index_sync.py --dry      # print to stdout, don't write
```

### `loop_check.py`

Read-only health check on the raw/wiki/output loop and registry freshness across every
`tier: active` vault. Four checks: RATCHET (raw far ahead of wiki), STALE (index older than a
routing block), PROV (a wiki note missing `source-refs`), GAP (an open gap marker with no
`## Gap backlog` section). Exit 0 clean, 1 with findings.

```
py -3.13 loop_check.py                  # all active, loop: true vaults
py -3.13 loop_check.py --vault <name>   # one vault
py -3.13 loop_check.py --self-test      # run the built-in test suite
```

### `loop_resume.py`

Inspects a wiki-to-output loop checkpoint and can claim or release its run lock.

```
py -3.13 loop_resume.py [--vault <path>] [--slug <slug>] [--json] [--claim] [--release]
                         [--run-id <id>] [--executor <name>] [--self-test]
```

- `--executor` defaults to `codex`.
- `--json` prints machine-readable output instead of text.

### `promote-terra.py`

Carries a draft from `2. wiki/_terra-drafts/` into a real `2. wiki/` note. Two lanes share one
mechanical core: `context` (no LLM call) and `promote` (an LLM fills the gap backlog, two calls
per non-trivial gap; needs `MOONSHOT_API_KEY`). `gate` runs the same lint/index/C2-log/
`loop_check.py` checks on a note written either way.

```
py -3.13 promote-terra.py --vault <name> context [<slug> | --all]
py -3.13 promote-terra.py --vault <name> promote [<slug> | --all]
py -3.13 promote-terra.py --vault <name> gate "<slug>" --note "<title>.md"
py -3.13 promote-terra.py --self-test
```

### `promote-vpacket.py`

Packages a vector-store evidence packet (from `rag.ps1 synth`) into a `2. wiki/_packet-drafts/`
note skeleton. Mechanical: copies passages verbatim, drops anything below the score threshold
and any duplicates, draws no conclusions.

```
py -3.13 promote-vpacket.py "<packet path>" [--vault <path>]
py -3.13 promote-vpacket.py --self-test
```

### `review-draft.py`

Sends the dated entries of one `_terra-drafts/` file to an LLM and asks it to flag pairs of
entries whose claims look contradictory. An assistant, not a verdict: it only compares entries
against each other, never against `1. raw/`. Appends its findings to the same draft file.

```
py -3.13 review-draft.py "<vault_dir>" "<source-name>"
py -3.13 review-draft.py --self-test
```

### `tally.py`

Scores a routing eval results file (`id | picked-vault | correct|wrong | note` rows, one per
line, between `<!-- data -->` / `<!-- /data -->` markers) and prints accuracy per group.

```
python tally.py <results-file.md>
python tally.py --self-test
```

### `ask-batch.ps1`

Runs a batch of retrieval questions from a question file (or a folder of them) against
`corpus.py`/`vcorpus.py` in a vault, writing one Markdown evidence packet per question file.
Also reachable through `rag.ps1 synth` inside a vault.

```
ask-batch.ps1 [-Vault <path>] [-Questions <path>] [-OutDir <path>]
              [-Tool corpus.py|vcorpus.py] [-DefaultTool corpus.py|vcorpus.py]
              [-DryRun] [-SelfTest]
```

- `-Vault`: vault root. Default: current directory.
- `-Questions`: a single question file or a folder of them, relative to `-Vault`. Default
  `tmp\ask-batch`.
- `-OutDir`: where evidence packets are written, relative to `-Vault`. Default
  `tmp\retrieval-packets`.
- `-Tool`: forces the engine for every file, overriding any `tool:` line in the question file.
- `-DefaultTool`: engine used when a file has no `tool:` line and `-Tool` isn't given. Default
  `vcorpus.py`.
- `-DryRun`: print the question plan, call nothing.
- `-SelfTest`: run the parser's built-in tests, touch nothing else.

Question file format: the first `# ...` line is the packet title; a `tool: corpus.py` or
`tool: vcorpus.py` line pins the engine; every other non-blank line is one question (a leading
`- ` or `1. ` is stripped); lines starting with `//`, `>`, or `<!--` are ignored. Write one
question file per planned wiki note, for example `tmp\ask-batch\01-literature-review.md`:

```markdown
# Facts - literature on <topic>
tool: corpus.py

What are the main findings of the papers in the corpus on <topic>?
What are the main criticisms of <approach A>?
How do the arguments for <approach A> and <approach B> differ?
```

Each packet lands in `-OutDir` with front matter `type: retrieval-packet`,
`status: bukti-mentah`, and `method:` naming the engine used. No draft is written. A vault
without the `rag.ps1` wrapper calls the script directly:
`& "<kit-root>\scripts\ask-batch.ps1" -Vault . -DryRun`.

## Per-vault retrieval scripts (`templates/retrieval-per-vault/`)

Copied into a vault by `new-vault.ps1` (unless `-NoRetrieval`/`-NoLoop`); the copies, not the
templates, are what a vault actually runs.

### `rag.ps1`

Single entry point for a vault's retrieval. Wraps `corpus.py` (PageIndex) and `vcorpus.py`
(local vector); default engine is `vcorpus.py`, add `-Page` for `corpus.py`.

```
rag.ps1 <check|ingest|list|ask|ask-file|ask-essential|remove|synth|status|convert|
         review-draft|promote-terra|terra-context|terra-gate> [args...] [-Page] [-DryRun]
```

- `check`: self-test both engines present in the vault, no API calls.
- `ingest`: index every `.md` (and, with `-Page`, PDF) in `1. raw/`.
- `ask "<question>"`: cross-document question; prints only, writes no draft.
- `ask-file "<name>" "<question>"`: one-source question; writes to
  `tmp/retrieval-packets/` and `2. wiki/_terra-drafts/` automatically.
- `ask-essential "<name>"` / `--new` / `--all`: the fixed essential-question set for one file,
  files without a draft yet, or every indexed file.
- `synth`: batch cross-document questions from `tmp\ask-batch\*.md` (delegates to
  `ask-batch.ps1`).
- `convert "<name.pdf>"`: convert a confidential/unstructured PDF to Markdown via the
  script named in `AIO_PDF2MD`, then park the original PDF under `1. raw/_source-pdf/`. The
  kit does not ship a converter. `rag.ps1` calls the script with the PDF path and expects a new
  `.md` somewhere under `1. raw/marker_output/` (the layout Marker writes); it moves that file
  to `1. raw/<name>.md`. It never overwrites an existing `.md`, and leaves the PDF in place if
  conversion fails.
- `remove "<name.pdf>"`: drop one PDF from the PageIndex index and manifest. Only
  `corpus.py` implements `remove`, so `rag.ps1` always sends it there (`-Page` not needed).
- `review-draft "<name>"`: flag candidate contradictions across a draft's entries.
- `promote-terra "<slug>"` / `terra-context "<slug>"` / `terra-gate "<slug>" --note "<file>"`:
  the gap-fill, mechanical, and lint-only promotion lanes (see `promote-terra.py` above).
- `status`: file counts per stage plus a `loop_check.py --vault` run.
- `-Page`: use `corpus.py`/PageIndex instead of the default `vcorpus.py`.
- `-DryRun`: for `synth` and `promote-terra`, show the plan without calling the engine/API.

Always run the engines from the vault root with `py -3.13`; their paths are relative to the
engine file's own location.

### `corpus.py` (PageIndex, cloud)

Structured-PDF retrieval via PageIndex tree search, over every top-level `*.pdf` in `1. raw/`.
Needs `OPENAI_API_KEY`.

| Command | What it does | API? |
|---|---|---|
| `py -3.13 corpus.py check` | self-test | no |
| `py -3.13 corpus.py ingest` | index new or changed PDFs; skips files whose sha256 is unchanged | yes |
| `py -3.13 corpus.py ingest "name.pdf"` | index that one file | yes |
| `py -3.13 corpus.py list` | list indexed documents | no |
| `py -3.13 corpus.py ask "q"` | question across every indexed PDF; prints only, writes nothing | yes |
| `py -3.13 corpus.py ask-file "name.pdf" "q"` | one PDF -> packet in `tmp/retrieval-packets/` + draft in `2. wiki/_terra-drafts/` (append) | yes |
| `py -3.13 corpus.py ask-essential "name.pdf"` / `--all` / `--new` | the Q1-Q8 essential set for one PDF, every PDF, or PDFs without a draft | yes |
| `py -3.13 corpus.py draft-wiki "name.pdf"` | deprecated alias for `ask-essential` | yes |
| `py -3.13 corpus.py remove "name.pdf"` | drop from `.pageindex/` and the manifest; `1. raw/` is untouched | no |
| `py -3.13 corpus.py sync-wiki` | rewrite the document-inventory table in the note named by `WIKI_NOTE` (between the `corpus:docs` markers, or appended as a new section if they're missing). Not claim synthesis | no |

`ask` writes nothing on purpose: cross-document answers risk misattribution, so a person reads
and writes them up. Only answers locked to one source become drafts automatically.

The essential set Q1-Q8 covers structure, main claims, key concepts, evidence and method, a
negative test (a bait question about a topic certainly absent from the document), a locator for
the key claim, per-section coverage, and open questions. A long answer to the negative test is a
fabrication signal.

### `vcorpus.py` (local vector)

Local embedding retrieval (fastembed, `paraphrase-multilingual-MiniLM-L12-v2`) over every
top-level `.md` in `1. raw/`. Indexing never leaves the machine. A passage is sent to an API
only when Terra assembles an answer for a file not on the `_terra-tolak.txt` deny-list.

| Command | What it does | API? |
|---|---|---|
| `py -3.13 vcorpus.py check` | self-test | no |
| `py -3.13 vcorpus.py ingest` | embed new or changed `.md`; no PDFs, no subfolders | no |
| `py -3.13 vcorpus.py list` | print the `.vector/manifest.json` catalog | no |
| `py -3.13 vcorpus.py ask "q"` | top 5 child chunks with score and band, plus each parent section (small-to-big). Top score below `WEAK` prints `[NEEDS SOURCE]` | no |
| `py -3.13 vcorpus.py ask-file "name.md" "q"` | one file -> packet + draft. Terra assembles it unless the file is on the deny-list, in which case the output is verbatim passages plus `[NEEDS SOURCE]` | unless denied |
| `py -3.13 vcorpus.py ask-essential "name.md"` / `--all` / `--new` | the 10-query essential set (Q1-Q10) for one file, every file, or files without a draft | unless denied |

Deny-list rules: with `1. raw/_terra-tolak.txt` present, every `.md` is allowed unless listed
(one file name per line, `#` for comments). If only the legacy `_terra-boleh.txt` exists, the
old allow-list applies instead.

### Model constants

Retrieval models and the gap-fill model are separate slots, set as constants in the files:

| Phase | File | Constant | Default |
|---|---|---|---|
| PageIndex, build the tree index | `corpus.py` | `INDEX_MODEL` | `gpt-5.6-luna` |
| PageIndex, search the tree | `corpus.py` | `CHAT_MODEL` | `gpt-5.6-terra` |
| Vector, assemble passages | `vcorpus.py` | `CHAT_MODEL` | `gpt-5.6-terra` |
| Gap-fill promotion | `scripts/promote-terra.py` | `KIMI_MODEL` | `kimi-k3` |

`promote-terra.py` has no `--model` flag. `--max-calls <n>` (default 60) caps LLM calls and
counts two logical steps per draft. If `MOONSHOT_API_KEY` or `MOONSHOT_BASE_URL` is missing from
the current shell, the script falls back to the persistent Windows `User`, then `Machine`,
environment, which helps when the key was set permanently but the terminal is older.

### Verify an index before you rely on it

After a PageIndex ingest, ask six questions. The fourth deliberately asks about something the
document doesn't cover: a healthy index refuses, a leaky one invents an answer.

```powershell
py -3.13 corpus.py ask "What is the main chapter or section structure of this document?"
py -3.13 corpus.py ask "What are the main claims or findings of this document?"
py -3.13 corpus.py ask "What is the value of [column X] in [table title]?"
py -3.13 corpus.py ask "What does this document's methodology say about [an unrelated topic]?"
py -3.13 corpus.py ask "In which section or page is claim [X] stated?"
py -3.13 corpus.py ask "How does [topic] differ between [document A] and [document B]?"
```

## Retrieval engines and when to use local-only

`retrieval/` holds the shared interface both engines implement (`Retriever` protocol,
`Passage` dataclass) and the eval harness that compares them:

| File | Role |
|---|---|
| `retriever.py` | `Retriever`/`Passage` contract + a substring evaluator. Self-test: `py -3.13 retriever.py`. |
| `pageindex_retriever.py` | PageIndex adapter. |
| `vector_store.py` | Local vector engine: semantic + parent-child chunking, fastembed, numpy cosine. Self-test: `py -3.13 vector_store.py`. |
| `run_eval.py` | Runs one retriever over the eval set (substring match). |
| `compare.py` | Runs every registered retriever, writes `eval-results.json`. |

Routing is flat and by file type, not by content judgment: every `.pdf` in `1. raw/` goes to
PageIndex, every `.md` goes to the vector store. Use the vector store exclusively (no cloud
call at all) for anything confidential or unstructured: convert the source to Markdown first
with `rag.ps1 convert`, and list any `.md` file that must never reach an API in
`1. raw/_terra-tolak.txt`. Vector-store answers below the calibrated cosine threshold
(`STRONG=0.65` / `WEAK=0.55`) are treated as `[NEEDS SOURCE]` rather than presented as evidence.

## Environment variables

| Variable | Read by | Purpose |
|---|---|---|
| `AIO_PROJECTS` | `scripts/index_sync.py` | Overrides the scan root for vaults (default `~/Projects`). |
| `AIO_PDF2MD` | `templates/retrieval-per-vault/rag.ps1` | Path to an external PDF-to-Markdown script used by `rag.ps1 convert`. PDF conversion is skipped if unset. |
| `AIO_EVALSET` | `retrieval/run_eval.py`, `retrieval/compare.py` | Path to the eval set (JSONL). Defaults to `evalset.jsonl` next to the scripts. `run_eval.py --evalset` still wins over it. |
| `AIO_EVAL_OUT` | `retrieval/compare.py` | Where `compare.py` writes its results. Defaults to `eval-results.json` next to the script. |
| `OPENAI_API_KEY` | `templates/retrieval-per-vault/corpus.py` | Required for PageIndex retrieval and ingest. |
| `MOONSHOT_API_KEY` | `scripts/promote-terra.py` | Required for the gap-fill promotion lane (`promote-terra.py promote`). |
| `MOONSHOT_BASE_URL` | `scripts/promote-terra.py` | Optional override of the Moonshot API base URL. |

## Protocol tokens

These literal strings are read by scripts and templates and must not be translated or
reworded; a vault written before or after this kit still parses correctly as long as they
appear verbatim.

| Token | Where it appears | Meaning |
|---|---|---|
| `Putusan:` / `LULUS` / `ULANG ACT` / `GAGAL` | Loop verdict lines (`loop_resume.py`, `loop-verify` skill) | Verdict line format: `Putusan: LULUS \| ULANG ACT \| GAGAL`: "verdict: pass / redo the ACT phase / fail". Indonesian, kept for scripts that parse this line literally. |
| `## Gap backlog` | `2. wiki` index notes, `loop_check.py` GAP check | Heading under which unresolved gap markers must be logged before a loop run closes. |
| `[NEEDS SOURCE]` | Wiki notes, drafts, `loop_check.py` | No documentary support found locally (forward gap). |
| `[COVERAGE?]` | Wiki notes | Source was retrieved but the synthesis may not represent its main point yet (backward gap). |
| `[K<n>]` | `3. output/` drafts | Per-claim marker linking a sentence back to the PLAN-phase claim map. |
| `G-TERRA-<slug>-<n>` | Terra draft return-legs | Identifier for a gap logged from the Terra synthesis path. |
| `status: terra-draft-unreviewed` | `2. wiki/_terra-drafts/*.md` front matter | Marks a promoted draft as not yet human-verified against source. |
| `status: bukti-mentah` | Evidence packets written by `ask-batch.ps1` | Indonesian for "raw evidence": marks a packet as work in progress, not a wiki note or a fact. |
| Front-matter keys `vault`, `path`, `domain`, `route-when`, `not-when`, `depends-on`, `entry`, `loop`, `skills` | `AGENTS.md`/`CLAUDE.md` routing blocks | Parsed literally by `index_sync.py`; see "Vault front matter" above. |
| Folder names `1. raw`, `2. wiki`, `3. output`, `.loop/` | Every vault | The loop's canonical stage folders; scripts match these names exactly. |
| `fakta`, `interpretasi`, `hipotesis`, `risiko`, `implikasi-desain` | Wiki note `type:` front matter | Indonesian for fact / interpretation / hypothesis / risk / design implication. Parsed literally by the loop scripts. |
| `## Peta klaim` | PLAN-phase claim maps | Indonesian for "claim map" heading, produced by the `loop-plan` skill. |
| `blok routing` | The first line of a routing front-matter block | Marker `index_sync.py` looks for before treating a front-matter block as a routing block. |
| `_terra-tolak.txt` / `_terra-boleh.txt` | `1. raw/` | Deny-list / (legacy) allow-list of confidential `.md` file names that must never be sent to an API. |
| `Negative test (umpan)` / `Negative test (deteksi fabrikasi)` | `2. wiki/` promotion drafts, `promote-terra.py`, `synthlog.py`, essential query sets | Bait section titles: queries whose correct answer is not in the sources. A long answer signals fabrication risk. Parsed by section-title prefix matching in `synthlog.py`. |

## Dormant registry

`dormant-registry.md` at the kit root lists vaults that live outside `~/Projects/` (and are
therefore not auto-harvested by `index_sync.py`). It is not a set of routing blocks: add one
table row per vault, `vault | path | tier | domain`, between the `<!-- data -->` and
`<!-- /data -->` markers. No leading pipe and no header row; every line with `|` inside the
markers is read as a vault. Rows only carry those four fields, and a harvested vault with the
same name takes precedence.

## Skills (`skills/`)

Installed into `~/.claude/skills/` by `install.ps1` as directory junctions.

| Skill | Role |
|---|---|
| `index-sync` | Regenerates `~/AI-INDEX.md` from every vault's routing block. |
| `loop-plan` | PLAN phase: builds the claim map (`.loop/<slug>/plan.md`) from `2. wiki/` notes. |
| `loop-act` | ACT phase: assembles the `3. output/` draft from the claim map and wiki notes only. |
| `loop-review` | REVIEW phase: adversarial critique of the draft by an independent subagent. |
| `loop-verify` | VERIFY phase: mechanical gate (`loop_check.py` + claim-marker matching) and the return-leg write to `2. wiki/`. |
| `loop-engine` | Orchestrator: chains PLAN -> ACT -> REVIEW -> VERIFY with gates and a bounded loop-back, then a FINISH style pass. |

## Which files you edit

Rule of thumb: `.md` files are yours to read and write. `.json`, `.npy`, `.py`, and dot-folders
are machinery, derived and rebuildable from source.

| File | What it is | Edit by hand? |
|---|---|---|
| `AGENTS.md` / `CLAUDE.md` at the vault root | vault contract: routing, delta rules, default skills | yes, when the rules change |
| `2. wiki/*.md` | sourced synthesis notes | yes, this is the work |
| `3. output/*.md` | deliverables | yes |
| PDFs in `1. raw/` | original evidence | no: don't change, rename, or delete |
| `.md` in `1. raw/` | raw text source, hand-written or converted from a PDF | only if hand-written |
| `1. raw/_terra-tolak.txt` | confidential deny-list | yes |
| `tmp/ask-batch/*.md` | batch question files | yes |
| `tmp/retrieval-packets/*.md` | evidence packets | no, rerun the batch to regenerate |
| `2. wiki/_terra-drafts/*.md` | per-source drafts awaiting promotion | read every section; promote rather than polish |
| `2. wiki/_packet-drafts/*.md` | skeletons from `promote-vpacket.py` | yes, this is what you turn into a note |
| `corpus.py`, `vcorpus.py`, `rag.ps1` | per-vault engines | only to change behavior or the CONFIG block |
| `manifest.json` at the vault root | `corpus.py` ingest catalog (file -> doc_id + sha256), prevents re-indexing | no |
| `.pageindex/` | PageIndex tree index | no |
| `.vector/manifest.json`, `.vector/docs/<doc>/chunks.json`, `parents.json`, `emb.npy` | vector catalog, child chunks, parent sections, embeddings | no |
| `.loop/<slug>/plan.md`, `critique.md`, `verify.md` | loop phase outputs | no, rerun the phase |
| `.loop/<slug>/state.json`, `run.lock` | checkpoint and concurrency lock | no |

Loop artifacts live in `.loop/`, not `2. wiki/`, on purpose: `loop_check.py` walks every `.md`
under `2. wiki` and flags notes without `source-refs`, so a `plan.md` there would trigger a false
PROV finding on every run.

## Why retrieval is per-vault

Each vault holds its own corpus instead of one shared index, for three reasons:

1. **Domain separation.** A combined cross-domain index can't be scoped, retrieval comes back
   noisy, and `route-when` stops meaning anything.
2. **Confidentiality.** Internal documents stay in their own vault with local embeddings only.
3. **Provenance.** `source-refs` in `2. wiki/` point at that vault's own `1. raw/`. Moving raw
   files elsewhere breaks the output -> wiki -> raw chain.

## Citations and Word export

Setup is once per machine; every new vault then carries its own CSL presets.

1. Install [Zotero](https://www.zotero.org/download/) and open it.
2. Install [Better BibTeX for Zotero](https://retorque.re/zotero-better-bibtex/installation/),
   then check `Tools > Plugins` that it is enabled.
3. Install [Pandoc](https://pandoc.org/installing.html), reopen PowerShell, and check
   `pandoc --version`.
4. Create the vault with `new-vault.ps1`. It copies four presets into `3. output/csl/`
   (`apa.csl`, `ieee.csl`, `chicago-author-date.csl`, `chicago-notes-bibliography.csl`); APA is
   the default.
5. In Zotero, select the literature, export it as BibTeX with Better BibTeX, and save it as
   `3. output/refs.bib`. The generator doesn't create this file, and the name must match exactly.
6. Cite in Markdown with `[@citekey]` or `@citekey`.
7. Export from the vault root:

   ```powershell
   pandoc input.md -o output.docx --citeproc --bibliography "3. output/refs.bib" --csl "3. output/csl/apa.csl"
   ```

   Swap the file after `--csl` for IEEE or Chicago. The vault's `AGENTS.md` lists the same
   command for each preset, in `.docx` and `.pdf`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | wrong interpreter | use `py -3.13`, not `python` |
| `Python not found. Set the launcher path in Resolve-Python.` | `rag.ps1` can't find `py` or `python` | install the `py` launcher or edit `Resolve-Python` in the vault's `rag.ps1` |
| Vault missing from `~/AI-INDEX.md` | `route-when` not a one-line `[a, b, c]` list; the front-matter block lacks the string `blok routing`; or the vault is outside `~/Projects/` (`AIO_PROJECTS`) | fix `AGENTS.md` and rerun `index_sync.py`, or add the vault to `dormant-registry.md` |
| `not found: ...` from `corpus.py ingest`, or `no .md in ...` from `vcorpus.py ingest` | the file isn't in this vault's `1. raw/` top level, or has the other extension | move it there; convert PDFs meant for the vector store |
| `empty corpus -- run ingest first.` | vector index not built | `.\rag.ps1 ingest` |
| `[NEEDS SOURCE] top score ... < 0.55` | no chunk relevant enough | rephrase the query, or treat it as a source gap |
| `Set AIO_PDF2MD to convert PDFs.` | no converter configured | set `AIO_PDF2MD` to your PDF-to-Markdown script |
| `Already exists: ... convert never overwrites.` | a `.md` with the same stem is in `1. raw/` | delete or rename it first |
| `note already exists ... skipping (use --force)` | target wiki note exists | review it, then rerun with `--force` if replacing is intended |
| `GATE FAILED:` followed by a list | the note breaks a structural rule | fix each listed item, then rerun `.\rag.ps1 terra-gate "<slug>" --note "<title>.md"` |
| Pandoc `citation ... not found` | the key in Markdown differs from the key in `refs.bib` | copy the exact key from `refs.bib` |

## Known limits

1. **`loop_check.py` proves the traceability chain exists, not that its content is right.**
   Claim-to-source fit is tested in REVIEW, and coverage of main ideas by the gap cycle.
2. **Retrieval is query-driven.** An idea nobody asks about won't surface, and the omission isn't
   detected on its own. That is what `[COVERAGE?]` is for.
3. **Vector score bands are calibrated on paraphrase-multilingual-MiniLM.** `STRONG=0.65` and
   `WEAK=0.55` in `retrieval/vector_store.py` should be re-swept with a per-corpus eval set before
   you treat them as hard cutoffs.
4. **Table queries score lower than prose.** Tables are often retrieved correctly but land in
   `weak`. Verify by eye. This is a MiniLM limit, not a chunking bug.
5. **`terra-context` is format cleanup, not verification.** `status: promoted` from that lane does
   not mean every claim was checked against raw.
