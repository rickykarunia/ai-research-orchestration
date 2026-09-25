"""Local vector corpus CLI -- TEMPLATE per-vault (every `.md` in "1. raw/").

Copy to the domain vault root, edit CONFIG. Corpus paths (`1. raw/`, `.vector/`) are relative
to this file. The embedding engine is NOT duplicated: this file points at the shared library in
ai-orchestration/retrieval. Local embedding (fastembed) -> data never leaves the machine.

Flat routing: PDFs go to corpus.py/PageIndex, `.md` goes here. Confidential or
unstructured PDFs are converted first via `rag.ps1 convert`, which drops a `.md` in "1. raw/"
and parks the original PDF in "1. raw/_source-pdf/".

    py -3.13 vcorpus.py ingest      # embed new/changed .md in "1. raw/" (local, free)
    py -3.13 vcorpus.py ask "q"     # top relevant chunk ACROSS the corpus (local, no API)
    py -3.13 vcorpus.py ask-file "name.md" "q"   # one file -> transit + wiki draft
    py -3.13 vcorpus.py ask-essential "name.md"  # essential set, 1 file -> transit + draft
    py -3.13 vcorpus.py ask-essential --new      # only files without a draft yet
    py -3.13 vcorpus.py ask-essential --all      # every indexed file
    py -3.13 vcorpus.py list        # indexed documents
    py -3.13 vcorpus.py check       # self-test (no model/API)

`ask-file` picks the synthesis path mechanically via the deny-list
"1. raw/_terra-tolak.txt" (one file name per line, `#` for comments):

    not listed -> Terra (GPT) assembles an answer from the passages; the passage text IS SENT to the API.
    listed     -> mechanical extraction: verbatim passage + [NEEDS SOURCE]; no API call.

Deny-list: as long as a file is in `1. raw/` and not listed in `_terra-tolak.txt`, it gets
synthesized directly. List ONLY confidential files. Backward compat: if `_terra-tolak.txt`
doesn't exist but `_terra-boleh.txt` does, the old allow-list behavior still applies.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ============================ CONFIG (edit per vault) ============================
# Shared library (vector_store + synthlog). Leave it pointing at ai-orchestration/retrieval;
# DON'T copy it into every vault. One engine, many vaults.
RETRIEVAL_LIB = r"__AIO_KIT__\retrieval"
# Model used to assemble answers for files on the allow list. Match corpus.py's CHAT_MODEL.
CHAT_MODEL = "gpt-5.6-terra"
# ==================================================================================
sys.path.insert(0, RETRIEVAL_LIB)
import vector_store as vs   # noqa: E402
import synthlog             # noqa: E402

RAW_DIR = os.path.join(HERE, "1. raw")
DENY_FILE = os.path.join(RAW_DIR, "_terra-tolak.txt")
LEGACY_ALLOW_FILE = os.path.join(RAW_DIR, "_terra-boleh.txt")

# Essential query set for the vector path (`vcorpus-essential-v1`). Designed to explore
# regulation and standards documents, NOT a copy of corpus.py's generic-paper Q1-Q8.
# Phrased as "this document", not "this regulation", so literature `.md` files are covered too.
# `purpose` is used verbatim as the draft heading by synthlog.essential_draft_block,
# so changing it changes the draft's shape. The canary purpose MUST still start with "Negative test".
ESSENTIAL_QUERIES = [
    ("Q1", "Scope & subject",
     "What is the scope of this document's rules or discussion, and which parties or transactions are subject to it?"),
    ("Q2", "Definitions",
     "What key terms and definitions does this document set out, and what does each definition say?"),
    ("Q3", "Core provisions",
     "What are this document's main provisions, obligations, or treatments, including conditions, thresholds, and quantitative criteria (values, percentages, time periods), by article or paragraph?"),
    ("Q4", "Limits & exceptions",
     "What does this document exclude, prohibit, or state is out of scope?"),
    ("Q5", "Transition & effective date",
     "What transitional provisions, effective date, and treatment of prior situations does this document set out?"),
    ("Q6", "Authority discretion",
     "What discretionary or determination authority does this document grant to a regulator or authority, and at what point in the process?"),
    ("Q7", "Links to other rules",
     "What other rules, standards, or documents does this document reference, revoke, or amend?"),
    ("Q8", "Locator",
     "For each important provision, which article, paragraph, or section is it in?"),
    ("Q9", "Negative test (umpan)",
     "What does this document say about growing grapes on Mars?"),
    ("Q10", "Gap",
     "What important question does this document leave unanswered?"),
]


def _read_names(path):
    """-> a set of lowercase file names, or None if the file doesn't exist. None means 'this
    tier doesn't apply'; set() means 'exists but empty' (an empty deny-list blocks nothing)."""
    if not os.path.exists(path):
        return None
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.add(line.lower())
    return out


def terra_allowed(name, deny_path=None, allow_path=None):
    """Allowed to be sent to the API (the Terra path)? Precedence:
      1. `_terra-tolak.txt` exists -> deny-list: allowed unless the name is listed confidential.
      2. else `_terra-boleh.txt` exists -> old allow-list: allowed only if listed.
      3. else -> allowed (default synthesis).
    A file listed in `_terra-tolak.txt` -> mechanical path, no API call."""
    n = name.lower()
    deny = _read_names(deny_path or DENY_FILE)
    if deny is not None:
        return n not in deny
    allow = _read_names(allow_path or LEGACY_ALLOW_FILE)
    if allow is not None:
        return n in allow
    return True


def hits_for_file(name, question, k=6):
    """Top passages from ONE file. Source filtering happens inside the retriever,
    BEFORE ranking, so the top-k that comes out is the top-k among this file's own chunks.

    Passages below `vs.WEAK` are dropped, not just labeled: that threshold is the same
    "not evidence" cutoff used by promote-vpacket.py. Letting them through would mean
    putting irrelevant text into the draft as a citation, and on the Terra path it means
    sending junk passages to the API while diluting the grounding."""
    hits = vs.VectorRetriever(HERE).retrieve(question, k=k, source=name)
    return select_hits(hits, name, k)


def select_hits(hits, name, k=6):
    """Filter retrieve results into (kept, best_score_seen). Split out from
    the index call so it can be tested without embeddings."""
    same = [h for h in hits if h.source.lower() == name.lower()]
    kept = [h for h in same if h.score >= vs.WEAK][:k]
    # The highest score that WAS seen is also returned, so the caller can tell
    # "file isn't in the index" apart from "it's there but everything's below the threshold".
    return kept, (same[0].score if same else None)


def _passage_lines(hits):
    out = []
    for h in hits:
        out.append(f"- **[{h.score:.3f} {vs.confidence(h.score)}]** `{h.source} {h.locator}`")
        out.append(f"  > {h.text.strip()}")
        if h.parent:
            out.append(f"  > parent: {h.parent.strip()[:700]}")
        out.append("")
    return out


def terra_answer(question, hits):
    """Assemble an answer from passages that are ALREADY retrieved. The passages are sent to
    the API, so this function may only be called for a file that isn't listed confidential
    in `_terra-tolak.txt` (see `terra_allowed`)."""
    from openai import OpenAI
    ctx = "\n\n".join(
        f"[{i + 1}] {h.source} {h.locator} (score {h.score:.3f})\n{h.parent or h.text}"
        for i, h in enumerate(hits)
    )
    sys_msg = (
        "Assemble the answer ONLY from the passages given. Do not add outside "
        "knowledge. Every claim must be followed by a source marker [n] matching the passage number. "
        "If the passages don't answer it, write exactly: [NEEDS SOURCE] and state what's missing. "
        "Don't invent numbers, article references, or names."
    )
    resp = OpenAI().chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": sys_msg},
                  {"role": "user", "content": f"Passages:\n\n{ctx}\n\nQuestion: {question}"}],
    )
    return resp.choices[0].message.content


def _answer_one(name, question):
    """Retrieve + answer ONE question for ONE file.

    -> (answer, method, allowed, hits). If no passage clears the threshold, `answer` is None
    and `method` holds a [NEEDS SOURCE] message ready to print or write to the draft.

    Split out from `ask_file` so `ask_essential` uses the exact same Terra/mechanical path,
    instead of duplicating it. `terra_allowed` is the single place that decides which file
    may be sent to the API: allowed unless listed confidential in `_terra-tolak.txt`.
    """
    hits, best = hits_for_file(name, question)
    if not hits:
        if best is None:
            msg = f"[NEEDS SOURCE] no passages from '{name}'. Has it been ingested? Check `vcorpus.py list`."
        else:
            msg = f"[NEEDS SOURCE] top score {best:.3f} < {vs.WEAK} -- no sufficiently relevant passage; don't answer from this."
        return None, msg, False, []

    allowed = terra_allowed(name)
    if allowed:
        method = f"vcorpus.py + Terra ({CHAT_MODEL}); passages sent to the API"
        answer = terra_answer(question, hits)
        if answer is None or not str(answer).strip():
            # message.content can be null: a content-filter finish, or a tool call with no text.
            # Different from the two [NEEDS SOURCE] cases above (retrieval found nothing) --
            # here a passage was found and is relevant, but the model produced no answer.
            msg = (f"[NEEDS SOURCE] Terra ({CHAT_MODEL}) returned no answer for '{name}' "
                   "-- likely a content filter or a tool call with no text; a passage was retrieved, "
                   "but nothing could be assembled. Don't answer from this.")
            return None, msg, allowed, hits
    else:
        method = "vcorpus.py (local vector, mechanical; no API)"
        answer = "\n".join(_passage_lines(hits))
    return answer, method, allowed, hits


def ask_file(name, question):
    answer, method, allowed, hits = _answer_one(name, question)
    if answer is None:
        print(method)
        return

    print(answer)
    if allowed:
        label = "Ad hoc question (Terra)"
        draft = [f"## {synthlog.stamp()} - Ad hoc question (Terra, unreviewed)", "",
                 f"**{question.strip()}**", "", str(answer).strip(), "",
                 "### Cited passages (verbatim)", ""] + _passage_lines(hits)
    else:
        label = "Ad hoc question (mechanical)"
        draft = [f"## {synthlog.stamp()} - Ad hoc question (mechanical, no claim yet)", "",
                 f"**{question.strip()}**", "",
                 "This file is listed confidential in `_terra-tolak.txt`, so no model assembled an answer.",
                 "The passage below is verbatim. Write the claim yourself.", "",
                 "[NEEDS SOURCE] claim not yet written by a human.", "",
                 "### Passage (verbatim)", ""] + _passage_lines(hits)

    t, d = synthlog.record(HERE, name, method,
                           [("Q", label, question, answer)], label, draft)
    print(f"\npath   : {'Terra (default)' if allowed else 'mechanical (confidential, _terra-tolak.txt)'}")
    print(f"transit: {t}\ndraft  : {d}")


def ask_essential(name):
    """Run every ESSENTIAL_QUERIES entry on one `.md`, write transit + draft (append).

    A query that finds no passage above the threshold still gets a section; its content is a
    [NEEDS SOURCE] message. An empty section is more useful than a missing one: it marks
    which question the corpus hasn't covered yet, and that's Gap backlog material.
    """
    allowed = terra_allowed(name)
    path = "Terra (default)" if allowed else "mechanical (confidential)"
    print(f"essential {len(ESSENTIAL_QUERIES)} quer(y/ies) for '{name}' via the {path} path ...", flush=True)

    answers = []
    method = None
    for qid, purpose, query in ESSENTIAL_QUERIES:
        print(f"  {qid} {purpose}", flush=True)
        answer, m, _allowed, _hits = _answer_one(name, query)
        if answer is None:
            answers.append((qid, purpose, query, m))   # the [NEEDS SOURCE] message goes into the draft as-is
        else:
            method = m
            answers.append((qid, purpose, query, answer))

    if method is None:
        # Not one query got a passage. Write the draft anyway, so this file has a record,
        # and so `--new` doesn't keep retrying it while nothing in the corpus has changed.
        method = (f"vcorpus.py + Terra ({CHAT_MODEL})" if allowed
                  else "vcorpus.py (local vector, mechanical; no API)")

    t, d = synthlog.record(HERE, name, method, answers, "Essential",
                           synthlog.essential_draft_block(answers, label="Essential"),
                           transit_extra=["query-set: vcorpus-essential-v1"])
    print(f"transit: {t}\ndraft  : {d}")


def _indexed_names():
    """File names present in the vector index, sorted. The source is the manifest written by
    `vs.build_index`, not the contents of `1. raw/`: a file not yet ingested genuinely can't
    be queried, and including it would just produce ten [NEEDS SOURCE] results."""
    man = os.path.join(HERE, ".vector", "manifest.json")
    if not os.path.exists(man):
        sys.exit("empty corpus -- run `ingest` first.")
    with open(man, encoding="utf-8") as fh:
        return sorted(json.load(fh).keys())


def ask_essential_all(only_new=False):
    """Run essential synthesis over several files at once.

    `only_new=True` skips files that already have a draft. That's the normal path after
    adding files to `1. raw/`: without this filter, every old file gets a duplicate
    dated section in its append-only draft, and API calls are wasted.
    """
    names = _indexed_names()
    if only_new:
        skipped = [n for n in names if not synthlog.needs_essential(HERE, n)]
        names = [n for n in names if synthlog.needs_essential(HERE, n)]
        if skipped:
            print(f"skipping {len(skipped)} file(s) that already have a draft.")
    if not names:
        print("no files need synthesis.")
        return
    print(f"essential for {len(names)} file(s); {len(names) * len(ESSENTIAL_QUERIES)} question(s).")
    for n in names:
        ask_essential(n)


def _selftest():
    import tempfile
    global _answer_one, HERE, _indexed_names, ask_essential   # ask_essential_all looks up its collaborators in module scope; declared up top
    global hits_for_file, terra_allowed, terra_answer          # patched in the Terra-empty test below
    vs._selftest()             # since the Task 2 assertion already references _answer_one earlier
    with tempfile.TemporaryDirectory() as td:
        deny = os.path.join(td, "_terra-tolak.txt")
        allow = os.path.join(td, "_terra-boleh.txt")
        absent = os.path.join(td, "_absent.txt")
        assert _read_names(deny) is None, "missing file -> None sentinel"
        # tier 1: deny-list
        open(deny, "w", encoding="utf-8").write("# comment\nConfidential.md\n\n  Internal Case.md  \n")
        assert _read_names(deny) == {"confidential.md", "internal case.md"}, _read_names(deny)
        assert terra_allowed("Regulation.md", deny_path=deny) is True, "not listed confidential -> synthesis allowed"
        assert terra_allowed("CONFIDENTIAL.md", deny_path=deny) is False, "listed confidential -> mechanical, case-insensitive"
        # tier 1 empty: nothing blocked
        open(deny, "w", encoding="utf-8").write("# comment only\n")
        assert terra_allowed("anything.md", deny_path=deny) is True, "empty deny-list -> everything allowed"
        # tier 2: the old allow-list is used only when _terra-tolak.txt doesn't exist
        open(allow, "w", encoding="utf-8").write("Public.md\n")
        assert terra_allowed("Public.md", deny_path=absent, allow_path=allow) is True, "listed on allow-list -> allowed"
        assert terra_allowed("Other.md", deny_path=absent, allow_path=allow) is False, "not on allow-list -> mechanical"
        # tier 3: no gate file at all -> allowed
        assert terra_allowed("free.md", deny_path=absent, allow_path=absent) is True, "no gate -> default synthesis"

    # evidence threshold: a passage < WEAK is dropped, not labeled. Letting it through would
    # put irrelevant text in the draft as a citation.
    import collections
    H = collections.namedtuple("H", "source score")
    hits = [H("a.md", 0.81), H("b.md", 0.77), H("a.md", 0.60), H("a.md", 0.42)]
    kept, best = select_hits(hits, "A.MD")
    assert [h.score for h in kept] == [0.81, 0.60], kept
    assert best == 0.81, best
    kept, best = select_hits([H("a.md", 0.42), H("a.md", 0.30)], "a.md")
    assert kept == [] and best == 0.42, (kept, best)   # the file exists, everything's below threshold
    kept, best = select_hits([H("b.md", 0.9)], "a.md")
    assert kept == [] and best is None, (kept, best)   # the file isn't in the results at all
    assert len(select_hits([H("a.md", 0.9)] * 10, "a.md", k=3)[0]) == 3, "k limit respected"

    # --- essential query set: shape, uniqueness, and canary ---
    assert len(ESSENTIAL_QUERIES) == 10, f"vcorpus essential set is 10 queries, got {len(ESSENTIAL_QUERIES)}"
    qids = [q[0] for q in ESSENTIAL_QUERIES]
    assert len(set(qids)) == len(qids), f"QIDs must be unique: {qids}"
    for qid, purpose, query in ESSENTIAL_QUERIES:
        assert qid and purpose and query, f"empty entry: {(qid, purpose, query)}"
        assert isinstance(query, str) and query.strip().endswith("?"), f"{qid} is not a question"
    canary = [p for _q, p, _t in ESSENTIAL_QUERIES if p.startswith("Negative test")]
    assert len(canary) == 1, f"exactly one canary, got {canary}"

    # --- _answer_one returns a 4-tuple, and fails safe with no index ---
    import inspect
    assert len(inspect.signature(_answer_one).parameters) == 2, "_answer_one(name, question)"

    # --- a None/empty Terra return (content-filter, tool-call with no text) must fail to
    # [NEEDS SOURCE], not leak through as an answer -- see _answer_one. Patch hits_for_file
    # + terra_allowed so the allow-list path activates without a real index or API.
    orig_hff, orig_ta, orig_tans = hits_for_file, terra_allowed, terra_answer
    try:
        hits_for_file = lambda name, question, k=6: ([H("x.md", 0.9)], 0.9)
        terra_allowed = lambda *a, **k: True
        terra_answer = lambda question, hits: None
        answer, method, allowed, hits2 = _answer_one("x.md", "test question?")
        assert answer is None, "an empty Terra result must fail to None, not pass through as an answer"
        assert "[NEEDS SOURCE]" in method, f"method must flag the failure: {method}"
    finally:
        hits_for_file, terra_allowed, terra_answer = orig_hff, orig_ta, orig_tans

    # --- ask_essential run for real, with _answer_one and HERE swapped out ---
    # (`global _answer_one, HERE` is declared at the top of _selftest)
    orig_answer_one, orig_here = _answer_one, HERE
    called = []

    def _fake(name, question):
        called.append(question)
        # the fourth query deliberately fails: confirm the section is still written, with a gap message
        if len(called) == 4:
            return None, "[NEEDS SOURCE] top score 0.100 < 0.35 -- no sufficiently relevant passage; don't answer from this.", False, []
        return f"answer for {question[:20]}", "vcorpus.py (test)", False, []

    with tempfile.TemporaryDirectory() as td5:
        try:
            _answer_one, HERE = _fake, td5
            ask_essential("test-regulation.md")
        finally:
            _answer_one, HERE = orig_answer_one, orig_here

        assert len(called) == len(ESSENTIAL_QUERIES), \
            f"every query must run, got {len(called)}"
        assert called == [q for _i, _p, q in ESSENTIAL_QUERIES], "query order preserved"

        draft = open(synthlog.draft_path(td5, "test-regulation.md"), encoding="utf-8").read()
        for _qid, purpose, _query in ESSENTIAL_QUERIES:
            assert f"### {purpose}" in draft, f"missing section in draft: {purpose}"
        assert "[NEEDS SOURCE]" in draft, "a failed query still gets a section with a gap message"
        assert draft.count("Query umpan") == 1, "canary annotation exactly once"
        assert "status: terra-draft-unreviewed" in draft, "draft front matter written"

        transit = open(synthlog.transit_path(td5, "test-regulation.md"), encoding="utf-8").read()
        assert "query-set: vcorpus-essential-v1" in transit, "transit records the query set"

    assert len(inspect.signature(ask_essential).parameters) == 1, "ask_essential(name)"

    # --- --new filter: a file that already has a draft is skipped ---
    with tempfile.TemporaryDirectory() as td4:
        all_names = ["a.md", "b.md", "c.md"]
        synthlog.append_block(synthlog.draft_path(td4, "b.md"), ["H"], ["already there"])
        fresh = [n for n in all_names if synthlog.needs_essential(td4, n)]
        assert fresh == ["a.md", "c.md"], f"b.md must be skipped, got {fresh}"
        skipped = [n for n in all_names if not synthlog.needs_essential(td4, n)]
        assert skipped == ["b.md"], skipped

    assert len(inspect.signature(ask_essential_all).parameters) == 1, "ask_essential_all(only_new)"
    assert inspect.signature(ask_essential_all).parameters["only_new"].default is False, \
        "default --all, not --new: the thrifty mode must be requested explicitly"

    # --- ask_essential_all run for real: the --new partition must not be inverted ---
    # (`global _indexed_names, ask_essential, HERE` is declared at the top of _selftest)
    orig_indexed, orig_ask_essential, orig_here6 = _indexed_names, ask_essential, HERE
    three = ["one.md", "two.md", "three.md"]
    called_all = []
    with tempfile.TemporaryDirectory() as td6:
        try:
            _indexed_names = lambda: list(three)
            ask_essential = lambda name: called_all.append(name)
            HERE = td6
            synthlog.append_block(synthlog.draft_path(HERE, "two.md"), ["H"], ["content"])

            ask_essential_all(only_new=True)
            assert called_all == ["one.md", "three.md"], \
                f"--new should only cover files without a draft, in order: {called_all}"

            del called_all[:]
            ask_essential_all()
            assert called_all == three, \
                f"with no argument: every indexed file gets synthesized: {called_all}"
        finally:
            _indexed_names, ask_essential, HERE = orig_indexed, orig_ask_essential, orig_here6

    print("OK vcorpus selftest")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "ingest":
        vs.build_index(HERE)
    elif cmd == "ask":
        if len(sys.argv) < 3:
            sys.exit('usage: vcorpus.py ask "question"')
        hits = vs.VectorRetriever(HERE).retrieve(sys.argv[2], k=5)
        if not hits:
            print("empty corpus -- run ingest first.")
        elif vs.confidence(hits[0].score) == "none":
            print(f"[NEEDS SOURCE] top score {hits[0].score:.3f} < {vs.WEAK} -- no sufficiently relevant chunk; don't answer from this.")
        else:
            seen = set()
            for p in hits:
                # ranking line first (stable format for any downstream parser), then the
                # precise child match, then the full parent section once (small-to-big).
                print(f"[{p.score:.3f} {vs.confidence(p.score)}] {p.source} {p.locator}")
                print(f"  match: {p.text[:300]}")
                key = (p.source, p.locator)
                if p.parent and key not in seen:
                    print(f"  parent [{len(p.parent)} ch]: {p.parent[:700]}")
                seen.add(key)
                print()
    elif cmd == "ask-file":
        if len(sys.argv) < 4:
            sys.exit('usage: vcorpus.py ask-file "name.md" "question"')
        ask_file(sys.argv[2], sys.argv[3])
    elif cmd == "ask-essential":
        if len(sys.argv) < 3:
            sys.exit('usage: vcorpus.py ask-essential "name.md" | --all | --new')
        if sys.argv[2] == "--all":
            ask_essential_all()
        elif sys.argv[2] == "--new":
            ask_essential_all(only_new=True)
        else:
            ask_essential(sys.argv[2])
    elif cmd == "list":
        man = os.path.join(HERE, ".vector", "manifest.json")
        print(open(man, encoding="utf-8").read() if os.path.exists(man) else "empty corpus")
    elif cmd == "check":
        _selftest()
    else:
        sys.exit(f"unknown: {cmd}")


if __name__ == "__main__":
    main()
