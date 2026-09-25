"""Local vector RAG (thin, free, offline) behind the shared Retriever contract.

For Markdown in `1. raw/`, including Marker output converted from PDFs that are
internal, unstructured, or poorly extracted by PageIndex. No API at query time: embeddings computed locally with
fastembed (ONNX, no torch); similarity = brute-force cosine over numpy.

# ponytail: brute-force cosine is O(n) per query. Fine for a local corpus of up to
# a few thousand chunks; swap in faiss/chroma only if that ceiling is actually hit.

Chunking is semantic + parent-child (both offline):
  * child  = a topic-coherent group of sentences, split where adjacent-sentence
             cosine drops past a percentile breakpoint (semantic_chunk). This is
             the unit that gets embedded, ranked, and scored.
  * parent = the whole section it came from (Markdown heading section / PDF page).
             Retrieval ranks on the precise child, then exposes the full parent via
             Passage.parent for small-to-big context. No LLM, no API: sentence
             boundaries use the same local fastembed model.

Index under <corpus>/.vector/:
    manifest.json              {filename: {sha256, n_chunks, indexed_at}}
    docs/<safe>/chunks.json    [{text, source, page}]        (children)
    docs/<safe>/emb.npy        float32 [n_chunks, dim]        (child embeddings)
    docs/<safe>/parents.json   {locator: section_text}        (parent lookup)

Self-test (no model, no API): py -3.13 vector_store.py
"""
from __future__ import annotations
import os
import sys
import json
import re
import hashlib
import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retriever import Passage

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # multilingual, small, free, local
CHUNK_SIZE = 800        # char-window fallback size (oversized single unit only)
OVERLAP = 150
# Semantic chunking knobs.
BREAKPOINT_PCTL = 75    # split where adjacent-sentence distance exceeds this percentile
SEM_MAX_CHARS = 1200    # force a break before a child grows past this
SEM_MIN_CHARS = 200     # merge a sub-this sliver into the previous child
_E5 = "e5" in MODEL.lower()                 # e5 models want query:/passage: prefixes

# Relevance bands for a top cosine score. Vector always returns top-k, so score is
# the only gap signal: below WEAK, the nearest chunk is not evidence -> [NEEDS SOURCE].
# Calibrated 2026-08-23 on paraphrase-multilingual-MiniLM (mean-pool) over a
# self-authored-documents corpus: in-domain top ~0.77-0.80, out-of-domain bait ~0.45-0.53.
# The Codex-audit defaults (0.55/0.40) let a 0.534 wrong-context hit through as "weak";
# these floors put it into "none" (abstain) while keeping true in-domain hits "strong".
# ponytail: still one corpus / one query-pair of evidence. Re-sweep against a real
# per-corpus evalset before treating these as hard cutoffs; distribution shifts with
# model/lang -- and with chunking: these were set on char-window chunks, and semantic
# chunks embed a cleaner (more coherent) unit, so scores may drift up. Re-sweep if the
# bands start mislabelling.
STRONG = 0.65   # usable candidate, still verify
WEAK = 0.55     # >=WEAK & <STRONG: weak, needs a second source; <WEAK: no source


