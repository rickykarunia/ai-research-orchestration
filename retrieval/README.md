# retrieval/ — shared interface + multi-method eval

Compares different RAG methods on one quality scale. Two active methods with flat routing: **PageIndex** for `*.pdf` and **vector** for `*.md` in `1. raw/`. An internal or unstructured PDF is converted to Markdown first, and the original PDF is parked in `_source-pdf/`.

## Why this exists

Different retrieval methods can't be made "equal quality" by hand-waving. What actually equalizes them is **one judge/reranker downstream of every method**. This module is the shared interface (`Passage`) + an eval that measures each method on the same scale + an LLM-judge subagent that scores meaning.

## Files

| File | Contents |
|---|---|
| `retriever.py` | the `Retriever` contract + `Passage` + a substring evaluator (`evaluate`, `load_evalset`). No API. Self-test: `py -3.13 retriever.py` |
| `pageindex_retriever.py` | PageIndex adapter (local mode) — one grounded-answer `Passage` |
| `vector_store.py` | local vector engine (**semantic + parent-child** chunking + fastembed + numpy cosine) + `VectorRetriever`. Self-test: `py -3.13 vector_store.py` |
| `evalset.jsonl` | labeled queries: `query`, `expect_contains`, `expect_any`, `expect_source`, `note` |
| `run_eval.py` | eval one retriever (substring) over the eval-set |
| `compare.py` | run ALL methods → `eval-results.json` (for the subagent) |
| `eval-results.json` | raw output per method per query (derived) |
| `EVAL-REPORT.md` | semantic scoring report (output of the `rag-eval` subagent) |

Judging subagent: `rag-eval` (Claude Code subagent; register your own under `~/.claude/agents/`).

## Contract

```python
class Retriever(Protocol):
    name: str
    def retrieve(self, query: str, k: int = 5) -> list[Passage]: ...

@dataclass
class Passage:
    text: str; source: str; locator: str = ""; score: float|None = None; method: str = ""
    parent: str|None = None   # full section (small-to-big); None if the method has none
```

A uniform `Passage` is what lets PageIndex's result (an answer), a vector chunk, and (later) a graph path be compared/merged by one judge.

## Chunking (vector engine)

Semantic + parent-child, both **offline** (no API):

- **child** = a topic-coherent group of sentences. The boundary is a drop in cosine between consecutive sentences (percentile breakpoint `BREAKPOINT_PCTL=75`) or the length passing `SEM_MAX_CHARS=1200`; a sliver `< SEM_MIN_CHARS=200` merges into the previous child; a giant child with no dip falls back to a char-window. This is the unit that gets embedded, ranked, and scored/banded.
- **parent** = the full section the child came from (Markdown heading / PDF page), stored in `docs/<safe>/parents.json` (`{locator: section_text}`). Retrieval ranks the precise child then exposes the full section via `Passage.parent`. `vcorpus.py ask` prints a ranking line + `match` (child) + `parent` once per section.
- LLM-free calibration: sentence boundaries use the same fastembed model, not a LangChain splitter. No new dependency.
- Back-compat: an old index (char-window, no `parents.json`) still reads fine; `parent = None`. To turn on semantic+parent for an old corpus, **re-ingest** (build_index skips a file with the same sha, so delete `.vector/` or change the file to force a re-chunk).
- The band calibration (`STRONG=0.65/WEAK=0.55`) was set on char-window chunks; semantic chunks are more coherent, so scores can drift up. Re-sweep if the bands start mislabelling.

## Two levels of scoring

1. **Substring** (`retriever.py evaluate`): fast, no LLM, but brittle against paraphrase. `expect_any` softens that, doesn't cure it. For quick checks/regressions.
2. **LLM-judge** (subagent `rag-eval`): reads `eval-results.json`, scores meaning, writes `EVAL-REPORT.md`. For a real comparison between methods. This is the "equalizing judge" that makes heterogeneous methods comparable.

## Workflow

```
# 1. fill the corpus (in each vault)
#    pageindex-corpus: py -3.13 corpus.py ingest       (structured)
#    vector-corpus:    py -3.13 vcorpus.py ingest       (unstructured/internal + raw .md, local & free)

# 2. add queries to evalset.jsonl (1-3/doc + at least 1 gap query)

# 3. run the comparison
cd <kit-root>/retrieval
py -3.13 compare.py            # -> eval-results.json (pageindex calls the API; vector is local)

# 4. score + report
#    run the rag-eval subagent (LLM-judge) -> EVAL-REPORT.md
```

## Adding a method

1. Write `<method>_retriever.py`, a class implementing `Retriever` (`.name` + `.retrieve()` returning `Passage`).
2. Register it in `compare.py` (`retrievers = [...]`).
3. Add relevant queries to `evalset.jsonl`, run `compare.py` + the subagent.
4. **Fusion + reranker** only once the eval shows one method is consistently weaker in another method's territory.

## Operational arbitration

There's no automatic hybrid between PageIndex and vector. For routine synthesis, pick one primary path per source: structured PDF to PageIndex, internal/unstructured PDF and every `.md` in `1. raw/` to vector. If both methods are run for the same source, treat the result as a comparison/fallback with per-claim method provenance. Native scores are not compared across methods; conflicts are checked back against the raw source.

## Results summary (2026-08-20)

These are the author's own results on a private corpus. The eval set, corpus, and
`EVAL-REPORT.md` are not shipped, so the figures are not reproducible from this kit; run your
own eval set to calibrate. In short:
- **pageindex** does better on synthesized answers and is **honest about gaps** (a query about a chapter that doesn't exist states it isn't available).
- **vector** returns relevant, paginated chunks but is **gap-blind**: it always offers up top-k even when nothing is relevant (a low score is the only signal).
- **Concrete recommendation (already in place):** a **cosine threshold** on vector — final calibration `>= 0.65` strong, `0.55-0.65` weak, `< 0.55` abstain `[NEEDS SOURCE]`. Closes off the risk of silent fabrication.
- Routing (structured→pageindex, unstructured→vector) plus the threshold is enough for now. Fusion/reranker isn't needed yet.

## Limits (honestly stated)

- **Small n + same corpus** in the baseline: real-world vector conditions (unstructured) haven't been tested yet. Still needed: ingest meeting notes/letters into `vector-corpus`, add queries, repeat.
- Substring matching is brittle (use the subagent for a real assessment).
- No graphify-retriever / reranker yet. Deliberate. Build it once the eval shows it's needed.
