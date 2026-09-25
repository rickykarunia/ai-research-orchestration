#!/usr/bin/env python3
"""index_sync — harvest each vault's routing front-matter, regen ~/AI-INDEX.md.

The registry is DERIVED. Source of truth = the routing block in each vault's
AGENTS.md/CLAUDE.md. Run it every time a project is added/retired/changed. No state
other than the source files.

Usage: python index_sync.py            # write ~/AI-INDEX.md
       python index_sync.py --dry      # print to stdout, don't write
"""
import os, sys, datetime

HOME = os.path.expanduser("~")
KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # abspath, not realpath: keeps junction paths
SCAN_ROOTS = [os.environ.get("AIO_PROJECTS", os.path.join(HOME, "Projects"))]
RULES_NAMES = ("AGENTS.md", "CLAUDE.md")
OUT = os.path.join(HOME, "AI-INDEX.md")
FIELDS = ("vault", "path", "domain", "route-when", "not-when", "depends-on",
          "entry", "tier", "loop", "rules", "skills")


def parse_frontmatter(text):
    """Grab the first YAML front-matter block if it carries a 'routing block' marker.
    Flat parser, no dependencies."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None
    body = []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            block = lines[1:i]
            break
        body.append(lines[i])
    else:
        return None
    joined = "\n".join(block)
    if "blok routing" not in joined:
        return None
    fm = {}
    for ln in block:
        ln = ln.strip()
        if not ln or ln.startswith("#") or ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        v = v.strip()
        if not v.startswith('"') and " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        fm[k.strip()] = v.strip('"')
    return fm if fm.get("vault") else None


def harvest():
    rows, seen = [], set()
    for root in SCAN_ROOTS:
        for dirpath, dirs, files in os.walk(root):
            # don't descend into derived/snapshot folders; the registry only harvests active rules
            dirs[:] = [d for d in dirs if d not in (
                "1. raw", "2. wiki", "3. output", "3. draft", "graphify-out",
                "codex-review-harness", "_backup-agents-20260814",
                "node_modules", ".git", ".obsidian")]
            for name in RULES_NAMES:
                if name not in files:
                    continue
                fp = os.path.join(dirpath, name)
                try:
                    with open(fp, encoding="utf-8") as fh:
                        fm = parse_frontmatter(fh.read())
                except (OSError, UnicodeDecodeError):
                    continue
                if not fm or fm["vault"] in seen:
                    continue
                seen.add(fm["vault"])
                rows.append(fm)
    return rows


DORMANT = os.path.join(KIT_ROOT, "dormant-registry.md")


def read_dormant(path=DORMANT):
    """Read `vault | path | tier | domain` rows between the <!-- data --> markers."""
    rows = []
    if not os.path.exists(path):
        return rows
    inside = False
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            s = ln.strip()
            if s == "<!-- data -->":
                inside = True
                continue
            if s == "<!-- /data -->":
                break
            if not inside or not s or "|" not in s:
                continue
            parts = [p.strip() for p in s.split("|")]
            if len(parts) < 4:
                continue
            rows.append({"vault": parts[0], "path": parts[1],
                         "tier": parts[2], "domain": parts[3]})
    return rows


def render(rows):
    order = {"active": 0, "dormant": 1, "archive": 2}
    rows.sort(key=lambda r: (order.get(r.get("tier", "archive"), 3),
                             0 if r.get("loop") == "true" else 1,
                             r.get("vault", "")))
    ts = datetime.date.today().isoformat()
    out = [
        "---", "title: AI-INDEX — cross-vault routing registry", "status: generated",
        f"generated: {ts}", "generator: index_sync.py",
        "authority: DERIVED from each vault's front-matter. Do not hand-edit; change it in "
        "the vault and regen.",
        "---", "",
        "# AI-INDEX — cross-vault routing registry", "",
        f"Harvested from each vault's routing block {ts}. Behavior rules: `~/AI-RULES.md`. "
        "How to use it (all harnesses): match the task against `route-when`, open `path`, "
        "start at `entry`. By default only consider tier `active`. Nothing matches: "
        "report it, don't guess from memory.", "",
    ]
    active = [r for r in rows if r.get("tier") == "active"]
    out += [f"**{len(active)} active vaults**, {len(rows) - len(active)} dormant/archive, "
            f"{len(rows)} registered total.", "",
            "| vault | domain | route-when | entry | loop |",
            "|---|---|---|---|---|"]
    for r in active:
        out.append("| `{vault}` | {domain} | {rw} | `{entry}` | {loop} |".format(
            vault=r.get("vault", ""), domain=r.get("domain", ""),
            rw=r.get("route-when", "").strip("[]"),
            entry=r.get("entry", ""), loop="🔁" if r.get("loop") == "true" else "—"))
    out += ["", "## Full path & skill bindings", ""]
    for r in active:
        sk = r.get("skills", "").strip("[]")
        sk = f" — skills: {sk}" if sk else ""
        out.append(f"- `{r.get('vault')}` → `{r.get('path')}` (rules: {r.get('rules','')}){sk}")
    dis = [r for r in active if r.get("not-when") or r.get("depends-on")]
    if dis:
        out += ["", "## Disambiguation & dependencies", "",
                "`not-when` = keywords that RULE OUT this vault even if `route-when` matches. "
                "`depends-on` = vaults that also need opening for cross-domain tasks.", "",
                "| vault | not-when | depends-on |", "|---|---|---|"]
        for r in dis:
            out.append("| `{v}` | {nw} | {dep} |".format(
                v=r.get("vault", ""),
                nw=r.get("not-when", "").strip("[]") or "—",
                dep=r.get("depends-on", "").strip("[]") or "—"))
    non_active = [r for r in rows if r.get("tier") != "active"]
    if non_active:
        out += ["", "## Dormant / archive", ""]
        for r in non_active:
            out.append(f"- `{r.get('vault')}` ({r.get('tier')}) — {r.get('domain','')}")
    out.append("")
    return "\n".join(out)


def main():
    rows = harvest()
    known = {r["vault"] for r in rows}
    rows += [r for r in read_dormant() if r["vault"] not in known]
    text = render(rows)
    if "--dry" in sys.argv:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # Windows console charmap fix
        except AttributeError:
            pass
        print(text)
        return
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {OUT}: {len(rows)} vaults ({sum(1 for r in rows if r.get('tier')=='active')} active)")


if __name__ == "__main__":
    main()
