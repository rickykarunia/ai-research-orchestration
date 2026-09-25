"""PageIndex corpus engine -- TEMPLATE per-vault.

Copy this file to the domain vault root (e.g. Projects/my-vault/corpus.py),
then edit the CONFIG block below. Every other path is relative to this file's
location, so the engine automatically works on that vault's `1. raw/`, `.pageindex/`, `2. wiki/`.
Needs OPENAI_API_KEY. Internal/confidential documents: use vcorpus.py (local embedding),
not this file.


Layout (relative to this file):
    1. raw/        source PDFs -- drop files here, then `ingest`
    .pageindex/    local tree index (auto)
    manifest.json  {filename: {doc_id, sha256}} -- lets ingest skip unchanged PDFs

Usage:
    py -3.13 corpus.py ingest            # index new/changed PDFs in "1. raw/"
    py -3.13 corpus.py ingest "name.pdf" # index just that one file (still sha-skip if unchanged)
    py -3.13 corpus.py ask "question"    # ask ACROSS every indexed PDF; prints only, writes nothing
    py -3.13 corpus.py ask-file "name.pdf" "question"   # one PDF -> transit + wiki draft (append)
    py -3.13 corpus.py ask-essential "name.pdf"         # Q1-Q8 one PDF -> transit + wiki draft
    py -3.13 corpus.py ask-essential --all              # Q1-Q8 whole corpus, one file pair per PDF
    py -3.13 corpus.py ask-essential --new              # only PDFs without a draft yet
    py -3.13 corpus.py list              # show indexed docs
    py -3.13 corpus.py remove "name.pdf" # drop from .pageindex/ + manifest; 1. raw/ untouched
    py -3.13 corpus.py check             # self-test (no API calls)

`ask` deliberately writes nothing. Cross-document questions are interpretive and
risk misattribution across sources, so a human reads the result and writes it up manually,
instead of it becoming an automatic draft. Only answers locked to ONE source get written automatically.

Needs OPENAI_API_KEY. Models are the two constants below -- swap for real IDs.

For OpenAI Agents SDK / other frameworks, import this module and call
openai_agent_config() or agent_tools() (see bottom).
"""
import os
import sys
import json
import hashlib
import datetime
import re

# ============================ CONFIG (edit per vault) ============================
INDEX_MODEL = "gpt-5.6-luna"   # builds the tree index (a cheap model is enough)
CHAT_MODEL  = "gpt-5.6-terra"  # searches the tree (cheaper; a strict review is still required)
# Name of the entry note in "2. wiki/" where the document inventory table is synced.
# Match it to this vault's `entry` in AGENTS.md. If it differs, sync-wiki is skipped silently.
WIKI_NOTE   = "00 - Index PDF Corpus.md"
# Shared transit+draft writer. Leave it pointing at ai-orchestration/retrieval;
# don't copy synthlog.py into every vault.
RETRIEVAL_LIB = r"__AIO_KIT__\retrieval"
# ==================================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "1. raw")
STORAGE = os.path.join(HERE, ".pageindex")
MANIFEST = os.path.join(HERE, "manifest.json")
WIKI = os.path.join(HERE, "2. wiki", WIKI_NOTE)
METHOD = f"corpus.py (PageIndex, {CHAT_MODEL})"

sys.path.insert(0, RETRIEVAL_LIB)
import synthlog  # noqa: E402  -- shared library path is only inserted on the line above
_DOCS_BEGIN = "<!-- corpus:docs -->"
_DOCS_END = "<!-- /corpus:docs -->"

