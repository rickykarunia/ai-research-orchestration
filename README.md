# ai-research-orchestration

A Windows toolkit for running research and writing projects as Obsidian-style vaults, with
Claude Code (and optionally Codex) doing the retrieval, synthesis, and drafting. Each project
gets its own vault; a routing index tells the agent which vault to open for a given task.

## What it is

- **One vault per project.** `new-vault.ps1` scaffolds a folder with `AGENTS.md`/`CLAUDE.md`,
  an Obsidian config, and (optionally) a raw/wiki/output loop and a retrieval wrapper.
- **A raw -> wiki -> output loop.** Source evidence goes in `1. raw/` untouched. Synthesis
  with source references goes in `2. wiki/`. Deliverables assembled from the wiki (never from
  raw files or model memory) go in `3. output/`. A behavior floor for this loop, plus
  anti-fabrication and gap-marker rules, ships in `RULES.template.md` and is installed as
  `~/AI-RULES.md`.
- **A cross-vault routing index.** `index_sync.py` scans `~/Projects/` for a routing block in
  each vault's `AGENTS.md`/`CLAUDE.md` and regenerates `~/AI-INDEX.md`, so an agent can match a
  task to the right vault by its `route-when` keywords.
- **Loop skills.** Five Claude Code skills (`loop-plan`, `loop-act`, `loop-review`,
  `loop-verify`, `loop-engine`) turn wiki notes into a reviewed, gate-checked deliverable in
  `3. output/`, instead of a single ungated generation.
- **Two retrieval engines.** PageIndex (cloud, tree search over structured PDFs) and a local
  vector store (fastembed embeddings, semantic + parent-child chunking, no API calls). Routing
  between them is by file type, not by content judgment: `.pdf` goes to PageIndex, `.md` goes
  to the vector store.

See `REFERENCE.md` for the full command and file reference.

## One-screen map

```text
STAGE 1-2   scripts\new-vault.ps1  ->  AGENTS.md + 2. wiki\01 - Project Context.md
                                        |
                                        v  scripts\index_sync.py
                                     AI-INDEX.md  (vault registered, routable)
                                        |
STAGE 3     drop source files    ->  <vault>\1. raw\
                                        |
                    +-------------------+-------------------+
                    |                                       |
                 *.pdf                                   *.md
                    |                                       |
STAGE 4        corpus.py ingest                      vcorpus.py ingest
               -> .pageindex\                        -> .vector\
               needs OPENAI_API_KEY                  local embeddings
                    |                                       |
                    +-------------------+-------------------+
                                        |
STAGE 5      ask-file / ask-essential  -> tmp\retrieval-packets\ + 2. wiki\_terra-drafts\
             (ask-essential --new = only files without a draft yet; both engines)
             ask / scripts\ask-batch.ps1 -> tmp\retrieval-packets\ only (cross-document)
                                        |
STAGE 6      terra-context lifts clean drafts without Kimi; promote-terra fills real gaps via kimi-k3
             review-draft only flags contradiction candidates; both lanes run the structural gate
                                        |
                                        v
                              <vault>\2. wiki\        <- notes with source-refs, where thinking happens
                                        |
STAGE 7                        /loop-engine <name>
                    PLAN -> ACT -> REVIEW -> VERIFY -> FINISH
                                        |
                                        v
                              <vault>\3. output\      <- deliverable, every claim tagged [K<n>]
                                        |
STAGE 8                   return leg + gap backlog flow back to 2. wiki
```

Rules that hold across every stage:

1. `1. raw` is the evidence of origin and is never edited. `2. wiki` is where thinking happens.
   `3. output` holds finished work.
