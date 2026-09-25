#!/usr/bin/env python3
"""review-draft — LLM assistant that finds contradictions across terra draft entries.

Read one draft `2. wiki/_terra-drafts/<slug> (terra-draft).md`, send each dated entry's
content to Terra, ask it to flag pairs of entries whose claims look contradictory.
The result is APPENDED to the same draft as one clearly labeled new entry.

This is an ASSISTANT, not a verdict. Terra only compares entries against other entries in
the same draft here -- it does NOT check back against `1. raw/` and has no way to know which
claim is actually correct. A manual re-read of the whole draft is still required before
promotion to `2. wiki/`. If the report says "no contradiction found", that's not a
guarantee; it only means Terra found nothing glaring from the draft content alone.

Usage:
    py -3.13 review-draft.py "<vault_dir>" "<source-name>"
    py -3.13 review-draft.py --self-test
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "retrieval"))
import synthlog  # noqa: E402

CHAT_MODEL = "gpt-5.6-terra"

# Entry headers written by synthlog.qa_block / draft blocks: "## <ISO timestamp> - <label>".
# "## Gap backlog" (static, written once by draft_header) doesn't match this pattern and is
# automatically skipped. Entries from a previous review ALSO match the timestamp pattern --
# they must be excluded explicitly below so they don't get compared against themselves again.
ENTRY_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}) - (.+)$", re.M
)
REVIEW_LABEL = "Consistency review"


def parse_entries(text):
    """-> [{'timestamp','title','body'}], with old review blocks excluded."""
    marks = list(ENTRY_RE.finditer(text))
    entries = []
    for i, m in enumerate(marks):
        title = m.group(2).strip()
        if title.startswith(REVIEW_LABEL):
            continue
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        entries.append({"timestamp": m.group(1), "title": title, "body": text[start:end].strip()})
    return entries


def ask_terra(entries):
    from openai import OpenAI
    listing = "\n\n---\n\n".join(
        f"[Entry {i + 1} - {e['timestamp']} - {e['title']}]\n{e['body']}"
        for i, e in enumerate(entries)
    )
    sys_msg = (
        "You are comparing the entries below. All of them come from a synthesis draft of the "
        "SAME source document, written at different times. Your ONLY task is to flag pairs of "
        "entries whose claims appear to contradict or be inconsistent with each other.\n\n"
        "For each candidate contradiction: name the conflicting entry numbers, quote the "
        "conflicting part from EACH entry verbatim (do not paraphrase), then briefly explain "
        "why it looks contradictory.\n\n"
        "Do not check against the original source -- you have no access to it here. Do not "
        "conclude which claim is correct; that's a human decision. If there is no glaring "
        "contradiction, write EXACTLY this sentence and nothing else: "
        "'No contradiction detected among the entries at this time.'"
    )
    resp = OpenAI().chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": listing}],
    )
    return resp.choices[0].message.content


def review(vault, name):
    path = synthlog.draft_path(vault, name)
    if not os.path.exists(path):
        sys.exit(f"draft not found: {path}\nrun ask-file or ask-essential first.")
    text = open(path, encoding="utf-8").read()
    entries = parse_entries(text)
    if len(entries) < 2:
        print(f"{len(entries)} content entries -- no pair to compare, skipping.")
        return
    print(f"comparing {len(entries)} entries with {CHAT_MODEL} ...", flush=True)
    report = ask_terra(entries)
    print(report)
    block = [
        f"## {synthlog.stamp()} - {REVIEW_LABEL} (LLM assistant, not a final verification)",
        "",
        f"Compared {len(entries)} content entries in this draft. Terra does not check against "
        "`1. raw/` and does not decide which claim is correct -- this is a reading pointer, "
        "not a verification.",
        "",
        report.strip(),
        "",
    ]
    synthlog.append_block(path, [], block)
    print(f"\nappended to: {path}")


def _selftest():
    sample = (
        "---\nfront matter\n---\n\n# Title\n\n"
        "## 2026-09-03T10:00:00+07:00 - Loose question\n\nfirst content\n\n"
        "## Gap backlog\n\n| a | b |\n\n"
        f"## 2026-09-03T11:00:00+07:00 - {REVIEW_LABEL} (LLM assistant, not a final verification)\n\n"
        "old report\n\n"
        "## 2026-09-03T12:00:00+07:00 - Essential Q1-Q8\n\nsecond content\n"
    )
    entries = parse_entries(sample)
    assert len(entries) == 2, entries  # Gap backlog and old review excluded
    assert entries[0]["title"] == "Loose question", entries
    assert entries[1]["title"] == "Essential Q1-Q8", entries
    assert "first content" in entries[0]["body"] and "second content" not in entries[0]["body"]
    assert "second content" in entries[1]["body"]
    assert parse_entries("## Gap backlog\n\nx\n") == [], "static header only -> empty"
    print("OK review-draft selftest")


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--self-test":
        return _selftest()
    if len(args) < 2:
        sys.exit('usage: review-draft.py "<vault_dir>" "<source-name>"')
    review(args[0], args[1])


if __name__ == "__main__":
    main()