# Terra raw->wiki synthesizer query set (Codex harness Mode C). Q1-Q8 written as a
# reviewable retrieval packet BEFORE any wiki synthesis, per
# codex-review-harness/prompts/pageindex-raw-to-wiki-synthesizer.md.
# The draft's section order now follows the QID order here (Q1..Q8), since the shared
# formatter synthlog.essential_draft_block builds it that way. Older drafts (from the
# private formatter that predates this one) used a different order: per-section coverage
# before the locator, canary last -- that's not a typo, just an earlier formatter era.
ESSENTIAL_QUERIES = [
    ("Q1", "Structure", "What are this document's main chapter/section structure?"),
    ("Q2", "Main claims / findings", "What are this document's main claims, findings, or arguments?"),
    ("Q3", "Key concepts", "What key concepts, terms, or definitions does this document explain?"),
    ("Q4", "Evidence base / method", "What data, methods, analytical basis, or type of evidence does this document use?"),
    ("Q5", "Negative test (umpan)", "What does this document say about a topic that is certainly not in it: growing grapes on Mars?"),
    ("Q6", "Locator", "For this document's most important claim or finding, where (section or page) is it stated?"),
    ("Q7", "Per-section coverage", "For each main section, what is the core idea that must not be missed in a synthesis?"),
    ("Q8", "Gap", "What important question does this document leave unanswered?"),
]


def _client(indexing=False):
    """PageIndexClient in local mode. Models only needed when indexing/chatting."""
    from pageindex import PageIndexClient
    return PageIndexClient(index_model=INDEX_MODEL, chat_model=CHAT_MODEL, storage_path=STORAGE)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_manifest(m):
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)


def ingest(target=None):
    """Index PDFs in RAW whose hash is new or changed. Skip unchanged.
    target: filename to index alone (still respects sha-skip); None = sweep all of RAW."""
    if not os.path.isdir(RAW):
        sys.exit(f"missing folder: {RAW}")
    if target:
        if not os.path.exists(os.path.join(RAW, target)):
            sys.exit(f"not found: {os.path.join(RAW, target)}")
        pdfs = [target]
    else:
        pdfs = [f for f in os.listdir(RAW) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"no PDFs in {RAW} -- drop files there first.")
        return
    manifest = _load_manifest()
    client = _client(indexing=True)
    failed = []
    for name in sorted(pdfs):
        path = os.path.join(RAW, name)
        digest = _sha256(path)
        if manifest.get(name, {}).get("sha256") == digest:
            print(f"skip  {name} (unchanged)")
            continue
        print(f"index {name} ...", flush=True)
        # no single mode fits every PDF: flash (heuristic structure) is fast and
        # handles clean layouts; standard (LLM reasoning) handles PDFs flash can't
        # structure. Try flash first, fall back to standard. One bad PDF must not
        # kill the batch, so failures are collected and reported, not raised.
        try:
            try:
                doc = client.submit_document(path, mode="flash", wait=True)
            except Exception as e_flash:
                print(f"  flash failed ({e_flash}); trying standard ...", flush=True)
                doc = client.submit_document(path, mode="standard", wait=True)
        except Exception as e:
            print(f"  FAILED {name}: {e}")
            failed.append(name)
            continue
        doc_id = doc.get("doc_id") or doc.get("id")
        manifest[name] = {"doc_id": doc_id, "sha256": digest,
                          "indexed_at": datetime.date.today().isoformat()}
        _save_manifest(manifest)   # persist per-file so a crash keeps progress
        print(f"  done -> {doc_id}")
    print(f"\nmanifest: {len(manifest)} docs -> {MANIFEST}")
    if failed:
        print(f"FAILED to index ({len(failed)}): {', '.join(failed)}")
        print("  A PDF with no section structure, or a pure scan, often fails in local mode.")
        print("  Try a structured document (a titled report/regulation/paper), or OCR/PageIndex Cloud.")
    sync_wiki()   # keep the wiki inventory table in step with the manifest


def _all_doc_ids():
    return [v["doc_id"] for v in _load_manifest().values() if v.get("doc_id")]


def _resolve_doc(name):
    """Return (manifest_name, doc_id) for an indexed PDF name (case-insensitive)."""
    manifest = _load_manifest()
    if name in manifest and manifest[name].get("doc_id"):
        return name, manifest[name]["doc_id"]
    matches = [k for k, v in manifest.items() if k.lower() == name.lower() and v.get("doc_id")]
    if len(matches) == 1:
        match = matches[0]
        return match, manifest[match]["doc_id"]
    if not matches:
        sys.exit(f"not in manifest: {name} (check `corpus.py list` or run ingest)")
    sys.exit(f"ambiguous name: {name} matches {', '.join(matches)}")