2. Output is assembled from `2. wiki`, never straight from `1. raw` and never from model memory.
3. `.pageindex\`, `.vector\`, converted Markdown and retrieval packets are working derivatives.
   They can be deleted and rebuilt, and they never count as canonical evidence.
4. An unsourced claim is written as `[NEEDS SOURCE]`, not patched over with a logical bridge.

## Why the flow is layered

Each stage produces files with a different level of authority. What makes a deliverable
defensible in front of a reviewer is the chain you can walk backwards, from `3. output` to a file
in `1. raw`. No single file carries that on its own.

### Authority levels

| Level | Artifact | Status | Can a claim rest on it? |
| --- | --- | --- | --- |
| 1 | `1. raw/<source>` | original evidence, canonical | yes, this is ground truth |
| 2 | `tmp/retrieval-packets/<slug>.md` | `status: bukti-mentah` (raw evidence) | no, it is a retrieval record |
| 3 | `2. wiki/_terra-drafts/<slug> (terra-draft).md` | `status: terra-draft-unreviewed`, `confidence: Guessing` | no, it is a machine hypothesis |
| 4 | `2. wiki/<promoted note>` | has `source-refs`, a set `confidence`, `[[wikilink]]`s | yes, still subject to Level 1 |
| 5 | `3. output/<deliverable>` | every claim tagged `[K<n>]`, passed REVIEW and VERIFY | yes, finished work |

When in doubt about which file to trust, the answer is the raw file at Level 1. Levels 2 and 3
are both scratch. A claim becomes trustworthy once it is promoted to Level 4, and even then only
if its locator can be checked against raw.

### Why evidence packets (Level 2) exist

The engines assemble answers with an LLM over retrieved passages. The typical failure is a model
writing a claim the source never made and attaching a citation that looks legitimate. Packets
are there to catch that.

- **Fabrication check.** A packet records what the retriever returned, as returned: verbatim
  passages with scores on the vector path, raw Q&A on the PageIndex path. That record is separate
  from what the model did with it. A draft claim that no passage supports shows up when you
  compare the draft to the packet, without rerunning retrieval.
- **Retrieval failure vs. synthesis failure.** A wrong wiki claim can come from retrieval
  surfacing the wrong passage, or from the model misreading the right one. The packet lets you
  tell which. With only the finished draft, you can't.
- **Defensibility.** When a claim is challenged, the chain packet -> locator -> raw page is the
  answer. It is the same norm a peer reviewer applies.
- **Confidence calibration.** Vector packets carry a score band (`strong`, `weak`, `none`), so a
  claim resting on three `weak` passages doesn't get the same `confidence` as one resting on two
  `strong` ones.

### Why append-only

Drafts and packets grow by adding dated sections; they never overwrite. Once you correct a
confidence level or rewrite a claim in a draft, the next `ask` must not throw that correction
away. The cost is that older sections can go stale without any marker, so the draft banner asks
you to read every section before promoting. The full history stays visible: what was asked, what
came back, and which answer was later revised.

### When a packet is overkill

- **Vector path:** the passages are already pasted into the draft, so the packet duplicates them.
- **PageIndex path:** the draft keeps only the answer prose, not the raw Q&A. Here the packet is
  the only record.
- **Batch `synth`:** writes no draft at all. Turning packets off would lose the output.

Elsewhere a packet is an extra safety layer on top of the verification Stage 6 requires anyway.

## Requirements

- Windows, PowerShell 5.1 or later.
- Python 3.13, reachable via the `py` launcher (`py -3.13 ...`).
- Claude Code. Codex is optional and only needed for the explicit loop-engine fallback.
- Cloud retrieval (PageIndex, structured PDFs) needs an `OPENAI_API_KEY` environment variable.
- Local retrieval (the vector store) needs no key. Embeddings run on the machine with
  fastembed; documents never leave it.
- The gap-fill lane (`promote-terra`, Kimi `kimi-k3`) needs a `MOONSHOT_API_KEY` environment
  variable. Everything else runs without it.
- Optional: an external PDF-to-Markdown converter script (for example one built on Marker),
  pointed to by `AIO_PDF2MD`, for `rag.ps1 convert`. Without it, PDF conversion is skipped.
- Optional, for citations: Zotero with Better BibTeX, and Pandoc. See
  [`REFERENCE.md`](REFERENCE.md#citations-and-word-export).

The retrieval packages (`pageindex`, `fastembed`) are installed for Python 3.13, so always call
`py -3.13`, not a bare `python`. A `ModuleNotFoundError` almost always means the wrong
interpreter. Once a vault exists, this smoke test costs nothing and is safe to repeat:

```powershell
cd "$HOME\Projects\<vault>"
.\rag.ps1 check                                   # self-test of corpus.py and vcorpus.py, no API calls
& "<kit-root>\scripts\ask-batch.ps1" -SelfTest    # batch parser self-test
```

## Install

```powershell
git clone https://github.com/rickykarunia/ai-research-orchestration
cd ai-research-orchestration
.\install.ps1
```

`install.ps1` installs the Python dependencies in `requirements.txt` (skip with
`-SkipPip`). If `pip install` fails, the installer stops and does not continue. Each skill
folder under `skills/` is linked into `~/.claude/skills/` as a directory junction; if a skill
folder already exists there and is not a junction to this kit, it is skipped with a warning.
Finally, `RULES.template.md` is copied to `~/AI-RULES.md` if that file doesn't exist yet
(an existing `~/AI-RULES.md` is left untouched).

### Skills as a plugin (Claude Code, Codex)

The six skills in `skills/` also ship as a plugin. Use this route for Codex, which does not
read `~/.claude/skills/`, or if you prefer plugin-managed updates in Claude Code.

Claude Code:

```text
/plugin marketplace add rickykarunia/ai-research-orchestration
/plugin install ai-research-orchestration@ai-research-orchestration
```

Codex:

```bash
codex plugin marketplace add rickykarunia/ai-research-orchestration
```

Then open `/plugins` in Codex, pick the AI Research Orchestration marketplace and install it.

The plugin carries the skills only. Keep the git clone for the scripts, retrieval library and
templates, because each vault stores the path of the kit it was created from, and a plugin's
install folder changes on every update. With the plugin installed, run the clone's installer
as `.\install.ps1 -SkipSkills` so Claude Code doesn't load each skill twice.

## Staged walkthrough

Stages 0 to 8 match the one-screen map. Every command and flag is listed in
[`REFERENCE.md`](REFERENCE.md); this section says what each stage is for and what it should leave
behind. If the vault already exists, do Stage 0 and then skip to Stage 3.

### Stage 0: routing, pick the vault before anything else

Every session starts here, including sessions in an old vault.

1. Read `~/AI-RULES.md` (the behavior floor) and `~/AI-INDEX.md` (the routing registry).
2. Match the task against each vault's `route-when` and drop candidates hit by `not-when`. Open
   the vaults in `depends-on` too when the task crosses domains.
3. Enter through the vault's `entry` file, then read `2. wiki/01 - Project Context.md` to pin
   down the problem, scope, assumptions, and the boundary with neighbor vaults.
4. If no vault matches, report the gap. Don't answer as if a corpus were available.

Precedence: instructions in the running session beat the project's `AGENTS.md`, which beats
`AI-RULES.md`.

### Stage 1: scaffold the vault

```powershell
cd "<kit-root>\scripts"
.\new-vault.ps1 <kebab-name> -Type <type> -Domain "<one sentence>" -RouteWhen "keyword, keyword, trigger"
.\new-vault.ps1 my-study -Type paper -DependsOn "neighbor-vault-a,neighbor-vault-b"
```

Add `-DryRun` first to preview every file without writing anything. `-Type` picks a default
skill set (`paper`, `kajian`, `regulasi`, `app`, `saas`, `ideation`, `equity`, `oped`, or
`generic`); `-NoLoop` skips the raw/wiki/output folders for a project that doesn't need them.
The vault must sit under `~/Projects/` (or `AIO_PROJECTS`). A vault outside it is not harvested
into the registry unless you add it to `dormant-registry.md`.

Result: `1. raw`, `2. wiki`, `3. output`, `.loop/`, both retrieval engines with the `rag.ps1`
wrapper, `AGENTS.md`, `CLAUDE.md`, `README.md`, an entry note, Project Context, and the C2 Log.

### Stage 2: fill in the vault contract, then register it

Two files are filled in by hand, and they do different jobs:

| File | Plane | Contents |
| --- | --- | --- |
| `AGENTS.md` | control | routing (`domain`, `route-when`, `not-when`, `depends-on`), project delta rules, default skills |
| `2. wiki/01 - Project Context.md` | context | problem background, research or policy question, distinguishing angle, scope, assumptions, required sources, output expectations, neighbor-vault boundary |

Don't copy Project Context into `AGENTS.md`. `AGENTS.md` configures the harness and rarely
changes; Project Context moves every time the research framing shifts. Then register the vault:

```powershell
py -3.13 "<kit-root>\scripts\index_sync.py"
```

Check that the vault appears in the active tier of `~/AI-INDEX.md`. If it doesn't, see
[Troubleshooting](REFERENCE.md#troubleshooting). `AI-INDEX.md` is derived: never edit it by hand.
Change `AGENTS.md` and regenerate. Rerun `index_sync.py` whenever a vault is added, removed,
or re-tagged.

### Stage 3: put sources in `1. raw`

`1. raw` is the evidence of origin. Don't edit, overwrite, rename, move, or delete what's in it
without explicit permission. Put the files in first, then run commands. Every engine looks for
files relative to its own location, so a source missing from the right vault's `1. raw` gives a
"not found" error or an empty corpus.

A source that belongs to one domain lives in that domain's vault (the reasons are in
[`REFERENCE.md`](REFERENCE.md#why-retrieval-is-per-vault)). Convert a confidential, unstructured,
or table-heavy PDF to Markdown first:

```powershell
.\rag.ps1 convert "file-name.pdf"   # needs AIO_PDF2MD; .md lands in "1. raw", PDF moves to "1. raw\_source-pdf"
```

List every `.md` that must never reach an API in `1. raw/_terra-tolak.txt`. Spot-check table
fidelity in the converted file before trusting retrieval over it.

### Stage 4: index the sources

The engine is chosen by file extension, not by judging the content: `.pdf` goes to PageIndex
(`corpus.py`), `.md` goes to the local vector store (`vcorpus.py`). No file lands in both
indexes, and neither engine recurses into subfolders. Run from the vault root:

```powershell
.\rag.ps1 check          # self-test of both engines
.\rag.ps1 ingest         # vector: every .md
.\rag.ps1 ingest -Page   # PageIndex: every PDF
.\rag.ps1 list           # add -Page for the PageIndex catalog
.\rag.ps1 status         # file counts per stage + loop_check
```

`list` is not a formality. If a file is missing there, every later `ask` answers from the wrong
corpus or an empty one. After a PageIndex ingest, run the six verification questions in
[`REFERENCE.md`](REFERENCE.md#verify-an-index-before-you-rely-on-it). One of them asks about a
topic that isn't in the document, and a healthy index refuses it.

Vector scores are an internal gate (`strong` / `weak` / `none`), never compared with PageIndex
output. Table queries often land in `weak` even when retrieved correctly; verify them by eye.

### Stage 5: ask, and collect evidence packets

This is the bridge from `1. raw` to `2. wiki`. The goal is candidate evidence with locators, not
a finished answer.

```powershell
.\rag.ps1 ask "narrow question"                # cross-document, prints only
.\rag.ps1 ask-file "name.md" "question"        # one source -> packet + terra draft
.\rag.ps1 ask-file "name.pdf" "question" -Page
.\rag.ps1 ask-essential --new                  # fixed question set, every .md without a draft
.\rag.ps1 ask-essential --new -Page            # same for PDFs (Q1-Q8)
.\rag.ps1 synth -DryRun                        # batch plan from tmp\ask-batch\*.md
.\rag.ps1 synth                                # batch run -> tmp\retrieval-packets\
```

`synth` writes one packet per question file and deliberately writes no draft. Cross-document
attribution is easier to get wrong, so a person writes those claims. The question-file format is
in [`REFERENCE.md`](REFERENCE.md#ask-batchps1).

Be honest about the limit here. Retrieval only finds what you ask for. A main idea you never
asked about won't surface, and nothing flags the omission. That is why Stage 6 has a coverage
step.

### Stage 6: synthesize in `2. wiki`

One wiki note holds one claim cluster: a fact, interpretation, hypothesis, risk, or design
implication. Drafts from `ask-file` / `ask-essential` land in `2. wiki/_terra-drafts/` with a
`DRAFT` banner, `status: terra-draft-unreviewed`, and `confidence: Guessing`. They are not facts
until checked against `1. raw` and promoted. There are two promotion lanes:

| Lane | Command | What it does |
| --- | --- | --- |
| Mechanical | `.\rag.ps1 terra-context "<slug>"` or `--all` | Turns the draft into a clean note with no LLM call: fills front matter, drops the banner, negative test, gap backlog and unanswered questions, links the note from `00 - Index`, logs to `_C2 Log`, flips the draft to `promoted`, runs the gate. Downgrades `Certain` to `Likely`. |
| Gap-fill | `.\rag.ps1 promote-terra "<slug>"` or `--all` | Same core. When `## Gap backlog` holds real gaps, Kimi runs in two steps: it writes gap queries, the harness retrieves only from the draft's `source-refs`, then it fills the gaps. Unfilled gaps become `G-TERRA-<slug>-<n>` return-leg rows in Project Context and `_C2 Log`. Needs `MOONSHOT_API_KEY`. |