def confidence(score):
    """Band a cosine score: 'strong' | 'weak' | 'none'. 'none' -> treat as [NEEDS SOURCE]."""
    if score >= STRONG:
        return "strong"
    if score >= WEAK:
        return "weak"
    return "none"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def chunk_text(text, size=CHUNK_SIZE, overlap=OVERLAP):
    """Whitespace-normalized, char-window chunks with overlap, split on spaces."""
    text = " ".join(text.split())
    if not text:
        return []
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            sp = text.rfind(" ", i, end)
            if sp > i:
                end = sp
        piece = text[i:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return out


def _split_sentences(text):
    """Split into sentence-ish units for semantic boundary detection. A blank-line
    block that looks like a table (has pipes) stays whole so its rows are not torn
    apart. Model-free."""
    text = text.strip()
    if not text:
        return []
    out = []
    for block in re.split(r"\n\s*\n", text):        # blank-line paragraphs first
        block = block.strip()
        if not block:
            continue
        if "|" in block and "\n" in block:          # pipe table: keep whole
            out.append(" ".join(block.split()))
            continue
        flat = " ".join(block.split())
        for s in re.split(r"(?<=[.!?])\s+", flat):   # then sentence enders
            s = s.strip()
            if s:
                out.append(s)
    return out


def _breakpoints(dists, pctl=BREAKPOINT_PCTL):
    """Indices i where dists[i] (distance between sentence i and i+1) exceeds the
    pctl-th percentile -> a topic boundary. Model-free."""
    if len(dists) == 0:
        return set()
    thr = float(np.percentile(dists, pctl))
    return {i for i, d in enumerate(dists) if d > thr}


def semantic_chunk(text, max_chars=SEM_MAX_CHARS, min_chars=SEM_MIN_CHARS):
    """Group sentences into topic-coherent children using LOCAL embeddings.

    Boundary = a percentile drop in adjacent-sentence cosine, or the running child
    hitting max_chars. Slivers < min_chars merge back into the previous child; any
    child still over max_chars (long run, no drop) is char-windowed as a safety net.
    Offline (fastembed), no API. Returns a list of chunk strings."""
    sents = _split_sentences(text)
    if not sents:
        return []
    if len(sents) == 1:
        return chunk_text(sents[0]) if len(sents[0]) > max_chars else [sents[0]]
    emb = _embed(sents, "passage")
    emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
    sims = np.sum(emb[:-1] * emb[1:], axis=1)        # cosine between consecutive
    brk = _breakpoints(1.0 - sims)
    chunks, cur = [], [sents[0]]
    for i in range(1, len(sents)):
        cur_len = sum(len(s) + 1 for s in cur)
        if (i - 1) in brk or cur_len + len(sents[i]) > max_chars:
            chunks.append(" ".join(cur))
            cur = [sents[i]]
        else:
            cur.append(sents[i])
    if cur:
        chunks.append(" ".join(cur))
    merged = []
    for c in chunks:                                 # fold slivers into previous
        if merged and len(c) < min_chars:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    out = []
    for c in merged:                                 # safety net for a giant run
        out.extend(chunk_text(c) if len(c) > max_chars else [c])
    return out


def _extract(path):
    """Yield (locator, text). PDF: locator = int page number. Markdown: locator = the
    section heading string (Marker-style converter output). The locator lands in chunk['page'];
    retrieve() renders an int as 'p N' and a string verbatim, so old PDF indexes
    (page = int) keep working with no reindex."""
    if path.lower().endswith(".md"):
        yield from _extract_md(path)
        return
    from pypdf import PdfReader
    reader = PdfReader(path)
    for pnum, page in enumerate(reader.pages, 1):
        yield pnum, (page.extract_text() or "")


def _extract_md(path):
    """Yield (heading, section_text) split on ATX headings (#..######). A pipe table
    stays whole inside its section, so its cells survive into one chunk. No heading yet
    -> locator 'md'. chunk_text still whitespace-normalizes, so table row breaks flatten
    but cell content and pipes remain searchable."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    head, buf, out = "md", [], []
    for ln in lines:
        if re.match(r"^#{1,6}\s+\S", ln):
            if any(x.strip() for x in buf):
                out.append((head, "\n".join(buf)))
            head = ln.lstrip("#").strip()[:60]
            buf = [ln]
        else:
            buf.append(ln)
    if any(x.strip() for x in buf):
        out.append((head, "\n".join(buf)))
    yield from out


_MODEL_CACHE = {}


def _embedder():
    from fastembed import TextEmbedding
    if MODEL not in _MODEL_CACHE:
        _MODEL_CACHE[MODEL] = TextEmbedding(model_name=MODEL)
    return _MODEL_CACHE[MODEL]


def _embed(texts, kind):
    """kind = 'query' | 'passage' (e5 prefix). Returns float32 [n, dim]."""
    if _E5:
        texts = [f"{kind}: {t}" for t in texts]
    return np.asarray(list(_embedder().embed(texts)), dtype=np.float32)


# Flat ingest routing (2026-09-03): PDF always goes to corpus.py/PageIndex, vector only .md.
# A confidential or unstructured PDF is converted first via `rag.ps1 convert`, which drops
# the .md result into "1. raw/" and parks the original PDF in "1. raw/_source-pdf/".
INGEST_EXT = (".md",)


def _sources(raw):
    """Files in `1. raw/` eligible for embedding. Deliberately NOT recursive: subfolders
    like `_source-pdf/` and `marker_output/` must stay invisible to ingest."""
    if not os.path.isdir(raw):
        return []
    return sorted(f for f in os.listdir(raw) if f.lower().endswith(INGEST_EXT))


def _vdir(corpus):
    return os.path.join(corpus, ".vector")


def build_index(corpus_dir):
    """Embed new/changed .md in <corpus>/1. raw/ into <corpus>/.vector/. Idempotent."""
    raw = os.path.join(corpus_dir, "1. raw")
    vdir = _vdir(corpus_dir)
    docs = os.path.join(vdir, "docs")
    os.makedirs(docs, exist_ok=True)
    man_path = os.path.join(vdir, "manifest.json")
    manifest = json.load(open(man_path, encoding="utf-8")) if os.path.exists(man_path) else {}
    srcs = _sources(raw)
    if not srcs:
        print(f"no .md in {raw} (PDF is handled by corpus.py; convert first via `rag.ps1 convert`)")
        return
    for name in sorted(srcs):
        path = os.path.join(raw, name)
        digest = _sha256(path)
        if manifest.get(name, {}).get("sha256") == digest:
            print(f"skip  {name} (unchanged)")
            continue
        print(f"embed {name} ...", flush=True)
        chunks, parents = [], {}
        for loc, txt in _extract(path):
            key = str(loc)
            parents[key] = parents[key] + "\n\n" + txt if key in parents else txt
            for c in semantic_chunk(txt):
                chunks.append({"text": c, "source": name, "page": loc})
        if not chunks:
            print("  no text extracted (pure scan? needs OCR) -> skip")
            continue
        emb = _embed([c["text"] for c in chunks], "passage")
        d = os.path.join(docs, _safe(name))
        os.makedirs(d, exist_ok=True)
        json.dump(chunks, open(os.path.join(d, "chunks.json"), "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(parents, open(os.path.join(d, "parents.json"), "w", encoding="utf-8"), ensure_ascii=False)
        np.save(os.path.join(d, "emb.npy"), emb)
        manifest[name] = {"sha256": digest, "n_chunks": len(chunks),
                          "indexed_at": datetime.date.today().isoformat()}
        json.dump(manifest, open(man_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"  done {len(chunks)} chunks")
    print(f"index: {len(manifest)} docs -> {vdir}")


# Cache the index per corpus directory, for the process lifetime. `retrieve()` calls
# _load_all() every time it's called, and the essential-question path calls retrieve ten
# times per file; without the cache, `ask-essential --all` would re-read every chunks.json
# and emb.npy hundreds of times.
# No invalidation: this CLI lives for one command, and `ingest` writes the index in a
# different process from `ask`. Clear it manually via _LOAD_CACHE.clear() when testing.
_LOAD_CACHE = {}


def _load_all(corpus_dir):
    """Return (chunks, embedding_matrix, parents) where parents maps
    (source, locator_str) -> full section text for small-to-big expansion. Old
    indexes without parents.json load with an empty parents map (parent = None).

    The result is cached per corpus_dir for the process lifetime; see _LOAD_CACHE."""
    if corpus_dir in _LOAD_CACHE:
        return _LOAD_CACHE[corpus_dir]
    docs = os.path.join(_vdir(corpus_dir), "docs")
    chunks, embs, parents = [], [], {}
    if not os.path.isdir(docs):
        _LOAD_CACHE[corpus_dir] = (chunks, None, parents)
        return _LOAD_CACHE[corpus_dir]
    for d in sorted(os.listdir(docs)):
        cp = os.path.join(docs, d, "chunks.json")
        ep = os.path.join(docs, d, "emb.npy")
        pp = os.path.join(docs, d, "parents.json")
        if os.path.exists(cp) and os.path.exists(ep):
            ch = json.load(open(cp, encoding="utf-8"))
            chunks.extend(ch)
            embs.append(np.load(ep))
            if os.path.exists(pp) and ch:
                src = ch[0]["source"]
                for loc, ptext in json.load(open(pp, encoding="utf-8")).items():
                    parents[(src, loc)] = ptext
    if not embs:
        _LOAD_CACHE[corpus_dir] = (chunks, None, parents)
        return _LOAD_CACHE[corpus_dir]
    _LOAD_CACHE[corpus_dir] = (chunks, np.vstack(embs), parents)
    return _LOAD_CACHE[corpus_dir]


def _cosine_topk(qv, mat, k):
    qn = qv / (np.linalg.norm(qv) + 1e-9)
    mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sims = mn @ qn
    idx = np.argsort(-sims)[:k]
    return idx, sims


def _locator(loc):
    """int page (PDF) -> 'p N'; string (Markdown heading) -> verbatim. Back-compat:
    old indexes stored int pages, so they still render 'p N'."""
    return f"p {loc}" if isinstance(loc, int) else str(loc)


def _source_rows(chunks, source):
    """Matrix row indices belonging to one source. Matches case-insensitively, same
    as file-name comparisons elsewhere (allow-list, select_hits)."""
    s = source.lower()
    return [i for i, c in enumerate(chunks) if c["source"].lower() == s]


class VectorRetriever:
    name = "vector"

    def __init__(self, corpus_dir):
        self.corpus_dir = corpus_dir

    def retrieve(self, query, k=5, source=None):
        """Top-k passages. `source` restricts candidates to one file BEFORE ranking,
        not filtered afterward: filtering after a global top-k would return an empty
        list for a file that loses the competition even though its relevant chunk is
        in the index."""
        chunks, mat, parents = _load_all(self.corpus_dir)
        if mat is None or not chunks:
            return []
        rows = None
        if source is not None:
            rows = _source_rows(chunks, source)
            if not rows:
                return []
            mat = mat[rows]
        qv = _embed([query], "query")[0]
        idx, sims = _cosine_topk(qv, mat, k)
        out = []
        for i in idx:
            j = rows[i] if rows is not None else i   # map back to the original row
            src, loc = chunks[j]["source"], chunks[j]["page"]
            out.append(Passage(text=chunks[j]["text"], source=src,
                               locator=_locator(loc), score=float(sims[i]),
                               method=self.name, parent=parents.get((src, str(loc)))))
        return out


def _selftest():
    cs = chunk_text("word " * 400, size=200, overlap=50)
    assert len(cs) > 1 and all(len(c) <= 200 for c in cs), "chunking window+overlap"
    # semantic helpers (model-free)
    assert _split_sentences("One sentence. Two sentences! Three?") == ["One sentence.", "Two sentences!", "Three?"], "sentence split"
    ss = _split_sentences("Intro paragraph.\n\n| a | b |\n| 1 | 2 |")
    assert any("| a | b |" in x and "| 1 | 2 |" in x for x in ss), "pipe table block kept whole"
    assert _breakpoints(np.array([0.1, 0.9, 0.1]), pctl=50) == {1}, "high-distance index is a boundary"
    assert _breakpoints(np.array([])) == set(), "no distances -> no breakpoints"
    assert semantic_chunk("Hello world.") == ["Hello world."], "single sentence, no model needed"
    mat = np.array([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]], dtype=np.float32)
    idx, _ = _cosine_topk(np.array([1, 0, 0], dtype=np.float32), mat, 2)
    assert idx[0] == 0 and idx[1] == 2, "cosine ranks nearest then close"
    assert confidence(0.9) == "strong" and confidence(0.60) == "weak" and confidence(0.45) == "none", "score bands"
    assert _locator(3) == "p 3" and _locator("Table 3") == "Table 3", "locator int vs str"
    import tempfile
    # flat routing: PDF to corpus.py/PageIndex, vector only .md. Without this gate a
    # single PDF could land in two indexes and get synthesized twice with no cross-check.
    with tempfile.TemporaryDirectory() as _td:
        for _n in ("a.md", "b.PDF", "c.pdf", "d.txt"):
            open(os.path.join(_td, _n), "w", encoding="utf-8").close()
        assert _sources(_td) == ["a.md"], f"vector ingest is .md only, got {_sources(_td)}"
        assert _sources(os.path.join(_td, "missing")) == [], "missing folder -> empty list"
    md = "# Title\nintro\n\n## Table 3\n| a | b |\n| 1 | 2 |\n"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as t:
        t.write(md); mp = t.name
    try:
        secs = list(_extract(mp))
        heads = [h for h, _ in secs]
        assert "Table 3" in heads, "md split on headings"
        tbl = next(b for h, b in secs if h == "Table 3")
        assert "| a | b |" in tbl and "| 1 | 2 |" in tbl, "table rows kept in section"
    finally:
        os.unlink(mp)
    # --- _load_all is cached per corpus_dir: the second call doesn't touch disk again ---
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        # even an empty corpus must be consistent and recorded in the cache
        a = _load_all(td)
        b = _load_all(td)
        assert a is b, "_load_all's result is reused from cache, not re-read"
        assert td in _LOAD_CACHE, "cache is keyed by corpus_dir"
        _LOAD_CACHE.clear()
        c = _load_all(td)
        assert c is not a, "after clearing the cache, the result is a new object"

    # --- per-source filter: row mapping, and retrieve actually running end to end ---
    ch = [{"source": "a.md", "page": "H1", "text": "alpha"},
          {"source": "b.md", "page": "H1", "text": "beta"},
          {"source": "a.md", "page": "H2", "text": "gamma"}]
    assert _source_rows(ch, "a.md") == [0, 2], _source_rows(ch, "a.md")
    assert _source_rows(ch, "A.MD") == [0, 2], "matches case-insensitively"
    assert _source_rows(ch, "missing.md") == [], "source not present -> empty"

    # retrieve run without a model: prime the index cache, swap out _embed temporarily.
    # Vectors are built so b.md (row 1) wins GLOBALLY, but a.md must still return its own
    # chunks when source is restricted -- this is exactly the bug being guarded against.
    global _embed
    original_embed = _embed
    mat = np.array([[0.6, 0.8, 0.0],      # a.md H1
                    [1.0, 0.0, 0.0],      # b.md H1  <- closest to the query
                    [0.0, 1.0, 0.0]],     # a.md H2
                   dtype=np.float32)
    try:
        _embed = lambda texts, kind: [np.array([1.0, 0.0, 0.0], dtype=np.float32)]
        _LOAD_CACHE["/test-source"] = (ch, mat, {})
        r = VectorRetriever("/test-source")

        everything = r.retrieve("q", k=3)
        assert [p.source for p in everything][0] == "b.md", "unfiltered, b.md wins globally"

        one = r.retrieve("q", k=2, source="a.md")
        assert one and all(p.source == "a.md" for p in one), f"filter leaked: {[p.source for p in one]}"
        assert [p.text for p in one] == ["alpha", "gamma"], f"ordered by score within source: {[p.text for p in one]}"
        assert abs(one[0].score - 0.6) < 1e-5, f"score mapped back to the original row, got {one[0].score}"
        assert one[0].locator == "H1", "locator follows the original row"

        assert r.retrieve("q", k=2, source="missing.md") == [], "source not present -> empty list"
    finally:
        _embed = original_embed
        _LOAD_CACHE.pop("/test-source", None)

    print("vector_store selftest OK")


if __name__ == "__main__":
    _selftest()
