#!/usr/bin/env python3
"""loop_check — check health of the raw/wiki/output loop and registry freshness.

Four checks, one report:
  RATCHET  — raw newer than wiki, wiki too thin, or output ahead of wiki.
  STALE    — AI-INDEX.md older than any routing front-matter.
  PROV     — a substantive `2. wiki` note without a `source-refs` front-matter field.
  GAP      — open [NEEDS SOURCE]/[COVERAGE?] markers with no `## Gap backlog` section.

This script is read-only. It never writes, moves, or deletes anything.
Exit 0 when clean, 1 when there are findings.

Usage:
    python loop_check.py                  # all vaults with loop: true
    python loop_check.py --vault audit-qa # a single vault
    python loop_check.py --self-test      # test the logic in a temp folder
"""
import os
import sys
import datetime
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index_sync  # noqa: E402  (needs the sys.path entry above)

HOME = os.path.expanduser("~")

# Threshold. Derived from a 2026-08-15 inventory, not a round number picked at random.
# supply-chain-audit 6 wiki / 60 raw = 0.10 -> must trip.
# policy-research 36 wiki / 58 raw = 0.62 -> must pass.
MIN_WIKI_RATIO = 0.25
# Hour tolerance for mtime; file copies and cloud sync can shift it slightly.
MTIME_SLACK_H = 24


def _md_files(folder):
    """All .md files in a folder, recursive. Empty list if the folder doesn't exist."""
    out = []
    if not os.path.isdir(folder):
        return out
    for dirpath, _dirs, files in os.walk(folder):
        for name in files:
            if name.lower().endswith(".md"):
                out.append(os.path.join(dirpath, name))
    return out


def _wiki_notes(folder):
    """Substantive wiki notes; skip internal working files/dirs starting with '_'."""
    out = []
    root = os.path.abspath(folder)
    for p in _md_files(folder):
        rel = os.path.relpath(p, root)
        parts = rel.split(os.sep)
        if any(part.startswith("_") for part in parts):
            continue
        out.append(p)
    return out


def _newest(paths):
    """(mtime epoch, basename) of the newest file. (0.0, None) if empty."""
    best = (0.0, None)
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > best[0]:
            best = (m, os.path.basename(p))
    return best


def _hours(delta_seconds):
    return delta_seconds / 3600.0


def _vault_dir(row, home):
    return os.path.join(home, row.get("path", "").replace("/", os.sep))


def check_ratchet(row, home):
    """Ratchet-rule violations per AI-RULES §6. Only for vaults with loop: true."""
    findings = []
    if row.get("loop") != "true":
        return findings
    base = _vault_dir(row, home)
    raw = _md_files(os.path.join(base, "1. raw"))
    wiki = _md_files(os.path.join(base, "2. wiki"))
    out = _md_files(os.path.join(base, "3. output"))

    if not raw and not wiki:
        findings.append("no loop structure found (neither 1. raw nor 2. wiki)")
        return findings

    raw_m, raw_name = _newest(raw)
    wiki_m, _ = _newest(wiki)
    out_m, out_name = _newest(out)

    if raw_m and wiki_m and _hours(raw_m - wiki_m) > MTIME_SLACK_H:
        findings.append(
            "raw is {:.0f}h newer than wiki (newest: {}) — synthesis is lagging".format(
                _hours(raw_m - wiki_m), raw_name))
    if raw and len(wiki) < len(raw) * MIN_WIKI_RATIO:
        findings.append(
            "wiki too thin: {} wiki / {} raw = {:.2f} (threshold {:.2f})".format(
                len(wiki), len(raw), len(wiki) / len(raw), MIN_WIKI_RATIO))
    if out_m and wiki_m and _hours(out_m - wiki_m) > MTIME_SLACK_H:
        findings.append(
            "output is {:.0f}h newer than wiki (newest: {}) — return leg not written yet".format(
                _hours(out_m - wiki_m), out_name))
    return findings