def remove(name):
    """Drop one doc from the local .pageindex/ store + manifest. Does NOT touch
    1. raw/ -- source PDF stays put (AI-RULES SS6: raw is immutable)."""
    manifest = _load_manifest()
    entry = manifest.get(name)
    if not entry:
        sys.exit(f"not in manifest: {name} (check `corpus.py list`)")
    doc_id = entry.get("doc_id")
    if doc_id:
        try:
            _client().delete_document(doc_id)
        except Exception as e:
            print(f"  warning: failed to delete from .pageindex/ store ({e}); continuing to remove from manifest")
    del manifest[name]
    _save_manifest(manifest)
    print(f"removed from index: {name} (the PDF file in 1. raw/ was not touched)")
    sync_wiki()


def ask(question):
    """Ask across every indexed PDF at once (multi-doc tree search)."""
    doc_ids = _all_doc_ids()
    if not doc_ids:
        sys.exit("empty corpus -- run `ingest` first.")
    client = _client()
    print(f"searching {len(doc_ids)} doc(s)...\n")
    print(client.chat(question, doc_id=doc_ids))


def ask_file(name, question):
    """Ask one indexed PDF. The answer is logged to the transit log AND the wiki draft, appended.
    Asking the same file again adds a new section; the old ones are untouched."""
    manifest_name, doc_id = _resolve_doc(name)
    client = _client()
    print(f"searching 1 doc: {manifest_name}\n")
    answer = client.chat(question, doc_id=[doc_id])
    print(answer)
    t, d = synthlog.record(
        HERE, manifest_name, METHOD,
        [("Q", "Ad hoc question", question, answer)],
        "Ad hoc question",
        [f"## {synthlog.stamp()} - Ad hoc question", "", f"**{question.strip()}**", "",
         str(answer).strip(), ""],
        transit_extra=[f'doc-id: "{doc_id}"'],
    )
    print(f"\ntransit: {t}\ndraft  : {d}")


def ask_essential(name):
    """Run Q1-Q8 on one PDF, write to the transit log + wiki draft (append)."""
    manifest_name, doc_id = _resolve_doc(name)
    client = _client()
    answers = []
    print(f"running essential Q1-Q8 for {manifest_name} with {CHAT_MODEL} ...", flush=True)
    for qid, purpose, query in ESSENTIAL_QUERIES:
        print(f"  {qid} {purpose}", flush=True)
        answers.append((qid, purpose, query, client.chat(query, doc_id=[doc_id])))
    t, d = synthlog.record(HERE, manifest_name, METHOD, answers, "Essential Q1-Q8",
                           synthlog.essential_draft_block(answers, label="Essential Q1-Q8"),
                           transit_extra=[f'doc-id: "{doc_id}"',
                                          "query-set: pageindex-essential-q1-q8"])
    print(f"transit: {t}\ndraft  : {d}")


def ask_essential_all(only_new=False):
    """Run Q1-Q8 for every indexed PDF, one packet per file.

    `only_new=True` skips PDFs that already have a draft. This is the normal path after
    adding PDFs to `1. raw/`: without this filter, every old PDF gets a duplicate section
    in the append-only draft and PageIndex calls are wasted.
    """
    manifest = _load_manifest()
    names = [name for name, v in sorted(manifest.items()) if v.get("doc_id")]
    if not names:
        sys.exit("empty corpus -- run `ingest` first.")
    if only_new:
        skipped = [n for n in names if not synthlog.needs_essential(HERE, n)]
        names = [n for n in names if synthlog.needs_essential(HERE, n)]
        if skipped:
            print(f"skipping {len(skipped)} PDF(s) that already have a draft.")
    if not names:
        print("no PDFs need synthesis.")
        return
    print(f"running essential packets for {len(names)} doc(s); this calls PageIndex {len(names) * len(ESSENTIAL_QUERIES)} times.")
    for name in names:
        ask_essential(name)


