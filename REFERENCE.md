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
`- ` or `1. ` is stripped); lines starting with `//`, `>`, or `<!--` are ignored.

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
  script named in `AIO_PDF2MD`, then park the original PDF under `1. raw/_source-pdf/`.
- `review-draft "<name>"`: flag candidate contradictions across a draft's entries.
- `promote-terra "<slug>"` / `terra-context "<slug>"` / `terra-gate "<slug>" --note "<file>"`:
  the gap-fill, mechanical, and lint-only promotion lanes (see `promote-terra.py` above).
- `status`: file counts per stage plus a `loop_check.py --vault` run.
- `-Page`: use `corpus.py`/PageIndex instead of the default `vcorpus.py`.
- `-DryRun`: for `synth` and `promote-terra`, show the plan without calling the engine/API.

### `corpus.py` (PageIndex, cloud)

Structured-PDF retrieval via PageIndex tree search. Needs `OPENAI_API_KEY`.

```
py -3.13 corpus.py check    # self-test, no API calls
```

### `vcorpus.py` (local vector)

Local embedding retrieval (fastembed) for internal/unstructured PDFs and every `.md` in
`1. raw/`. Data never leaves the machine for indexing; a passage is sent to an API only when
Terra assembles an answer for a file not on the `_terra-tolak.txt` deny-list.

```
py -3.13 vcorpus.py ask "<question>"   # top relevant chunk across the corpus, local, no API
py -3.13 vcorpus.py check              # self-test, no model/API calls
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