def check_provenance(row, home):
    """Substantive wiki note without a `source-refs:` front-matter field. See AI-RULES §6."""
    findings = []
    if row.get("loop") != "true":
        return findings
    wiki = _wiki_notes(os.path.join(_vault_dir(row, home), "2. wiki"))
    if not wiki:
        return findings
    missing = []
    for p in wiki:
        try:
            with open(p, encoding="utf-8") as fh:
                head = fh.read(2048)
        except (OSError, UnicodeDecodeError):
            continue
        if "source-refs:" not in head:
            missing.append(os.path.basename(p))
    if missing:
        findings.append("{}/{} wiki notes without `source-refs` (e.g. {})".format(
            len(missing), len(wiki), ", ".join(sorted(missing)[:3])))
    return findings


GAP_MARKERS = ("[NEEDS SOURCE]", "[COVERAGE?]")


def _has_open_marker(text):
    """A BARE gap marker (on a claim line) = an open gap. A backtick-quoted mention
    (`[NEEDS SOURCE]`, in prose explaining the convention) does not count.
    # ponytail: backtick heuristic, not a full Markdown parser. Good enough as long as
    # real gaps are written bare and documentary mentions stay backtick-wrapped — the
    # corpus's current convention."""
    t = text
    for m in GAP_MARKERS:
        t = t.replace("`" + m + "`", "")
    return any(m in t for m in GAP_MARKERS)


def check_gap(row, home):
    """Gaps must leave a trace. A [NEEDS SOURCE]/[COVERAGE?] marker in `2. wiki` or
    `3. output` requires a `## Gap backlog` section in `2. wiki` (see loop-engine's
    'Gap cycle'). This enforces that every gap ends up either closed or logged, never
    silently dropped."""
    findings = []
    if row.get("loop") != "true":
        return findings
    base = _vault_dir(row, home)
    wiki = _md_files(os.path.join(base, "2. wiki"))
    out = _md_files(os.path.join(base, "3. output"))
    has_marker, has_backlog = False, False
    for p in wiki + out:
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        if _has_open_marker(text):
            has_marker = True
        if p in wiki and "## Gap backlog" in text:
            has_backlog = True
    if has_marker and not has_backlog:
        findings.append("gap marker ([NEEDS SOURCE]/[COVERAGE?]) present but no "
                        "`## Gap backlog` section in 2. wiki — gap not tracked")
    return findings


def check_stale(rows, home):
    """AI-INDEX.md older than any rules file carrying a routing block."""
    findings = []
    idx = os.path.join(home, "AI-INDEX.md")
    if not os.path.exists(idx):
        return ["AI-INDEX.md not found — run index_sync.py"]
    idx_m = os.path.getmtime(idx)
    for row in rows:
        base = _vault_dir(row, home)
        for name in ("AGENTS.md", "CLAUDE.md"):
            fp = os.path.join(base, name)
            if not os.path.exists(fp):
                continue
            if _hours(os.path.getmtime(fp) - idx_m) > MTIME_SLACK_H:
                findings.append("{}/{} is newer than AI-INDEX.md — regen the registry".format(
                    row.get("vault"), name))
    return findings


def report(rows, home, only=None):
    """Print the report. Return the number of flagged vaults."""
    flagged = 0
    stale = check_stale(rows, home)
    if stale:
        print("STALE")
        for s in stale:
            print("  - " + s)
        print("")
        flagged += 1
    for row in sorted(rows, key=lambda r: r.get("vault", "")):
        if only and row.get("vault") != only:
            continue
        found = check_ratchet(row, home) + check_provenance(row, home) + check_gap(row, home)
        if not found:
            continue
        flagged += 1
        print("{} ({})".format(row.get("vault"), row.get("path")))
        for f in found:
            print("  - " + f)
        print("")
    if not flagged:
        print("clean: no findings across {} vaults".format(len(rows)))
    return flagged