def list_docs():
    m = _load_manifest()
    if not m:
        print("empty corpus.")
        return
    for name, v in m.items():
        print(f"{v.get('doc_id')}  {name}")


def _render_docs_table(manifest):
    rows = ["| # | PDF name | doc_id | Ingested on |", "|---|---|---|---|"]
    for i, (name, v) in enumerate(sorted(manifest.items()), 1):
        rows.append(f"| {i} | {name} | `{v.get('doc_id','')}` | {v.get('indexed_at','-')} |")
    if len(rows) == 2:
        rows.append("| - | _(empty corpus)_ | - | - |")
    return "\n".join(rows)


def _replace_between(text, begin, end, body):
    """Swap content between the begin/end markers with body. Markers kept.
    Returns None if either marker is missing (caller skips)."""
    if begin not in text or end not in text:
        return None
    pre = text.split(begin, 1)[0]
    post = text.split(end, 1)[1]
    return f"{pre}{begin}\n{body}\n{end}{post}"


def sync_wiki():
    """Rewrite the auto doc-inventory table in the wiki entry note from the manifest.
    Only the region between the corpus:docs markers changes; synthesis is preserved."""
    if not os.path.exists(WIKI):
        print(f"  wiki note doesn't exist, skipping sync: {WIKI}")
        return
    with open(WIKI, encoding="utf-8") as fh:
        text = fh.read()
    body = _render_docs_table(_load_manifest())
    new = _replace_between(text, _DOCS_BEGIN, _DOCS_END, body)
    if new is None:
        new = text.rstrip() + f"\n\n## PDF Corpus (PageIndex)\n\n{_DOCS_BEGIN}\n{body}\n{_DOCS_END}\n"
        print(f"  marker {_DOCS_BEGIN} not found in the wiki; added the table section.")
    if new != text:
        with open(WIKI, "w", encoding="utf-8") as fh:
            fh.write(new)
    print(f"  wiki table synced ({len(_load_manifest())} doc(s))")


