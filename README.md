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

## Requirements

- Windows, PowerShell 5.1 or later.
- Python 3.13, reachable via the `py` launcher (`py -3.13 ...`).
- Claude Code. Codex is optional and only needed for the explicit loop-engine fallback.
- Cloud retrieval (PageIndex, structured PDFs) needs an `OPENAI_API_KEY` environment variable.
- Local retrieval (the vector store) needs no key. Embeddings run on the machine with
  fastembed; documents never leave it.
- The gap-fill lane (`promote-terra`, Kimi `kimi-k3`) needs a `MOONSHOT_API_KEY` environment
  variable. Everything else runs without it.

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

## Quick start

1. Create a vault:

   ```powershell
   .\scripts\new-vault.ps1 my-research -Type generic
   ```

   Add `-DryRun` first to preview the files without writing anything. `-Type` picks a default
   skill set (`paper`, `kajian`, `regulasi`, `app`, `saas`, `ideation`, `equity`, `oped`, or
   `generic`); `-NoLoop` skips the raw/wiki/output folders for a project that doesn't need them.

2. Change into the vault directory:

   ```powershell
   cd "$HOME\Projects\my-research"
   ```

3. Drop source documents into `1. raw\`, then build the corpus:

   ```powershell
   .\rag.ps1 ingest          # local vector store: every .md in "1. raw" (convert PDFs first)
   .\rag.ps1 ingest -Page    # PageIndex: structured PDFs (needs OPENAI_API_KEY)
   ```

4. Ask questions against the corpus, then promote a draft into `2. wiki/` with
   `.\rag.ps1 terra-context "<slug>"` (mechanical, no API) or `.\rag.ps1 promote-terra "<slug>"`
   (fills real gaps via an LLM call).

5. Assemble a deliverable from the wiki notes with the `/loop-engine <name>` skill in Claude
   Code. It runs PLAN, ACT, REVIEW, and VERIFY in sequence and writes to `3. output/`.

6. After adding, removing, or re-tagging a vault, regenerate the routing index. This command
   runs from anywhere, referencing the kit path (e.g., if you cloned to `~/git-repo/ai-research-orchestration`):

   ```powershell
   py -3.13 "$HOME\git-repo\ai-research-orchestration\scripts\index_sync.py"
   ```

   Or if the kit is elsewhere, use its full path instead.

Full command and flag reference: `REFERENCE.md`.

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
