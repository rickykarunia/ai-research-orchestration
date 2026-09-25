"""Writer engine for the transit log + wiki draft, shared by corpus.py and vcorpus.py.

Two files per source, both APPEND-ONLY:

    tmp/retrieval-packets/<slug>.md          raw Q&A log (audit trail)
    2. wiki/_terra-drafts/<slug> (terra-draft).md   formatted wiki draft

Append-only isn't a style choice: once a human corrects a confidence tag or rewrites a
claim in the draft, the next ask must not throw that correction away. The consequence is
that an old section can go stale with no marker, so the draft banner requires reading the
whole section before promoting it to `2. wiki/`.

This module makes no API calls and draws no conclusions of its own. It only formats and
appends.

`essential_draft_block()` formats one round of essential questions into a draft block; the
heading comes from the `purpose` string, so each engine is free to have its own question
set. `needs_essential()` answers "has this file already been synthesized?" purely from
whether a draft exists, used by the `--new` mode in corpus.py and vcorpus.py.

    py -3.13 synthlog.py        # self-test
"""
import datetime
import os
import re

TRANSIT_DIR = os.path.join("tmp", "retrieval-packets")
DRAFT_DIR = os.path.join("2. wiki", "_terra-drafts")


def slugify(name):
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem[:80] or "document"


def stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def append_block(path, header, block):
    """Add `block` to `path`; write `header` first if the file doesn't exist yet.
    Never touches content already written. -> True if the file was just created."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fresh = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if fresh:
            fh.write("\n".join(header).rstrip() + "\n")
        fh.write("\n" + "\n".join(block).rstrip() + "\n")
    return fresh


def transit_path(vault, name):
    return os.path.join(vault, TRANSIT_DIR, f"{slugify(name)}.md")


def draft_path(vault, name):
    return os.path.join(vault, DRAFT_DIR, f"{slugify(name)} (terra-draft).md")


def transit_header(name, method, extra=()):
    return [
        "---",
        "type: retrieval-packet",
        "status: bukti-mentah",
        f'source: "1. raw/{name}"',
        f'method: "{method}"',
    ] + list(extra) + [
        "---",
        "",
        f"# Retrieval transit - {name}",
        "",
        "Raw Q&A log, append-only. Not a wiki synthesis, not verified evidence.",
        "New entries are appended below; old entries are never overwritten so the audit trail stays intact.",
    ]


def draft_header(name, method):
    today = datetime.date.today().isoformat()
    return [
        "---",
        "type: hipotesis",
        f'source-refs: ["1. raw/{name}"]',
        "confidence: Guessing",
        f"updated: {today}",
        "status: terra-draft-unreviewed",
        f'method: "{method}"',
        "---",
        "",
        f"# {os.path.splitext(name)[0]} (draft)",
        "",
        "> **DRAFT - NOT YET REVIEWED.** Written by machine with no review agent. Don't use it",
        "> as fact before verifying it against the source in `1. raw/`.",
        ">",
        "> **This note grows append-only.** Every following `ask-file` or `ask-essential` adds",
        "> a dated section below without touching the old ones. Before promotion: read ALL",
        "> sections including the earliest, cross-check against the latest findings, reconcile",
        "> anything contradictory, then set confidence per claim. An old section can be stale",
        "> with no marker at all.",
        "",
        "## Gap backlog",
        "",
        "| gap | type | status | follow-up |",
        "|---|---|---|---|",
        "| whole section not yet verified against the source | verification-gap | open | check the locator, reconcile across sections, then promote |",
    ]


def qa_block(label, answers):
    """answers: [(qid, purpose, query, answer)] -> a dated markdown block."""
    out = [f"## {stamp()} - {label}", ""]
    for qid, purpose, query, answer in answers:
        out += [
            f"### {qid} - {purpose}",
            "",
            f"Query: {query}",
            "",
            "Answer:",
            "",
            str(answer).strip(),
            "",
        ]
    return out


def essential_draft_block(answers, label="Essential"):
    """Structured draft from one round of essential questions.

    Each section's heading comes from the `purpose` string, not the QID, so this module
    doesn't need to know any engine's question set. An engine is free to change, add, or
    drop queries without touching the formatter.

    A section whose `purpose` starts with "Negative test" gets one annotation line: that
    query is bait, and a long answer is a fabrication signal, not document content.
    Without the annotation, a draft reader could misread it as a real finding.
    """
    out = [f"## {stamp()} - {label}", ""]
    for _qid, purpose, query, answer in answers:
        out += [f"### {purpose}", ""]
        if str(purpose).startswith("Negative test"):
            # NOTE: "_Query umpan; ... sinyal fabrikasi:_" is a protocol token kept for
            # compatibility: promote-terra.py's _is_bait_line() and the per-vault templates
            # match it literally. Do not translate it.
            out += [f"_Query umpan; jawaban panjang = sinyal fabrikasi:_ {query}", ""]
        out += [str(answer).strip(), ""]
    return out


def needs_essential(vault, name):
    """True if `name` has no draft file at all yet.

    Used by the `--new` mode of both engines. Stateless: no tracking file, just whether a
    draft exists. The consequence is that a file whose draft already exists but whose
    `1. raw/` content changed later won't be detected; the workaround is to name that file
    explicitly.
    """
    return not os.path.exists(draft_path(vault, name))


def record(vault, name, method, answers, label, draft_block, transit_extra=()):
    """Write transit + draft at once. -> (transit_path, draft_path)."""
    t = transit_path(vault, name)
    append_block(t, transit_header(name, method, transit_extra), qa_block(label, answers))
    d = draft_path(vault, name)
    append_block(d, draft_header(name, method), draft_block)
    return t, d


def _selftest():
    import tempfile

    assert slugify("My Report (Final).pdf") == "my-report-final"
    assert slugify("A.PDF") == slugify("a.pdf"), "slug is stable across casing"
    assert slugify("???.pdf") == "document", "a name with no alnum still gets a slug"

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "sub", "x.md")
        assert append_block(p, ["HEADER"], ["one"]) is True, "new file -> True"
        assert append_block(p, ["HEADER"], ["two"]) is False, "existing file -> False"
        txt = open(p, encoding="utf-8").read()
        assert txt.count("HEADER") == 1, "header written only once"
        assert "one" in txt and "two" in txt, "both blocks present"
        assert txt.index("one") < txt.index("two"), "chronological order preserved"

        answers = [("Q1", "Structure", "What's the structure?", "Three chapters.")]
        t, d = record(td, "test file.pdf", "corpus.py (PageIndex)", answers, "Essential",
                      ["## draft block", "", "draft content", ""])
        assert t == os.path.join(td, TRANSIT_DIR, "test-file.md"), t
        assert d == os.path.join(td, DRAFT_DIR, "test-file (terra-draft).md"), d
        tt = open(t, encoding="utf-8").read()
        assert "type: retrieval-packet" in tt and "Three chapters." in tt
        dd = open(d, encoding="utf-8").read()
        # loop_check gates: PROV needs source-refs filled in, GAP needs the gap backlog table
        assert 'source-refs: ["1. raw/test file.pdf"]' in dd, "PROV gate"
        assert "## Gap backlog" in dd, "GAP gate"
        assert "read ALL" in dd, "reconciliation warning must be present"
        assert "status: terra-draft-unreviewed" in dd

        # a second ask appends, doesn't overwrite
        record(td, "test file.pdf", "corpus.py (PageIndex)",
               [("Q", "Loose question", "Who's the author?", "Not stated yet.")],
               "Loose question", ["## second block", "", "second content", ""])
        dd2 = open(d, encoding="utf-8").read()
        assert "draft content" in dd2 and "second content" in dd2, "second append doesn't drop the first"
        assert dd2.count("status: terra-draft-unreviewed") == 1, "front-matter stays single"

    # --- essential_draft_block: heading from `purpose`, not from QID ---
    ans = [
        ("Q1", "Scope & subject", "What's the scope?", "Chapter I covers the scope."),
        ("Q9", "Negative test (bait)", "Grapes on Mars?", "Not discussed."),
        ("Q10", "Gap", "What's left unanswered?", "The rate isn't stated."),
    ]
    blk = essential_draft_block(ans)
    assert blk[0].endswith("- Essential"), blk[0]
    assert "### Scope & subject" in blk, "heading taken from purpose"
    assert "### Negative test (bait)" in blk, "canary still gets a heading"
    assert "### Gap" in blk
    assert "Chapter I covers the scope." in blk, "answer is included"
    bait = [ln for ln in blk if "Query umpan" in ln]
    assert len(bait) == 1, f"canary annotation exactly once, got {len(bait)}"
    assert "Grapes on Mars?" in bait[0], "annotation includes the bait query"
    assert blk.index("### Scope & subject") < blk.index("### Gap"), "order preserved"
    assert essential_draft_block(ans, label="Essential Q1-Q8")[0].endswith("- Essential Q1-Q8"), "label can be overridden"

    # --- needs_essential: stateless, purely from whether the draft file exists ---
    with tempfile.TemporaryDirectory() as td3:
        assert needs_essential(td3, "none.md") is True, "no draft -> needs synthesis"
        append_block(draft_path(td3, "none.md"), ["H"], ["content"])
        assert needs_essential(td3, "none.md") is False, "draft exists -> skip"
        assert needs_essential(td3, "NONE.MD") is False, "slug stable across casing"

    print("OK synthlog selftest")


if __name__ == "__main__":
    _selftest()