def check():
    """Self-test: manifest round-trip + hash-skip + wiki table sync. No API calls."""
    import tempfile
    # hash is stable and change-sensitive
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
        t.write(b"hello"); p = t.name
    try:
        h1 = _sha256(p)
        with open(p, "ab") as fh:
            fh.write(b"x")
        h2 = _sha256(p)
        assert h1 != h2, "hash must change when bytes change"
        assert _sha256(p) == h2, "hash must be stable for same bytes"
    finally:
        os.unlink(p)
    # manifest round-trips
    global MANIFEST
    real = MANIFEST
    fd, MANIFEST = tempfile.mkstemp(prefix="corpus_selftest_manifest_", suffix=".json")
    os.close(fd)
    try:
        _save_manifest({"a.pdf": {"doc_id": "pi-x", "sha256": "abc"}})
        assert _load_manifest()["a.pdf"]["doc_id"] == "pi-x"
        # skip logic: same sha => treated as unchanged
        m = _load_manifest()
        assert m.get("a.pdf", {}).get("sha256") == "abc"
        assert _resolve_doc("A.PDF") == ("a.pdf", "pi-x"), "case-insensitive doc resolution"
    finally:
        if os.path.exists(MANIFEST):
            os.unlink(MANIFEST)
        MANIFEST = real
    assert synthlog.slugify("My Report (Final).pdf") == "my-report-final", "packet slug is stable"
    # transit + draft must land inside the vault, not the vault root like the old version
    assert synthlog.transit_path(HERE, "x.pdf").startswith(os.path.join(HERE, "tmp")), "transit under tmp/"
    assert "_terra-drafts" in synthlog.draft_path(HERE, "x.pdf"), "draft under 2. wiki/_terra-drafts/"
    assert len(ESSENTIAL_QUERIES) == 8, "essential query set must stay Q1-Q8"
    # wiki table sync: marker-replace keeps surroundings, swaps body only
    body = _render_docs_table({"z.pdf": {"doc_id": "pi-1", "indexed_at": "2026-01-01"}})
    assert "z.pdf" in body and "pi-1" in body
    sample = f"HEAD\n{_DOCS_BEGIN}\nOLD\n{_DOCS_END}\nTAIL"
    out = _replace_between(sample, _DOCS_BEGIN, _DOCS_END, body)
    assert out.startswith("HEAD") and out.rstrip().endswith("TAIL"), "surroundings preserved"
    assert "OLD" not in out and "z.pdf" in out, "body replaced"
    assert _replace_between("no markers", _DOCS_BEGIN, _DOCS_END, "x") is None, "missing markers -> None"
    appended = "HEAD".rstrip() + f"\n\n## PDF Corpus (PageIndex)\n\n{_DOCS_BEGIN}\n{body}\n{_DOCS_END}\n"
    assert _DOCS_BEGIN in appended and "z.pdf" in appended, "missing marker path appends table section"
    # purpose is used verbatim as the draft heading, so don't mix two languages here
    canary_c = [p for _q, p, _t in ESSENTIAL_QUERIES if p.startswith("Negative test")]
    assert len(canary_c) == 1, f"exactly one canary in corpus, got {canary_c}"
    blok_c = synthlog.essential_draft_block(
        [(q, p, t, f"answer {q}") for q, p, t in ESSENTIAL_QUERIES], label="Essential Q1-Q8")
    assert blok_c[0].endswith("- Essential Q1-Q8"), blok_c[0]
    assert "### Structure" in blok_c, "purpose heading in English"
    assert "### Main claims / findings" in blok_c
    assert sum("Query umpan" in ln for ln in blok_c) == 1, "canary annotation exactly once"
    assert not any(p in ("Struktur", "Klaim / temuan utama", "Konsep kunci") for _q, p, _t in ESSENTIAL_QUERIES), \
        "corpus purpose labels are already in English"

    import inspect as _inspect
    assert _inspect.signature(ask_essential_all).parameters["only_new"].default is False, \
        "default --all; the thrifty mode must be requested explicitly"
    print("check OK")


# ---- adapters for OpenAI Agents SDK / other agent frameworks ----
def openai_agent_config():
    """Kwargs for `agents.Agent(**openai_agent_config())` -- searches the whole corpus."""
    return _client().openai_agent_config(doc_id=_all_doc_ids())


def agent_tools():
    """Plain tool functions for LangChain / PydanticAI / etc., scoped to the corpus."""
    return _client().agent_tools()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "ingest":
        ingest(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "ask":
        if len(sys.argv) < 3:
            sys.exit('usage: corpus.py ask "your question"')
        ask(sys.argv[2])
    elif cmd == "ask-file":
        if len(sys.argv) < 4:
            sys.exit('usage: corpus.py ask-file "name.pdf" "your question"')
        ask_file(sys.argv[2], sys.argv[3])
    elif cmd == "ask-essential":
        if len(sys.argv) < 3:
            sys.exit('usage: corpus.py ask-essential "name.pdf" | --all | --new')
        if sys.argv[2] == "--all":
            ask_essential_all()
        elif sys.argv[2] == "--new":
            ask_essential_all(only_new=True)
        else:
            ask_essential(sys.argv[2])
    elif cmd == "draft-wiki":
        # Old name for the same path. `ask-essential` now writes the wiki draft too, so
        # they're the same command. The alias is kept so old notes don't break.
        if len(sys.argv) < 3:
            sys.exit('usage: corpus.py draft-wiki "name.pdf"  (deprecated alias for ask-essential)')
        print("note: `draft-wiki` is now an alias for `ask-essential`; use ask-essential.")
        ask_essential(sys.argv[2])
    elif cmd == "list":
        list_docs()
    elif cmd == "sync-wiki":
        sync_wiki()
    elif cmd == "remove":
        if len(sys.argv) < 3:
            sys.exit('usage: corpus.py remove "name.pdf"')
        remove(sys.argv[2])
    elif cmd == "check":
        check()
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")
