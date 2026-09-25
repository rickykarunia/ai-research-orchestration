# Per-vault retrieval template

Two engines you can copy into any domain vault so the project gets its own retrieval, instead of
piling every PDF into the central `ai-orchestration` corpus. The reasoning behind the split is in
[`../../REFERENCE.md`](../../REFERENCE.md#kenapa-retrieval-per-vault). The full workflow is
in [`../../README.md`](../../README.md).

| File | For | Needs an API? |
|---|---|---|
| `corpus.py` | every `*.pdf` in `1. raw/` - PageIndex tree | yes, `OPENAI_API_KEY` |
| `vcorpus.py` | every `*.md` in `1. raw/` - local vector embedding | no, except `ask-file` on a file NOT listed in `_terra-tolak.txt` (deny-list) |

Routing is decided by extension, not by judging content. No file enters both indexes:
`corpus` only sweeps `.pdf`, `vcorpus` only `.md`, and neither is recursive. Confidential or
unstructured PDFs are converted first via `.\rag.ps1 convert`, which drops a `.md` in `1. raw/` and
parks the original PDF in `1. raw/_source-pdf/` (outside both engines' sweep).

## How to use it

1. Automated path: `scripts\new-vault.ps1` writes `corpus.py` and `vcorpus.py` to the root of a loop
   vault by default. Use `-NoRetrieval` to scaffold without the retrieval wrapper.

2. Manual path / retrofitting an existing vault: copy the matching engine to the domain vault's root:

   ```powershell
   copy "<kit-root>\templates\retrieval-per-vault\vcorpus.py" `
        "$HOME\Projects\<vault>\vcorpus.py"
   ```

3. Edit or check the `CONFIG` block at the top of the file:
   - **`corpus.py`** -> `WIKI_NOTE`: match it to the vault's `entry` in `AGENTS.md` (e.g.
     `"00 - Index Project Name.md"`). On the automated scaffold, this value is filled in from the
     new vault's `entry`. If the note exists but the table marker doesn't, `sync-wiki` adds a
     `Korpus PDF (PageIndex)` section. If the note name differs or is missing, the inventory sync is skipped.
     Current defaults are `INDEX_MODEL = "gpt-5.6-luna"` and `CHAT_MODEL = "gpt-5.6-terra"`.
     Optional: change `INDEX_MODEL`/`CHAT_MODEL` if the vault needs a different model.
   - **`vcorpus.py`** -> `RETRIEVAL_LIB`: leave it pointing at `ai-orchestration/retrieval`. Don't
     copy `vector_store.py` or `synthlog.py` into every vault. One engine, many vaults.
     `corpus.py` uses the same `RETRIEVAL_LIB` for `synthlog.py` (the transit+draft writer).

4. Drop PDFs/MDs into `<vault>/1. raw/`, then run from the vault root:

   ```powershell
   cd "$HOME\Projects\<vault>"
   py -3.13 vcorpus.py check      # self-test first
   py -3.13 vcorpus.py ingest     # embed the .md files in 1. raw/
   py -3.13 vcorpus.py ask "question"                    # CROSS-document, prints only
   py -3.13 vcorpus.py ask-file "name.md" "question"     # ONE file -> transit + draft
   ```

   Swap `vcorpus.py` for `corpus.py` for PDFs (the commands share the same names).

   For several questions at once, use `scripts\ask-batch.ps1`: write questions into
   `tmp\ask-batch\*.md`, run it once, and get a Markdown evidence packet in `tmp\retrieval-packets\`.
   Flag details are in [`../../REFERENCE.md`](../../REFERENCE.md#perintah-terminal-lengkap).

   `vcorpus.py ask` returns a score band: `>= 0.65` strong, `0.55-0.65` weak, `< 0.55`
   `[NEEDS SOURCE]` (the engine abstains). A query outside the corpus's domain **must** fall to
   `[NEEDS SOURCE]` - that's per-vault isolation working, not a retrieval failure.

   `vcorpus.py ingest` only picks up `.md` in `1. raw/`; `.pdf` is handled by `corpus.py`. For a
   table-heavy or confidential PDF, run `.\rag.ps1 convert "name.pdf"` (wraps `pdf2md.ps1`
   /Marker; `-Describe` adds image descriptions via the `gpt-5.6-luna` LLM, needs `OPENAI_API_KEY`).
   The resulting `.md` lands in `1. raw/`, the original PDF moves to `1. raw/_source-pdf/`. Table cells stay
   intact within a chunk and the locator uses the section heading. Number/table queries tend to score
   lower than prose (often `weak`), so verify table results rather than take them at face value.

   `ask-file` writes two append-only files: the transit log `tmp/retrieval-packets/<slug>.md` and
   the draft `2. wiki/_terra-drafts/<slug> (terra-draft).md`. On the vector path, Terra assembles
   the answer for any file NOT listed as confidential in `1. raw/_terra-tolak.txt`
   (deny-list); a confidential file comes out as a verbatim passage plus `[NEEDS SOURCE]`, with no API call.

   Chunking is semantic + parent-child (offline): child = a topic-coherent group of sentences,
   parent = the full section (`ask` prints both the `match` child and the `parent` section). An older corpus needs
   a re-`ingest` to pick this up (delete `.vector/` if the files haven't changed).

## What's automatic, what isn't

Every corpus path (`1. raw/`, `.pageindex/`, `.vector/`, `manifest.json`, `2. wiki/`) is resolved
relative to the engine file's location. So once the wrapper sits at the vault root, the engine
works directly on that vault's corpus. The only thing you edit by hand is the `CONFIG` block: the
wiki note name (`corpus.py`) and the shared library path (`vcorpus.py`).

## Rules that still apply

- Confidential internal documents: **`vcorpus.py` only** (local embedding, data never leaves the machine).
  Don't use `corpus.py` for those - it calls an external API.
- There's no automatic hybrid between `corpus.py` and `vcorpus.py`. If one source ends up in both
  indexes, pick one primary path per synthesis, run the second path only as a comparison or
  fallback, and log the method's provenance per claim.
- Don't compare native scores across methods. The vector score is only an internal gate; a conflict
  between paths must be checked back against `1. raw/`.
- `1. raw/` is immutable. Don't edit/rename/delete a PDF after ingest without permission; the
  `source-refs` chain in `2. wiki/` points to it.
- `.pageindex/` and `.vector/` are derived. Safe to delete, rebuild with `ingest`.