def self_test():
    """Build fake vaults in a temp folder, make sure every check fires."""
    tmp = tempfile.mkdtemp(prefix="loopcheck-")
    try:
        vault = os.path.join(tmp, "Projects", "test")
        for sub in ("1. raw", "2. wiki", "3. output"):
            os.makedirs(os.path.join(vault, sub))
        row = {"vault": "test", "path": "Projects/test", "loop": "true", "tier": "active"}

        # 1. thin wiki: 5 raw, 1 wiki -> ratio 0.2 < 0.25
        for i in range(5):
            with open(os.path.join(vault, "1. raw", "r%d.md" % i), "w", encoding="utf-8") as fh:
                fh.write("raw")
        with open(os.path.join(vault, "2. wiki", "w0.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nsource-refs: [1. raw/r0.md]\n---\nwiki")
        found = check_ratchet(row, tmp)
        assert any("too thin" in f for f in found), found

        # 2. raw newer than wiki
        old = datetime.datetime(2020, 1, 1).timestamp()
        os.utime(os.path.join(vault, "2. wiki", "w0.md"), (old, old))
        found = check_ratchet(row, tmp)
        assert any("newer than wiki" in f for f in found), found

        # 3. provenance: add a note without source-refs
        with open(os.path.join(vault, "2. wiki", "w1.md"), "w", encoding="utf-8") as fh:
            fh.write("no front-matter")
        found = check_provenance(row, tmp)
        assert any("without `source-refs`" in f for f in found), found

        # 4. clean case: healthy ratio, wiki fresh, all have source-refs
        vault2 = os.path.join(tmp, "Projects", "clean")
        for sub in ("1. raw", "2. wiki", "3. output"):
            os.makedirs(os.path.join(vault2, sub))
        row2 = {"vault": "clean", "path": "Projects/clean", "loop": "true", "tier": "active"}
        with open(os.path.join(vault2, "1. raw", "r0.md"), "w", encoding="utf-8") as fh:
            fh.write("raw")
        os.utime(os.path.join(vault2, "1. raw", "r0.md"), (old, old))
        for i in range(2):
            with open(os.path.join(vault2, "2. wiki", "w%d.md" % i), "w", encoding="utf-8") as fh:
                fh.write("---\nsource-refs: [1. raw/r0.md]\n---\nwiki")
        with open(os.path.join(vault2, "2. wiki", "_C2 Log.md"), "w", encoding="utf-8") as fh:
            fh.write("# C2 Log\n\n## 2026-09-09 10:00\n\nhandoff")
        os.makedirs(os.path.join(vault2, "2. wiki", "_terra-drafts"))
        with open(os.path.join(vault2, "2. wiki", "_terra-drafts", "wip.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("draft not yet final wiki")
        assert check_ratchet(row2, tmp) == [], check_ratchet(row2, tmp)
        assert check_provenance(row2, tmp) == [], check_provenance(row2, tmp)

        # 5. output newer than wiki: raw & wiki old, output fresh (>24h)
        #    -> return leg not written. Separate fixture so it doesn't clash
        #    with the ratio/mtime setup of the other cases.
        vault3 = os.path.join(tmp, "Projects", "output-stale")
        for sub in ("1. raw", "2. wiki", "3. output"):
            os.makedirs(os.path.join(vault3, sub))
        row_out = {"vault": "output-stale", "path": "Projects/output-stale",
                   "loop": "true", "tier": "active"}
        with open(os.path.join(vault3, "1. raw", "r0.md"), "w", encoding="utf-8") as fh:
            fh.write("raw")
        os.utime(os.path.join(vault3, "1. raw", "r0.md"), (old, old))
        with open(os.path.join(vault3, "2. wiki", "w0.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nsource-refs: [1. raw/r0.md]\n---\nwiki")
        os.utime(os.path.join(vault3, "2. wiki", "w0.md"), (old, old))
        with open(os.path.join(vault3, "3. output", "o0.md"), "w", encoding="utf-8") as fh:
            fh.write("fresh output")  # default mtime = now, >> 24h from the old wiki
        found = check_ratchet(row_out, tmp)
        assert any("newer than wiki" in f for f in found), found

        # 6. non-loop vault is skipped: fixture is fresh & would trip on its own
        #    (thin ratio, stale wiki, no source-refs) so EVERY sub-check would fire
        #    if the `loop` guard were removed — not a fixture from another case that
        #    happens to be clean.
        vault4 = os.path.join(tmp, "Projects", "guard")
        for sub in ("1. raw", "2. wiki", "3. output"):
            os.makedirs(os.path.join(vault4, sub))
        row_guard = {"vault": "guard", "path": "Projects/guard",
                     "loop": "false", "tier": "active"}
        for i in range(5):
            with open(os.path.join(vault4, "1. raw", "r%d.md" % i), "w", encoding="utf-8") as fh:
                fh.write("raw")
        with open(os.path.join(vault4, "2. wiki", "w0.md"), "w", encoding="utf-8") as fh:
            fh.write("no front-matter")  # deliberately missing source-refs
        os.utime(os.path.join(vault4, "2. wiki", "w0.md"), (old, old))
        assert check_ratchet(row_guard, tmp) == [], check_ratchet(row_guard, tmp)
        assert check_provenance(row_guard, tmp) == [], check_provenance(row_guard, tmp)

        # 7. gap: [NEEDS SOURCE] marker in wiki without `## Gap backlog` -> fires;
        #    add a backlog -> clean. Non-loop guard is also checked.
        vault5 = os.path.join(tmp, "Projects", "gap")
        for sub in ("1. raw", "2. wiki", "3. output"):
            os.makedirs(os.path.join(vault5, sub))
        row_gap = {"vault": "gap", "path": "Projects/gap", "loop": "true", "tier": "active"}
        wpath = os.path.join(vault5, "2. wiki", "w0.md")
        with open(wpath, "w", encoding="utf-8") as fh:
            fh.write("---\nsource-refs: []\n---\nclaim [NEEDS SOURCE]")
        assert any("Gap backlog" in f for f in check_gap(row_gap, tmp)), check_gap(row_gap, tmp)
        with open(wpath, "a", encoding="utf-8") as fh:
            fh.write("\n## Gap backlog\n| gap | type | status | follow-up |\n")
        assert check_gap(row_gap, tmp) == [], check_gap(row_gap, tmp)
        row_gap_off = dict(row_gap, loop="false")
        assert check_gap(row_gap_off, tmp) == [], "non-loop must be skipped"
        # a backtick-quoted mention only (no bare gap, no backlog) -> does not fire
        with open(wpath, "w", encoding="utf-8") as fh:
            fh.write("---\nsource-refs: []\n---\nconvention example `[NEEDS SOURCE]` in prose")
        assert check_gap(row_gap, tmp) == [], "a backtick-quoted mention must not count"

        # 8. stale: AI-INDEX older than AGENTS.md
        with open(os.path.join(tmp, "AI-INDEX.md"), "w", encoding="utf-8") as fh:
            fh.write("idx")
        os.utime(os.path.join(tmp, "AI-INDEX.md"), (old, old))
        with open(os.path.join(vault, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write("rules")
        found = check_stale([row], tmp)
        assert any("is newer than AI-INDEX.md" in f for f in found), found

        print("self-test passed: 8 cases")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if "--self-test" in sys.argv:
        self_test()
        return 0
    only = None
    if "--vault" in sys.argv:
        only = sys.argv[sys.argv.index("--vault") + 1]
    rows = index_sync.harvest()
    rows = [r for r in rows if r.get("tier") == "active"]
    return 1 if report(rows, HOME, only) else 0


if __name__ == "__main__":
    sys.exit(main())
