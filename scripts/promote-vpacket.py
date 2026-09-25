#!/usr/bin/env python3
"""promote-vpacket — package a vcorpus evidence packet into a `2. wiki` note draft skeleton.

Mechanical, no API and no LLM: this script does NOT draw conclusions, does not
paraphrase, and does not judge evidence. It copies passages verbatim from the packet,
drops anything below threshold, drops duplicates, then writes a front-matter'd skeleton
to `2. wiki/_packet-drafts/`. Claims, `confidence`, `[[wikilink]]`, and the coverage
check remain human work (README Stage 6, the five conditions for a finished note).

The vector-path counterpart to `corpus.py`'s `promote-packet`. Its input is an evidence
packet from `rag.ps1 synth` (cross-document questions), not the per-file draft written
by `ask-file` or `ask-essential` -- that draft is already note-shaped and is promoted
manually.

Usage:
    py -3.13 promote-vpacket.py "tmp\\retrieval-packets\\01-literature.md"
    py -3.13 promote-vpacket.py <packet> --vault "C:\\...\\Projects\\policy-research"
    py -3.13 promote-vpacket.py --self-test
"""
import datetime
import os
import re
import sys

WEAK = 0.55  # mirrors retrieval/vector_store.py: below this it isn't evidence
DRAFT_DIR = os.path.join("2. wiki", "_packet-drafts")

# "[0.812 strong] filename.pdf p3" -> score, band, ref.
# ref (source + locator) is deliberately NOT split further: file names and headings can
# both contain spaces, so splitting them would be a guess. Leave that to the human.
HIT_RE = re.compile(r"^\[(\d\.\d+) (strong|weak|none)\] (.+?)\s*$")
CONT_RE = re.compile(r"^\s+(match|parent(?: \[\d+ ch\])?): (.*)$")
QBLOCK_RE = re.compile(r"^## Q(\d+)\. (.+?)$", re.M)


def _slugify(name):
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem[:80] or "packet"


def parse_frontmatter(text):
    """Flat `key: value` front-matter written by ask-batch.ps1. -> (meta, body)."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        sys.exit("packet has no YAML front-matter at the start of the file.")
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end():]


def parse_blocks(body):
    """-> [{'n', 'question', 'hits': [{'score','band','ref','match','parent'}], 'needs_source': bool}]"""
    marks = list(QBLOCK_RE.finditer(body))
    blocks = []
    for i, m in enumerate(marks):
        chunk = body[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        hits, seen, cur = [], set(), None
        for line in chunk.splitlines():
            hm = HIT_RE.match(line)
            if hm:
                score, band, ref = float(hm.group(1)), hm.group(2), hm.group(3)
                cur = None
                if score < WEAK or ref in seen:   # below threshold or a duplicate
                    continue
                seen.add(ref)
                cur = {"score": score, "band": band, "ref": ref, "match": "", "parent": ""}
                hits.append(cur)
                continue
            cm = CONT_RE.match(line)
            if cm and cur is not None:
                key = "parent" if cm.group(1).startswith("parent") else "match"
                cur[key] = cm.group(2).strip()
        blocks.append({
            "n": int(m.group(1)),
            "question": m.group(2).strip(),
            "hits": hits,
            "needs_source": "[NEEDS SOURCE]" in chunk,
        })
    return blocks


def render(meta, blocks, title, packet_rel):
    today = datetime.date.today().isoformat()
    refs = {}   # ref -> (best band, [Q numbers])
    for b in blocks:
        for h in b["hits"]:
            best, qs = refs.get(h["ref"], ("none", []))
            rank = {"strong": 2, "weak": 1, "none": 0}
            refs[h["ref"]] = (h["band"] if rank[h["band"]] > rank[best] else best, qs + [b["n"]])

    out = [
        "---",
        "type: hipotesis",
        "source-refs: []   # fill in manually from ## Candidate source-refs",
        "confidence: Guessing",
        "method: vcorpus.py",
        f"updated: {today}",
        "status: vpacket-draft-unreviewed",
        f'source-packet: "{packet_rel}"',
        f'generated-from-packet: {meta.get("generated", "")}',
        "---",
        "",
        f"# {title} (vpacket draft)",
        "",
        "> **VPACKET DRAFT - NOT YET REVIEWED.** What follows is verbatim retrieval passages,",
        "> not claims. The script draws no conclusions of its own. This note does not meet the",
        "> five conditions in README Stage 6 until claims are written, locators are checked, and",
        "> coverage is assessed by a human.",
        "",
        # AI-RULES 6a: an empty source-refs must be paired with a bare marker in the note body.
        "[NEEDS SOURCE] — `source-refs` is still empty. Candidates are in the table below, but",
        "they haven't been verified into final refs yet, so they can't be used as claim provenance.",
        "",
        "## Review checklist",
        "",
        "- [ ] Each claim is rewritten from a passage you've actually read, not copied from `match:`.",
        "- [ ] Final `source-refs` filled in from `## Candidate source-refs`, locators specific enough.",
        "- [ ] `type` and `confidence` set to the strength of the evidence, not the raw score.",
        "- [ ] There's a `[[wikilink]]` to another note.",
        "- [ ] Coverage checked; any untouched main idea is flagged `[COVERAGE?]` and logged in the gap backlog.",
        "",
    ]

    for b in blocks:
        out += [f"## Q{b['n']}. {b['question']}", "", "### Claim", "", "<!-- write the claim here -->", "", "### Evidence", ""]
        if b["needs_source"]:
            out += ["`[NEEDS SOURCE]` — top score below threshold; don't answer from this packet.", ""]
        if not b["hits"]:
            out += [f"No passage >= {WEAK}. Log it in `## Gap backlog`.", ""]
        for h in b["hits"]:
            out.append(f"- **[{h['score']:.3f} {h['band']}]** `{h['ref']}`")
            if h["match"]:
                out.append(f"  > match: {h['match']}")
            if h["parent"]:
                out.append(f"  > parent: {h['parent']}")
            out.append("")

    out += ["## Candidate source-refs", "", "| ref (source + locator, verbatim) | best band | appears in |", "|---|---|---|"]
    for ref, (band, qs) in sorted(refs.items()):
        out.append(f"| `{ref}` | {band} | {', '.join(f'Q{n}' for n in sorted(set(qs)))} |")
    if not refs:
        out.append("| (empty) | — | — |")

    out += [
        "",
        "## Links",
        "",
        "<!-- [[related note]] -->",
        "",
        "## Gap backlog",
        "",
        "| gap | type | status | follow-up |",
        "|---|---|---|---|",
    ]
    for b in blocks:
        if b["needs_source"] or not b["hits"]:
            q = " ".join(b["question"].split()).replace("|", "/")[:200]
            out.append(f"| {q} | source-gap | open | find a source, ingest it, re-ask |")
    out.append("")
    return "\n".join(out)


def find_vault(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, "2. wiki")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            sys.exit("could not find the vault root (a folder containing '2. wiki'). Use --vault.")
        d = parent


def promote(packet, vault=None):
    packet = os.path.abspath(packet)
    if not os.path.isfile(packet):
        sys.exit(f"packet not found: {packet}")
    text = open(packet, encoding="utf-8").read()
    meta, body = parse_frontmatter(text)
    if meta.get("type") != "retrieval-packet":
        sys.exit(f"not a retrieval-packet (type: {meta.get('type')}).")
    if "vcorpus.py" not in meta.get("method", ""):
        sys.exit(f"this packet is a different path (method: {meta.get('method')}). Use promote-packet for corpus.py.")

    blocks = parse_blocks(body)
    if not blocks:
        sys.exit("no '## Qn.' blocks in the packet.")

    vault = os.path.abspath(vault) if vault else find_vault(os.path.dirname(packet))
    title = next((l[2:].strip() for l in body.splitlines() if l.startswith("# ")), _slugify(packet))
    draft_dir = os.path.join(vault, DRAFT_DIR)
    os.makedirs(draft_dir, exist_ok=True)
    out_path = os.path.join(draft_dir, f"{_slugify(packet)} (vpacket-draft).md")
    packet_rel = os.path.relpath(packet, vault).replace("\\", "/")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(render(meta, blocks, title, packet_rel))

    kept = sum(len(b["hits"]) for b in blocks)
    print(f"draft written: {out_path}")
    print(f"  {len(blocks)} questions, {kept} passages passed the {WEAK} threshold.")
    print("  NOT a wiki note yet. Write the claims, fill in source-refs, check coverage first.")


SAMPLE = """---
type: retrieval-packet
status: bukti-mentah
vault: test
method: vcorpus.py (local vector, small-to-big)
generated: 2026-09-02
---

