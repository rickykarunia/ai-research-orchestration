#!/usr/bin/env python3
"""tally — score routing eval results.

Read a results file formatted `id | picked-vault | correct|wrong | note`, one per line,
between <!-- data --> and <!-- /data -->. Print accuracy per group (E, H, N).

Usage: python tally.py routing-results-2026-08-15.md
       python tally.py --self-test
"""
import sys
import os
import tempfile
import shutil


def parse(path):
    rows = []
    inside = False
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            s = ln.strip()
            if s == "<!-- data -->":
                inside = True
                continue
            if s == "<!-- /data -->":
                break
            if not inside or "|" not in s:
                continue
            parts = [p.strip() for p in s.split("|")]
            if len(parts) < 3 or not parts[0]:
                continue
            rows.append({"id": parts[0], "picked": parts[1],
                         "verdict": parts[2].lower()})
    return rows


def score(rows):
    groups = {}
    for r in rows:
        g = r["id"][0].upper()
        hit, total = groups.get(g, (0, 0))
        groups[g] = (hit + (1 if r["verdict"] == "correct" else 0), total + 1)
    return groups


def self_test():
    tmp = tempfile.mkdtemp(prefix="tally-")
    try:
        fp = os.path.join(tmp, "results.md")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write("title\n<!-- data -->\n"
                     "E1 | policy-research | correct | -\n"
                     "E2 | policy-research | wrong | should be audit-qa\n"
                     "H1 | ai-pilot | correct | -\n"
                     "<!-- /data -->\ntail\n")
        rows = parse(fp)
        assert len(rows) == 3, rows
        g = score(rows)
        assert g["E"] == (1, 2), g
        assert g["H"] == (1, 1), g
        print("self-test passed: 2 cases")
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
    if len(sys.argv) < 2:
        print("usage: python tally.py <results-file.md>")
        return 2
    rows = parse(sys.argv[1])
    if not rows:
        print("no data rows found. Make sure there is a <!-- data --> ... <!-- /data --> block")
        return 2
    names = {"E": "easy", "H": "overlapping", "N": "negative"}
    for g, (hit, total) in sorted(score(rows).items()):
        print("{:10s} {}/{} = {:.0%}".format(names.get(g, g), hit, total, hit / total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