Neither lane overwrites an existing note without `--force`. A finished note carries:

```yaml
---
type: fakta | interpretasi | hipotesis | risiko | implikasi-desain
source-refs: ["1. raw/<file>.pdf#<section or page>"]
confidence: Certain | Likely | Guessing
method: corpus.py | vcorpus.py | terra-context (mechanical) | kimi-k3 (gap-fill)
updated: YYYY-MM-DD
---
```

A note counts as done when:

1. its claims come from retrieval results someone has read, not from model memory;
2. `source-refs` point at raw files with locators another person can check;
3. `confidence` follows the strength of the evidence, not how fluent the answer sounded;
4. it has at least one `[[wikilink]]` to another note;
5. a source that was retrieved but not fully represented is marked `[COVERAGE?]`, and the rest
   is moved to `## Gap backlog`.

`terra-gate` runs inside both lanes, or by hand with
`.\rag.ps1 terra-gate "<slug>" --note "<title>.md"`. It enforces the mechanical part: front
matter, draft markers gone, a wikilink present, the draft flipped, `00 - Index` linking the note,
a `_C2 Log` entry, and a clean `loop_check.py`. It does **not** check that a claim matches its
source. That is your job, or REVIEW's in Stage 7.

You can also promote by hand against the five conditions. For cross-document `synth` packets,
`promote-vpacket.py` builds a skeleton (see [`REFERENCE.md`](REFERENCE.md#promote-vpacketpy)).

### Stage 7: assemble the output through the loop

```text
PLAN -> ACT -> REVIEW -> VERIFY -> FINISH
  ^                        |
  +---- gap to 2. wiki ----+   (max 3 iterations)
```

Run `/loop-engine <deliverable name>` in Claude Code, or one phase at a time with `/loop-plan`,
`/loop-act`, `/loop-review`, `/loop-verify`. Claude Code is the default executor. Codex takes
over only on an explicit user instruction such as "Codex, assemble output for <slug>"; nothing
detects provider limits automatically. Before a takeover changes anything, inspect and claim the
checkpoint:

```powershell
py -3.13 "<kit-root>\scripts\loop_resume.py" --vault <vault-path> --slug <slug> --json
py -3.13 "<kit-root>\scripts\loop_resume.py" --vault <vault-path> --slug <slug> --claim --run-id <uuid> --executor codex
```

`.loop/<slug>/run.lock` stops two executors writing the same target, and `state.json` records
phase, iteration, executor, and `runId`. A lock owned by another run, conflicting state, or an
ambiguous slug is a reason to stop, not to guess. The takeover keeps writing the same canonical
file in `3. output/`.

| Phase | What happens | Artifact |
| --- | --- | --- |
| PLAN | Claim map from the wiki: each claim gets an ID (`K1`, `K2`, ...) and the full chain claim -> wiki note -> raw file -> source section, plus open gaps and pass criteria | `.loop/<slug>/plan.md` |
| ACT | Draft assembled from `2. wiki` only; every claim sentence carries `[K<n>]` | `3. output/<name>.md` |
| REVIEW | Adversarial critique by an independent clean-context subagent; findings rated `BLOCKER`, `MAJOR`, or `MINOR` | `.loop/<slug>/critique.md` |
| VERIFY | Four mechanical checks (below) and the return-leg write | `.loop/<slug>/verify.md` |
| FINISH | One style pass (`humanizer` by default), then `status: final` | the draft itself |

VERIFY checks: (A) every `[K<n>]` exists in the claim map; (B) every `[NEEDS SOURCE]` and
`[COVERAGE?]` has a row in `## Gap backlog`; (C) the return leg is written to `2. wiki`; (D)
`loop_check.py --vault <name>` is clean. C runs before D on purpose, because `loop_check.py`
flags output more than 24 hours newer than the wiki as an unwritten return leg.

Rules for the whole run: no phase is skipped. ACT reads only `2. wiki`. The reviewer is never
the context that wrote the draft. A failing deterministic gate is a failure, whatever the model
thinks. After three iterations, stop and hand the remaining gaps to the user. Verdict lines use
the literal tokens `Putusan: LULUS | ULANG ACT | GAGAL` (pass / redo ACT / fail).

`loop_check.py` proves the traceability chain exists, not that claims match sources (REVIEW) or
cover the source's main ideas (the gap cycle).

### Stage 8: return leg and the gap cycle

A loop isn't done until new source gaps, decisions taken, questions the current evidence can't
answer, and any Claude/Codex disagreement are written back to `2. wiki`. There are two markers,
pointing in opposite directions:

| Marker | Direction | Meaning |
| --- | --- | --- |
| `[NEEDS SOURCE]` | forward | a claim exists, its source doesn't yet |
| `[COVERAGE?]` | backward | a source section no note cites yet, possibly a missed main idea |

Triage every gap into one of two kinds:

| Kind | Meaning | Action |
| --- | --- | --- |
| retrieval gap | the fact is in raw; the query wasn't sharp enough | targeted re-query, at most two reformulations. Closed: write the claim with a locator. Still open: move it to the backlog |
| source gap | the fact isn't in the corpus | don't re-query. Log it as needing new raw, or as a permanent honest limit |

Whatever stays open goes to `## Gap backlog` in the `2. wiki` index note and persists across
sessions. Every gap ends closed or logged, and the GAP check in `loop_check.py` enforces that.

## Practical don'ts

- Don't answer from memory when a vault and its wiki exist.
- Don't build output straight from `1. raw`, and don't treat a derived index as canonical evidence.
- Don't edit `AI-INDEX.md` by hand.
- Don't put `.obsidian` inside `2. wiki`; the Obsidian vault root is the project folder.
- Don't read PDF, DOCX, XLSX, PPTX, images, or other non-Markdown files without explicit
  permission for the task.
- Don't hide gaps to make an output look finished.
- Don't stack `draft-v1`, `draft-v2` in `3. output`. Revise the same file across iterations of
  one run; versioned names are for deliverables already sent, and only when the user asks.
- Don't run a style pass before REVIEW and VERIFY pass.

## Daily routine

```powershell
Get-Content -Raw "$HOME\AI-RULES.md"; Get-Content -Raw "$HOME\AI-INDEX.md"   # 1. rules + registry
cd "$HOME\Projects\<vault>"; .\rag.ps1 ingest                                # 2. index new sources
.\rag.ps1 ask-essential --new                                                # 3. collect evidence
.\rag.ps1 terra-context --all                                                # 4. promote drafts (or promote-terra)
# 5. in Claude Code: /loop-engine <deliverable name>
py -3.13 "<kit-root>\scripts\loop_check.py" --vault <vault>                  # 6. gate
```

## Recommended: humanizer

The loop's FINISH phase runs one style pass before marking an output final. The kit doesn't
ship a style skill of its own. `new-vault.ps1` adds the third-party
[`humanizer`](https://github.com/blader/humanizer) skill to every vault's `skills` list by
default; it removes common signs of AI-generated writing (em-dash runs, inflated language,
rule-of-three padding). Install it separately. The per-type skill sets (`academic-paper`,
`equity-research`, `superpowers:*`, and so on) are third-party too and are not shipped with
the kit.

## License

MIT. See `LICENSE`.

Exception: the citation styles in `templates/csl/` come from the
[Citation Style Language project](https://github.com/citation-style-language/styles) and keep
their own license, CC BY-SA 3.0, as stated inside each `.csl` file.