# Test packet

## Q1. What are the main findings?

```text
[0.812 strong] annual-report.pdf p12
  match: finding A appears in table 3.
  parent [540 ch]: full section context.

[0.700 strong] annual-report.pdf p12
  match: duplicate ref, must be dropped.

[0.400 none] other-file.md ## Chapter 2
  match: below threshold, must be dropped.
```

## Q2. Question with no source?

```text
[NEEDS SOURCE] top score 0.310 < 0.55 -- no chunk relevant enough; don't answer from here.
```
"""


def _selftest():
    meta, body = parse_frontmatter(SAMPLE)
    assert meta["type"] == "retrieval-packet", meta
    assert "vcorpus.py" in meta["method"], meta
    blocks = parse_blocks(body)
    assert len(blocks) == 2, blocks
    assert len(blocks[0]["hits"]) == 1, blocks[0]["hits"]          # duplicate + below threshold dropped
    assert blocks[0]["hits"][0]["ref"] == "annual-report.pdf p12"
    assert blocks[0]["hits"][0]["parent"].startswith("full section"), blocks[0]["hits"][0]
    assert blocks[1]["hits"] == [] and blocks[1]["needs_source"], blocks[1]
    out = render(meta, blocks, "Test packet", "tmp/retrieval-packets/test.md")
    assert "source-refs: []" in out and "vpacket-draft-unreviewed" in out
    assert "| `annual-report.pdf p12` | strong | Q1 |" in out, out
    assert "| Question with no source? | source-gap |" in out, out
    # AI-RULES 6a: empty source-refs -> bare marker required, and loop_check's GAP gate
    # demands a `## Gap backlog` in the same note.
    assert "\n[NEEDS SOURCE] — `source-refs` is still empty." in out, out
    assert "## Gap backlog" in out, out
    assert _slugify("01 - Tax Holiday Literature.md") == "01-tax-holiday-literature"
    print("OK promote-vpacket selftest")


def main():
    args = [a for a in sys.argv[1:]]
    if not args or "--self-test" in args:
        return _selftest() if args else sys.exit(__doc__.strip())
    vault = None
    if "--vault" in args:
        i = args.index("--vault")
        vault = args[i + 1] if i + 1 < len(args) else sys.exit("--vault needs a path.")
        del args[i:i + 2]
    promote(args[0], vault)


if __name__ == "__main__":
    main()
