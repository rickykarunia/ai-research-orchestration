#!/usr/bin/env python3
"""promote-terra — carry a draft from _terra-drafts/ over to a 2. wiki/ note.

TWO lanes both use the mechanical core `draft_to_note()`, no LLM: the draft's
`### <sub>` outline is kept as `## <sub>`, draft scaffolding is dropped, and
`## Reviewer Addendum` is carried over verbatim.

    promote-terra.py --vault <name> context [slug | --all]    # lane without Kimi
    promote-terra.py --vault <name> promote [slug | --all]     # Kimi fills the gap backlog
    promote-terra.py --vault <name> gate "<slug>" --note "<title>.md"   # deterministic gate

`promote` lane: an empty/boilerplate backlog costs 0 Kimi calls. A real backlog costs
two kimi-k3 calls: compose retrieval queries, then fill gaps from passages retrieved
scoped to `source-refs`. A gap that's still unfilled is logged as a return-leg.
`gate` still checks note lint, the index, the C2 Log, and loop_check on both lanes.

Replaces scripts/verify-draft.py (removed). Pattern: sub-command + --self-test,
stdlib + openai, no pytest.

Usage:
    py -3.13 promote-terra.py --vault example-vault promote --all
    py -3.13 promote-terra.py --vault example-vault context "some-source-slug"
    py -3.13 promote-terra.py --self-test
"""
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "retrieval"))
import synthlog  # noqa: E402

HOME = os.path.expanduser("~")
KIMI_MODEL = "kimi-k3"
KIMI_BASE_URL = "https://api.moonshot.ai/v1"
KIMI_MAX_COMPLETION_TOKENS = 32768
KIMI_REASONING_EFFORT = "high"


def resolve_vault(name):
    path = os.path.join(os.environ.get("AIO_PROJECTS", os.path.join(HOME, "Projects")), name)
    if not os.path.isdir(path):
        sys.exit(f"vault not found: {path}")
    return path


def _arg_vault(args):
    if "--vault" not in args:
        sys.exit('needs --vault <name>')
    return args[args.index("--vault") + 1]


def _today():
    return datetime.date.today().isoformat()


def transit_for(vault_dir, slug):
    # DON'T use synthlog.transit_path/draft_path here. Both run slugify() on their
    # argument, but `slug` is ALREADY the slugified result. slugify() truncates to
    # 80 characters AFTER .strip("-"), so an 80-character slug can end in "-";
    # running it through again drops that hyphen and produces a 79-character name
    # that matches no file. Seen in production: 3 of 45 drafts hit this.
    return os.path.join(vault_dir, "tmp", "retrieval-packets", f"{slug}.md")


def draft_for(vault_dir, slug):
    return os.path.join(vault_dir, "2. wiki", "_terra-drafts", f"{slug} (terra-draft).md")


def parse_frontmatter(text):
    text = text.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val == "" and i + 1 < len(lines) and re.match(r"^\s*-\s+", lines[i + 1]):
            items = []
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
                items.append(lines[i].split("-", 1)[1].strip().strip('"').strip("'"))
                i += 1
            out[key] = items
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                out[key] = []
            elif '"' in inner or "'" in inner:
                # Quoted item: extract the full quoted content. Raw file names often
                # contain ", " -- a naive comma split would break one path into two.
                pairs = re.findall(r'"([^"]*)"|\'([^\']*)\'', inner)
                out[key] = [a or b for a, b in pairs]
            else:
                out[key] = [x.strip() for x in inner.split(",") if x.strip()]
        else:
            out[key] = val.strip('"').strip("'")
        i += 1
    return out


_SECTION_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}[T ][0-9:+\-]*)\s*-\s*.+$", re.M)
_SUBSEC_RE = re.compile(r"^### (.+?)\s*$", re.M)


def extract_gap_backlog(body):
    """Grab the note-level backlog that sits before any dated section."""
    m = re.search(r"^## Gap backlog\s*$", body, re.M)
    if not m:
        return ""
    next_section = _SECTION_RE.search(body, m.end())
    end = next_section.start() if next_section else len(body)
    return body[m.end():end].strip()


_TITLE_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")
_DRAFT_SUFFIX_RE = re.compile(r"\s*\(draft\)\s*$", re.I)


def extract_title(body_src):
    match = _TITLE_RE.search(body_src)
    if not match:
        return None
    return _DRAFT_SUFFIX_RE.sub("", match.group(1)).strip()


def extract_section(body_src, heading):
    match = re.search(rf"(?m)^##\s+{re.escape(heading)}\s*$", body_src)
    if not match:
        return ""
    rest = body_src[match.end():]
    next_heading = re.search(r"(?m)^##\s+", rest)
    return (rest[:next_heading.start()] if next_heading else rest).strip()


def clean_markers(text):
    marker = re.compile(r"^\s*\[(?:NEEDS SOURCE|COVERAGE\?)\]")
    return "\n".join(line for line in text.split("\n")
                     if not marker.match(line)).strip()


def parse_collapse(draft_path):
    text = open(draft_path, encoding="utf-8").read().replace("\r\n", "\n")
    fm = parse_frontmatter(text)
    slug = os.path.basename(draft_path).replace(" (terra-draft).md", "")
    body = text[text.find("\n---\n", 3) + 5:] if text.startswith("---") else text

    gap_backlog = extract_gap_backlog(body)
    secs = list(_SECTION_RE.finditer(body))
    dated = []
    for i, m in enumerate(secs):
        chunk = body[m.end(): secs[i + 1].start() if i + 1 < len(secs) else len(body)]
        subs = {}
        sm = list(_SUBSEC_RE.finditer(chunk))
        for j, s in enumerate(sm):
            name = s.group(1).strip()
            val = chunk[s.end(): sm[j + 1].start() if j + 1 < len(sm) else len(chunk)].strip()
            subs[name] = val
        dated.append((m.group(1), subs))
    dated.sort(key=lambda t: t[0])          # ISO timestamp string sort = chronological
    merged = {}
    for _, subs in dated:                    # a later occurrence overwrites
        merged.update(subs)
    # A terra draft uses TWO negative-test section titles: "(umpan)" (vector path) and
    # "(deteksi fabrikasi)" (PageIndex path). Pop both. Normally only one is present;
    # if both are (e.g. a draft updated across both paths), merge them -- order
    # doesn't matter for negative_is_clean.
    neg_parts = [merged.pop(h, "") for h in
                 ("Negative test (umpan)", "Negative test (deteksi fabrikasi)")]
    negative = "\n\n".join(p for p in neg_parts if p)
    return {
        "frontmatter": fm,
        "subsections": merged,
        "negative_test": negative,
        "gap_backlog": gap_backlog,
        "slug": slug,
    }


# Bait-negation phrases for the "(deteksi fabrikasi)" section: an explicit refusal
# stating the bait topic isn't in the document. Case-insensitive, checked over the
# joined content lines.
# NOTE: the Indonesian phrases are protocol tokens kept for compatibility with
# existing vault drafts; the English phrases cover answers in English.
_NEG_BAIT_PHRASES = (
    "tidak membahas", "tidak ada", "tidak dibahas", "tidak menyinggung",
    "tidak termasuk", "di luar cakupan", "bukan tentang", "bukan mengenai",
    "does not", "not discuss", "no discussion", "not mention", "not cover",
)
# A clean refusal block may briefly mention the original document's scope after
# rejecting the bait. A concise sample PDF can reach 9 lines because of its focus list.
_NEG_MAX_BODY_LINES = 10


def _is_bait_line(s):
    low = s.lower()
    return (low.startswith("query bait:")
            or low.startswith("_query umpan;")
            or "sinyal fabrikasi" in low)


def negative_is_clean(neg_text):
    """Two forms of the negative-test section count as clean:

    (umpan)             -- every content line is a [NEEDS SOURCE] marker (low score,
                          retrieval declined to answer).
    (deteksi fabrikasi) -- an explicit refusal: a bait-negation phrase is present AND
                          the block is short (<= _NEG_MAX_BODY_LINES content lines).

    Dirty if the block is long OR no negation phrase is present -- i.e. an elaborate
    answer treating the bait topic as if it were real. A bait line itself doesn't count.
    An empty string -> True (defensive default; a real draft always has the section)."""
    body = [s for s in (ln.strip() for ln in neg_text.splitlines())
            if s and not _is_bait_line(s)]
    if not body:
        return True
    if all(s.startswith("[NEEDS SOURCE]") for s in body):
        return True
    low = " ".join(body).lower()
    has_negation = any(p in low for p in _NEG_BAIT_PHRASES)
    return has_negation and len(body) <= _NEG_MAX_BODY_LINES


def draft_status(path):
    return parse_frontmatter(open(path, encoding="utf-8").read()).get("status", "")


def unreviewed_drafts(vault_dir):
    """`terra-draft-unreviewed` drafts, sorted by ascending mtime (oldest first). The
    one place that list gets built; pick_next_draft, `context --all`, and
    `promote --all` all go through here."""
    ddir = os.path.join(vault_dir, "2. wiki", "_terra-drafts")
    if not os.path.isdir(ddir):
        return []
    return sorted(
        (os.path.join(ddir, f) for f in os.listdir(ddir)
         if f.endswith(".md") and draft_status(os.path.join(ddir, f)) == "terra-draft-unreviewed"),
        key=os.path.getmtime,
    )


def pick_next_draft(vault_dir):
    return next(iter(unreviewed_drafts(vault_dir)), None)


TYPE_ENUM = {"fakta", "interpretasi", "hipotesis", "risiko", "implikasi-desain"}
CONF_ENUM = {"Certain", "Likely", "Guessing"}


def lint_note(note_path):
    fails = []
    if not os.path.exists(note_path):
        return [f"note not found: {note_path}"]
    text = open(note_path, encoding="utf-8").read()
    fm = parse_frontmatter(text)
    body = text[text.find("---", 3) + 3:] if text.startswith("---") else text

    t = fm.get("type", "")
    if not isinstance(t, str) or t not in TYPE_ENUM:
        fails.append(f"type must be one of {sorted(TYPE_ENUM)}, got: {t!r}")
    if fm.get("confidence") not in CONF_ENUM:
        fails.append(f"confidence must be {sorted(CONF_ENUM)}, got: {fm.get('confidence')!r}")
    if not fm.get("method"):
        fails.append("method is empty (corpus.py | vcorpus.py)")
    if fm.get("updated") != _today():
        fails.append(f"updated must be today ({_today()}), got: {fm.get('updated')!r}")

    refs = fm.get("source-refs")
    has_refs = isinstance(refs, list) and len(refs) > 0
    if not has_refs:
        gap_ok = "## Gap backlog" in body and re.search(r"\n\|.*\|.*\|", body)
        ns_ok = re.search(r"(?<!`)\[NEEDS SOURCE\](?!`)", body)
        if not (gap_ok and ns_ok):
            fails.append("source-refs is empty with no bare [NEEDS SOURCE] + populated ## Gap backlog")

    if "> **DRAFT" in body:
        fails.append("DRAFT banner not yet removed")
    if "status: terra-draft-unreviewed" in body:
        fails.append("the string 'status: terra-draft-unreviewed' is still in the body")
    if _GAP_BOILERPLATE in body:
        fails.append("boilerplate Gap backlog row not yet replaced")
    if "[[" not in body:
        fails.append("no [[wikilink]] in the body")
    return fails


def check_index_links(vault_dir, titles):
    wiki = os.path.join(vault_dir, "2. wiki")
    if not os.path.isdir(wiki):
        return [f"2. wiki/ not found in {vault_dir}"]
    idx = [f for f in os.listdir(wiki) if f.startswith("00 - Index") and f.endswith(".md")]
    if not idx:
        return ["00 - Index*.md not found in 2. wiki/"]
    text = open(os.path.join(wiki, idx[0]), encoding="utf-8").read()
    return [f"00 - Index doesn't link [[{t}]]" for t in titles if f"[[{t}]]" not in text]


def check_c2_log(vault_dir):
    p = os.path.join(vault_dir, "2. wiki", "_C2 Log.md")
    if not os.path.exists(p):
        return ["_C2 Log.md not found"]
    for line in open(p, encoding="utf-8"):
        if line.startswith("## "):
            return [] if _today() in line else [f"top _C2 Log entry isn't today: {line.strip()}"]
    return ["_C2 Log.md has no entry heading"]


def run_loop_check(vault_name):
    lc = os.path.join(HERE, "loop_check.py")
    r = subprocess.run([sys.executable, lc, "--vault", vault_name],
                       capture_output=True, text=True)
    return [] if r.returncode == 0 else [f"loop_check.py failed:\n{r.stdout}\n{r.stderr}"]


def _pi_doc_id(vault_dir, ref):
    """Map one PDF source-ref to its PageIndex manifest doc_id."""
    manifest_path = os.path.join(vault_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return None
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    want = os.path.basename(ref.split("#")[0].strip()).lower()
    for name, meta in manifest.items():
        if name.lower() == want and isinstance(meta, dict):
            return meta.get("doc_id")
    return None


def _pi_retriever(vault_dir):
    from pageindex_retriever import PageIndexRetriever
    return PageIndexRetriever(vault_dir)


def _vec_retriever(vault_dir):
    from vector_store import VectorRetriever
    return VectorRetriever(vault_dir)


def _ref_for_gap(refs, ref_hint):
    """Use an exact source-ref hint; otherwise use refs[0] deterministically."""
    clean_hint = str(ref_hint or "").split("#")[0].strip().lower()
    for ref in refs:
        if ref.split("#")[0].strip().lower() == clean_hint and clean_hint:
            return ref
    return refs[0] if refs else None


def retrieve_for_gaps(vault_dir, refs, gap_queries, cap=8):
    """Retrieve each bounded gap query from its selected source-ref only."""
    results = []
    pi = vec = None
    queries = list(gap_queries or [])
    for gq in queries[:max(0, cap)]:
        gap = str(gq.get("gap", "")).strip()
        query = str(gq.get("query", "")).strip()
        ref = _ref_for_gap(refs, gq.get("ref_hint"))
        entry = {"gap": gap, "query": query, "ref": ref, "passages": []}
        if not ref or not query:
            entry["skipped"] = "empty gap/query or no source-ref available"
            results.append(entry)
            continue
        rel = ref.split("#")[0].strip()
        try:
            if rel.lower().endswith(".pdf"):
                doc_id = _pi_doc_id(vault_dir, rel)
                if not doc_id:
                    entry["skipped"] = "ref not yet indexed"
                    print(f"ref not yet indexed, gap {gap} can't be retrieved")
                else:
                    if pi is None:
                        pi = _pi_retriever(vault_dir)
                    passages = pi.retrieve(query, k=5, doc_ids=[doc_id])
                    entry["passages"] = [str(getattr(p, "text", p)) for p in passages]
            elif rel.lower().endswith(".md"):
                if vec is None:
                    vec = _vec_retriever(vault_dir)
                passages = vec.retrieve(query, k=5, source=os.path.basename(rel))
                entry["passages"] = [str(getattr(p, "text", p)) for p in passages]
            else:
                entry["skipped"] = "unsupported source-ref extension"
        except Exception as exc:
            entry["skipped"] = f"retrieval failed: {exc}"
            print(f"retrieval failed, gap {gap}: {exc}")
        results.append(entry)
    if len(queries) > max(0, cap):
        print(f"{len(queries) - max(0, cap)} gap queries skipped due to cap={cap}")
    return results


def append_return_leg(vault_dir, slug, unfilled):
    """Log orphaned gaps (Kimi couldn't fill them) as `G-TERRA-<slug>-<n>` rows in
    `01 - Project Context.md`'s `## Gap backlog`, plus one short entry in
    `_C2 Log.md`. `unfilled` is a list of gap text strings. Returns the row count."""
    if not unfilled:
        return 0
    context = os.path.join(vault_dir, "2. wiki", "01 - Project Context.md")
    if not os.path.isfile(context):
        print("warning: 01 - Project Context.md not found; skipping the return-leg backlog")
        return 0
    text = open(context, encoding="utf-8").read()
    section = re.search(r"^## Gap backlog\s*$", text, re.M)
    if not section:
        print("warning: ## Gap backlog not found; skipping the return-leg backlog")
        return 0
    next_section = re.search(r"^## .+$", text[section.end():], re.M)
    end = section.end() + (next_section.start() if next_section else len(text[section.end():]))
    prefix = text[:end]
    if not prefix.endswith("\n"):
        prefix += "\n"
    pattern = re.compile(rf"G-TERRA-{re.escape(slug)}-(\d+)")
    next_number = max((int(m.group(1)) for m in pattern.finditer(text)), default=0) + 1
    ids = []
    rows = []
    for gap in unfilled:
        gap = str(gap).replace("|", "/").replace("\n", " ").strip()
        ident = f"G-TERRA-{slug}-{next_number}"
        ids.append(ident)
        rows.append(f"| {ident} | NEEDS SOURCE | {gap} |\n")
        next_number += 1
    open(context, "w", encoding="utf-8").write(prefix + "".join(rows) + text[end:])

    c2 = os.path.join(vault_dir, "2. wiki", "_C2 Log.md")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"## {stamp} — promote-terra return-leg\n\n"
        f"Orphaned gaps from `{slug}` logged as NEEDS SOURCE: {', '.join(ids)}.\n\n"
    )
    old = open(c2, encoding="utf-8").read() if os.path.isfile(c2) else "# C2 Log\n"
    head, _, tail = old.partition("\n")
    open(c2, "w", encoding="utf-8").write(f"{head}\n\n{entry}{tail.lstrip()}")
    return len(ids)


def _load_names(path):
    """-> set of file names (as-is, case-sensitive), or None if the file doesn't exist.
    None is the sentinel for 'this tier doesn't apply', distinct from set() 'exists but empty'."""
    if not os.path.isfile(path):
        return None
    return {ln.strip() for ln in open(path, encoding="utf-8")
            if ln.strip() and not ln.lstrip().startswith("#")}


def terra_tolak_ok(refs, vault_dir):
    """Gate .md refs. Precedence:
      1. `1. raw/_terra-tolak.txt` exists -> deny-list: a .md is blocked if its basename
         is listed. Empty file = nothing blocked = every .md passes.
      2. else `1. raw/_terra-boleh.txt` exists -> old allow-list: a .md is blocked if it's
         NOT listed.
      3. else -> every .md passes.
    .pdf always passes (PageIndex path, controlled on its own)."""
    raw = os.path.join(vault_dir, "1. raw")
    deny = _load_names(os.path.join(raw, "_terra-tolak.txt"))
    allow = _load_names(os.path.join(raw, "_terra-boleh.txt")) if deny is None else None
    bad = []
    for ref in refs:
        rel = ref.split("#")[0].strip()
        if not rel.lower().endswith(".md"):
            continue                       # .pdf: PageIndex path, controlled on its own
        name = os.path.basename(rel)
        if deny is not None:
            if name in deny:
                bad.append(name)
        elif allow is not None and name not in allow:
            bad.append(name)
    return (not bad, bad)


def clamp_confidence(value):
    """Map confidence: 'Certain' -> 'Likely'; 'Likely'/'Guessing' -> unchanged; anything else -> 'Guessing'."""
    if value == "Certain":
        return "Likely"
    return value if value in ("Likely", "Guessing") else "Guessing"


def _windows_persistent_env(name):
    """Read a persistent Windows env var without printing a secret value."""
    if os.name != "nt":
        return None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return None
    try:
        import winreg
    except ImportError:
        winreg = None
    if winreg is not None:
        keys = (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        )
        for root, path in keys:
            try:
                with winreg.OpenKey(root, path) as key:
                    value, _kind = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if isinstance(value, str) and value.strip():
                return os.path.expandvars(value.strip())
    cmd = (
        f"$v=[Environment]::GetEnvironmentVariable('{name}','User');"
        f"if(-not $v){{$v=[Environment]::GetEnvironmentVariable('{name}','Machine')}};"
        "if($v){[Console]::Out.Write($v)}"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip()
    if proc.returncode == 0 and value:
        return os.path.expandvars(value)
    return None


def env_value(name):
    """Get an env var from the process; fall back to the persistent Windows env if the
    terminal hasn't restarted yet."""
    value = os.environ.get(name)
    if value:
        return value
    value = _windows_persistent_env(name)
    if value:
        os.environ[name] = value
        return value
    return None


def has_kimi_key():
    """True if the environment provides a key for Terra's verification lane."""
    return bool(env_value("MOONSHOT_API_KEY"))


def sanitize_title(raw):
    """Strip :/ \\?* characters, collapse whitespace, cap at 120 characters."""
    t = re.sub(r"[:/\\?*]", " ", raw)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:120]


def cmd_gate(vault_dir, slug, notes):
    vault_name = os.path.basename(vault_dir)
    draft = draft_for(vault_dir, slug)
    fails = []
    if not os.path.exists(draft):
        print(f"GATE FAILED: draft not found: {draft}")
        return 1
    st = parse_frontmatter(open(draft, encoding="utf-8").read()).get("status", "")
    if st == "terra-draft-unreviewed":
        fails.append("draft status is still 'terra-draft-unreviewed' -- flip it to 'promoted' after the note is written")
    if not notes:
        fails.append("needs at least one --note \"<title>.md\"")
    titles = [n[:-3] if n.endswith(".md") else n for n in notes]
    for n in notes:
        fails += lint_note(os.path.join(vault_dir, "2. wiki", n))
    if notes:
        fails += check_index_links(vault_dir, titles)
    fails += check_c2_log(vault_dir)
    fails += run_loop_check(vault_name)
    if fails:
        print("GATE FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"GATE PASSED: {slug} -> {', '.join(notes)}")
    return 0


def cmd_promote_manual(vault_dir, rest):
    """Promote drafts mechanically through draft_to_note, without Kimi."""
    dry = "--dry-run" in rest
    force = "--force" in rest
    targets = _promote_targets(vault_dir, rest)
    if not targets:
        print("DONE: no terra-draft-unreviewed drafts.")
        return 0
    done = fail = skip = 0
    for n, draft in enumerate(targets, 1):
        parsed = parse_collapse(draft)
        slug = parsed["slug"]
        negative = parsed["negative_test"]
        if negative.strip() and not negative_is_clean(negative):
            print(f"[{n}/{len(targets)}] {slug}  -> negative-test dirty, SKIP")
            skip += 1
            continue
        ok, bad = terra_tolak_ok(parsed["frontmatter"].get("source-refs") or [], vault_dir)
        if not ok:
            print(f"[{n}/{len(targets)}] {slug}  -> .md source blocked by confidential gate: {bad}, REFUSE")
            skip += 1
            continue
        if dry:
            print(f"[{n}/{len(targets)}] {slug}  -> draft_to_note (mechanical), not writing")
            continue
        result = draft_to_note(vault_dir, draft, "terra-context (mechanical)")
        try:
            note = write_register(vault_dir, slug, result, force=force,
                                  method="terra-context (mechanical)")
        except FileExistsError as exc:
            print(f"[{n}/{len(targets)}] {slug}  -> note already exists: {exc}, skipping (use --force)")
            fail += 1
            continue
        rc = cmd_gate(vault_dir, slug, [os.path.basename(note)])
        if rc == 0:
            print(f"[{n}/{len(targets)}] {slug}  -> GATE PASSED (mechanical)")
            done += 1
        else:
            print(f"[{n}/{len(targets)}] {slug}  -> GATE FAILED (note left in place)")
            fail += 1
            if len(targets) == 1:
                return 1
    print(f"\nsummary: {done} promoted (mechanical), {fail} gate-failed, {skip} skipped.")
    return 0 if fail == 0 else 1


def _gate_cli(vault_dir, rest):
    slug = None
    notes = []
    j = 0
    while j < len(rest):
        if rest[j] == "--note":
            if j + 1 >= len(rest):
                sys.exit('--note needs a value')
            notes.append(rest[j + 1])
            j += 2
        elif slug is None:
            slug = rest[j]
            j += 1
        else:
            sys.exit(f"unrecognized argument: {rest[j]}")
    if slug is None:
        sys.exit('usage: promote-terra.py --vault <name> gate "<slug>" --note "<title>.md" [--note ...]')
    return cmd_gate(vault_dir, slug, notes)


_SYS_QUERIES = (
    "You are Terra's retrieval planner. Input: a per-document synthesis draft's "
    "`## Gap backlog` and the draft text. For EVERY material gap row in the backlog, "
    "compose ONE specific retrieval query that, if answered from the source, closes that "
    "gap. Do not make up an answer; your only job is the query. Fill `ref_hint` with the "
    "source file name if the draft names it, otherwise an empty string. Output JSON: "
    '{"gap_queries": [{"gap": "<gap text>", "query": "<query>", "ref_hint": "<file name or empty>"}]}.'
    "\n\nAnswer in the language of the source material."
)

_SYS_FILL = (
    "You are Terra's gap filler. Input: the draft's `## Gap backlog`, the draft text, and "
    "the retrieval results per gap (a list of passages). For EVERY gap: if the passages "
    "support it well enough, write a short, locator-bearing `markdown` that closes the gap "
    "and set `filled` true; if the passages aren't enough or are empty, set `filled` false "
    "and `markdown` to an empty string. Do NOT use knowledge outside the passages. Do NOT "
    "touch or rewrite existing draft content -- you only add material for the gap. Output "
    "JSON: {\"fills\": [{\"gap\": \"<gap text>\", \"filled\": true, "
    "\"markdown\": \"<content>\", \"evidence\": \"<locator/quote>\"}]} ."
    "\n\nAnswer in the language of the source material."
)


def _kimi_json(system_prompt, user_payload):
    from openai import OpenAI
    api_key = env_value("MOONSHOT_API_KEY")
    if not api_key:
        raise RuntimeError("MOONSHOT_API_KEY not set")
    client = OpenAI(
        api_key=api_key,
        base_url=env_value("MOONSHOT_BASE_URL") or KIMI_BASE_URL,
    )
    for _ in range(2):
        resp = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_payload}],
            response_format={"type": "json_object"},
            reasoning_effort=KIMI_REASONING_EFFORT,
            max_completion_tokens=KIMI_MAX_COMPLETION_TOKENS,
        )
        try:
            return json.loads(resp.choices[0].message.content)
        except (json.JSONDecodeError, TypeError):
            pass
    raise RuntimeError("kimi: invalid JSON after 1 retry")


def llm_gap_queries(gap_backlog, draft_text):
    payload = (f"=== GAP BACKLOG ===\n{gap_backlog or '(empty)'}\n\n"
               f"=== DRAFT ===\n{draft_text}\n")
    result = _kimi_json(_SYS_QUERIES, payload)
    if not isinstance(result.get("gap_queries"), list):
        raise RuntimeError("llm_gap_queries: 'gap_queries' is not a list")
    return result


def llm_fill_gaps(gap_backlog, draft_text, retrieved):
    blocks = []
    for item in retrieved:
        joined = "\n---\n".join(item["passages"]) if item["passages"] else "(no passages)"
        blocks.append(f"## GAP: {item['gap']}\nquery: {item['query']}\nsource: {item['ref']}\n{joined}")
    payload = (f"=== GAP BACKLOG ===\n{gap_backlog or '(empty)'}\n\n"
               f"=== DRAFT ===\n{draft_text}\n\n=== RETRIEVAL PER GAP ===\n"
               + "\n\n".join(blocks) + "\n")
    result = _kimi_json(_SYS_FILL, payload)
    if not isinstance(result.get("fills"), list):
        raise RuntimeError("llm_fill_gaps: 'fills' is not a list")
    return result


def validate_fills(fills):
    """Validate only the structure returned by llm_fill_gaps."""
    errors = []
    if not isinstance(fills, list):
        return ["fills is not a list"]
    for i, item in enumerate(fills, 1):
        if not isinstance(item, dict):
            errors.append(f"fills[{i}] is not an object")
            continue
        if not isinstance(item.get("gap"), str) or not item["gap"].strip():
            errors.append(f"fills[{i}] gap is empty")
        if not isinstance(item.get("filled"), bool):
            errors.append(f"fills[{i}] filled is not a bool")
        elif item["filled"] and (not isinstance(item.get("markdown"), str)
                                  or not item["markdown"].strip()):
            errors.append(f"fills[{i}] filled=true without markdown")
    return errors


def write_register(vault_dir, slug, result, force=False, method=KIMI_MODEL):
    wiki = os.path.join(vault_dir, "2. wiki")
    title = sanitize_title(result["title"])
    note_path = os.path.join(wiki, f"{title}.md")
    if os.path.exists(note_path) and not force:
        raise FileExistsError(note_path)
    note_md = result["note_markdown"].replace("\r\n", "\n")
    # Pin method:/confidence: to script-controlled values, not an LLM guess.
    # Only inside the front-matter block (between the first --- and the closing ---);
    # a body sentence that happens to mention "method"/"confidence" must not get rewritten.
    fm_end = note_md.find("\n---\n", 4) if note_md.startswith("---\n") else -1
    # ponytail: no closing fence -> degenerate, replace over the whole string.
    head = note_md if fm_end == -1 else note_md[:fm_end]
    tail = "" if fm_end == -1 else note_md[fm_end:]
    for key, new_line in (("method", f'method: "{method}"'),
                          ("confidence", f'confidence: {result["confidence"]}')):
        pat = re.compile(rf"(?m)^{key}:.*$")
        # A missing line stays missing: lint_note fails a note without
        # method:/confidence:, and a gate failure is more honest than silently
        # patching a broken note. re.sub with no match = a no-op.
        head = pat.sub(lambda _m: new_line, head, count=1)
    note_md = head + tail
    open(note_path, "w", encoding="utf-8").write(note_md if note_md.endswith("\n") else note_md + "\n")

    idx = [f for f in os.listdir(wiki) if f.startswith("00 - Index") and f.endswith(".md")]
    if idx:
        p = os.path.join(wiki, idx[0])
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"\n- [[{title}]]\n")

    c2 = os.path.join(wiki, "_C2 Log.md")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"## {stamp} — promote-terra\n\nPromote `{slug}` -> `{title}.md` ({method}).\n\n"
    old = open(c2, encoding="utf-8").read() if os.path.exists(c2) else "# C2 Log\n"
    head, _, tail = old.partition("\n")
    open(c2, "w", encoding="utf-8").write(f"{head}\n\n{entry}{tail.lstrip()}")

    draft = draft_for(vault_dir, slug)
    dt = open(draft, encoding="utf-8").read()
    dt = re.sub(r"(?m)^status:\s*terra-draft-unreviewed\s*$",
                f'status: promoted\npromoted-to: "2. wiki/{title}.md"', dt, count=1)
    open(draft, "w", encoding="utf-8").write(dt)
    return note_path


_DROP_SUBSECTIONS = {"Questions this document doesn't answer"}


def _index_stem(vault_dir):
    wiki = os.path.join(vault_dir, "2. wiki")
    if os.path.isdir(wiki):
        for name in sorted(os.listdir(wiki)):
            if name.startswith("00 - Index") and name.endswith(".md"):
                return name[:-3]
    return "00 - Index"


def draft_to_note(vault_dir, draft_path, method_label, extra_fill=None):
    """Convert a Terra draft to a clean wiki note without calling an LLM."""
    raw = open(draft_path, encoding="utf-8").read().replace("\r\n", "\n")
    body_src = raw[raw.find("\n---\n", 3) + 5:] if raw.startswith("---") else raw
    parsed = parse_collapse(draft_path)
    fm = parsed["frontmatter"]
    title = extract_title(body_src) or parsed["slug"].replace("-", " ").title()
    parts = []
    for name, value in parsed["subsections"].items():
        if name in _DROP_SUBSECTIONS:
            continue
        cleaned = clean_markers(value)
        if cleaned:
            parts.append(f"## {name}\n\n{cleaned}")
    reviewer = extract_section(body_src, "Reviewer Addendum")
    if reviewer:
        parts.append(f"## Reviewer Addendum\n\n{reviewer}")
    if extra_fill:
        parts.append(extra_fill.strip())
    body = "\n\n".join(parts)
    if "[[" not in body:
        body = f"{body}\n\n[[{_index_stem(vault_dir)}]]"
    confidence = clamp_confidence(fm.get("confidence", "Guessing"))
    refs = fm.get("source-refs") or []
    ref_lines = "\n".join(f'  - "{ref}"' for ref in refs) if refs else "  []"
    frontmatter = (
        f"---\ntype: {fm.get('type', 'interpretasi')}\n"
        f"source-refs:\n{ref_lines}\n"
        f"confidence: {confidence}\n"
        f'method: "{method_label}"\n'
        f"updated: {_today()}\n---"
    )
    return {
        "title": title,
        "type": fm.get("type", "interpretasi"),
        "confidence": confidence,
        "note_markdown": f"{frontmatter}\n\n# {title}\n\n{body}\n",
    }


def _promote_targets(vault_dir, rest):
    if "--all" in rest:
        return unreviewed_drafts(vault_dir)
    slugs = []
    skip_value = False
    for arg in rest:
        if skip_value:
            skip_value = False
            continue
        if arg == "--max-calls":
            skip_value = True
            continue
        if not arg.startswith("--"):
            slugs.append(arg)
    if slugs:
        d = draft_for(vault_dir, slugs[0])
        return [d] if os.path.exists(d) else sys.exit(f"draft not found: {d}")
    d = pick_next_draft(vault_dir)
    return [d] if d else []


_GAP_BOILERPLATE = "not yet verified against the source"
# NOTE: must match a substring of synthlog.draft_header()'s boilerplate gap-backlog
# row verbatim (see retrieval/synthlog.py) -- that's how a still-untouched gap
# backlog is recognized as boilerplate rather than real content.


def _gap_is_boilerplate(gap_backlog):
    text = (gap_backlog or "").strip()
    if not text:
        return True
    data_rows = [line for line in text.splitlines()
                 if line.strip().startswith("|") and set(line.strip()) - set("|-: ")]
    return len(data_rows) <= 2 and _GAP_BOILERPLATE in text


def cmd_promote(vault_dir, rest):
    if "--model" in rest:
        sys.exit("--model was removed; the Terra verification lane only uses kimi-k3")
    dry = "--dry-run" in rest
    force = "--force" in rest
    max_calls = int(rest[rest.index("--max-calls") + 1]) if "--max-calls" in rest else 60
    print(f"model: {KIMI_MODEL}   max-calls: {max_calls}")
    targets = _promote_targets(vault_dir, rest)
    if not targets:
        print("DONE: no terra-draft-unreviewed drafts.")
        return 0
    calls = 0
    done = fail = skip = 0
    for n, draft in enumerate(targets, 1):
        parsed = parse_collapse(draft)
        slug = parsed["slug"]
        refs = parsed["frontmatter"].get("source-refs") or []
        negative = parsed["negative_test"]
        if negative.strip() and not negative_is_clean(negative):
            print(f"[{n}/{len(targets)}] {slug}  -> negative-test dirty, SKIP")
            skip += 1
            continue
        ok, bad = terra_tolak_ok(refs, vault_dir)
        if not ok:
            print(f"[{n}/{len(targets)}] {slug}  -> .md source blocked by confidential gate: {bad}, REFUSE")
            skip += 1
            continue
        gap = parsed["gap_backlog"]
        use_kimi = not _gap_is_boilerplate(gap)
        extra_fill = None
        unfilled = []
        if use_kimi:
            if dry:
                print(f"[{n}/{len(targets)}] {slug}  -> would call {KIMI_MODEL} 2x + retrieval")
                calls += 2
                continue
            if calls + 2 > max_calls:
                print(f"max-calls {max_calls} not enough for two stages; stopping at {slug}")
                break
            if not has_kimi_key():
                print("MOONSHOT_API_KEY not set; set that environment variable before the Kimi lane.")
                return 1
            draft_text = "\n\n".join(f"## {key}\n\n{value}"
                                      for key, value in parsed["subsections"].items())
            try:
                query_result = llm_gap_queries(gap, draft_text)
                calls += 1
                retrieved = retrieve_for_gaps(vault_dir, refs, query_result["gap_queries"])
                fill_result = llm_fill_gaps(gap, draft_text, retrieved)
                calls += 1
            except Exception as exc:
                print(f"[{n}/{len(targets)}] {slug}  -> LLM/retrieval failed: {exc}")
                fail += 1
                if len(targets) == 1:
                    return 1
                continue
            errors = validate_fills(fill_result.get("fills"))
            if errors:
                print(f"[{n}/{len(targets)}] {slug}  -> broken fills: {'; '.join(errors)}")
                fail += 1
                if len(targets) == 1:
                    return 1
                continue
            filled = [item for item in fill_result["fills"] if item["filled"]]
            unfilled = [item["gap"] for item in fill_result["fills"] if not item["filled"]]
            if filled:
                extra_fill = "## Supplement\n\n" + "\n\n".join(
                    f"### {item['gap']}\n\n{item['markdown'].strip()}" for item in filled
                )
        elif dry:
            print(f"[{n}/{len(targets)}] {slug}  -> empty gap backlog, draft_to_note without Kimi")
            continue

        method = "kimi-k3 (gap-fill)" if use_kimi else "terra-context (mechanical)"
        result = draft_to_note(vault_dir, draft, method, extra_fill=extra_fill)
        try:
            note = write_register(vault_dir, slug, result, force=force, method=method)
        except FileExistsError as exc:
            print(f"[{n}/{len(targets)}] {slug}  -> note already exists: {exc}, skipping (use --force)")
            fail += 1
            continue
        if unfilled:
            append_return_leg(vault_dir, slug, unfilled)
        rc = cmd_gate(vault_dir, slug, [os.path.basename(note)])
        if rc == 0:
            print(f"[{n}/{len(targets)}] {slug}  -> GATE PASSED   (calls {calls})")
            done += 1
        else:
            print(f"[{n}/{len(targets)}] {slug}  -> GATE FAILED (note left in place)   (calls {calls})")
            fail += 1
            if len(targets) == 1:
                return 1
    print(f"\nsummary: {done} promoted, {fail} gate-failed, {skip} skipped. {calls} LLM calls.")
    return 0 if fail == 0 else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    args = sys.argv[1:]
    if not args or args[0] == "--self-test":
        _selftest()
        return 0
    vault = resolve_vault(_arg_vault(args))
    i = args.index("--vault")
    rest = args[:i] + args[i + 2:]
    if not rest:
        sys.exit('usage: promote-terra.py --vault <name> <promote|context|gate> ...')
    verb, verb_args = rest[0], rest[1:]
    if verb == "promote":
        return cmd_promote(vault, verb_args)
    if verb == "context":
        return cmd_promote_manual(vault, verb_args)
    if verb == "gate":
        return _gate_cli(vault, verb_args)
    sys.exit(f"unrecognized sub-command: {verb}")


def _selftest():
    import tempfile
    import shutil
    global llm_gap_queries, llm_fill_gaps, retrieve_for_gaps
    global _pi_retriever, _vec_retriever
    tmp = tempfile.mkdtemp()
    today = _today()
    try:
        # parse_frontmatter: flow-list, block-list, comma-inside-quotes, CRLF
        fm_flow = parse_frontmatter('---\ntype: fakta\nsource-refs: ["a", "b"]\nconfidence: Likely\n---\nx\n')
        assert fm_flow["source-refs"] == ["a", "b"], fm_flow
        fm_comma = parse_frontmatter('---\nsource-refs: ["1. raw/An x, y and z.pdf"]\n---\n')
        assert fm_comma["source-refs"] == ["1. raw/An x, y and z.pdf"], fm_comma
        fm_block = parse_frontmatter('---\nsource-refs:\n  - "a"\n  - "b"\n---\n')
        assert fm_block["source-refs"] == ["a", "b"], fm_block
        fm_crlf = parse_frontmatter('---\r\ntype: fakta\r\nsource-refs: ["a"]\r\n---\r\nbody\r\n')
        assert fm_crlf.get("type") == "fakta", fm_crlf
        # mechanical text helpers
        assert extract_title("# Foo Bar (draft)\n\nx") == "Foo Bar"
        assert extract_title("## sub\n# Real Title\n") == "Real Title"
        assert extract_title("no heading here") is None
        _bs = "## A\n\naaa\n\n## Reviewer Addendum\n\nline1\nline2\n\n## B\n\nbbb\n"
        assert extract_section(_bs, "Reviewer Addendum") == "line1\nline2"
        assert extract_section(_bs, "Nope") == ""
        _mk = ("klaim satu.\n[NEEDS SOURCE]\n[COVERAGE?] - cek hal. 4\n"
               "klaim dua.\npakai [NEEDS SOURCE] di tengah kalimat.\n")
        assert clean_markers(_mk) == ("klaim satu.\nklaim dua.\n"
                                      "pakai [NEEDS SOURCE] di tengah kalimat.")
        # pick_next_draft: oldest unreviewed wins, promoted is skipped
        dv = os.path.join(tmp, "pv", "2. wiki", "_terra-drafts")
        os.makedirs(dv)
        old = os.path.join(dv, "aa (terra-draft).md")
        new = os.path.join(dv, "bb (terra-draft).md")
        open(old, "w", encoding="utf-8").write("---\nstatus: promoted\n---\n")
        open(new, "w", encoding="utf-8").write("---\nstatus: terra-draft-unreviewed\n---\n")
        assert os.path.basename(pick_next_draft(os.path.join(tmp, "pv"))) == "bb (terra-draft).md"
        open(old, "w", encoding="utf-8").write("---\nstatus: terra-draft-unreviewed\n---\n")
        os.utime(old, (1, 1))
        assert os.path.basename(pick_next_draft(os.path.join(tmp, "pv"))) == "aa (terra-draft).md"

        # lint_note: a clean note passes (updated = today)
        good = os.path.join(tmp, "Good.md")
        open(good, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs:\n  - \"1. raw/x.md#p1\"\n"
            f"confidence: Certain\nmethod: kimi-k3\nupdated: {today}\n---\n\n"
            "# Judul\n\nKlaim. [[00 - Index]]\n"
        )
        assert lint_note(good) == [], lint_note(good)
        # DRAFT banner -> fails
        bad1 = os.path.join(tmp, "Bad1.md")
        open(bad1, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs:\n  - \"a\"\nconfidence: Certain\n"
            f"method: x\nupdated: {today}\n---\n\n> **DRAFT - NOT REVIEWED**\n\n[[x]]\n"
        )
        assert any("DRAFT" in m for m in lint_note(bad1)), lint_note(bad1)
        # empty source-refs with no NEEDS SOURCE + Gap backlog -> fails
        bad3 = os.path.join(tmp, "Bad3.md")
        open(bad3, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs: []\nconfidence: Guessing\n"
            f"method: x\nupdated: {today}\n---\n\n# J\n\nklaim [[x]]\n"
        )
        assert any("source-refs" in m for m in lint_note(bad3)), lint_note(bad3)
        # empty source-refs BUT with NEEDS SOURCE + Gap backlog -> passes
        ok2 = os.path.join(tmp, "Ok2.md")
        open(ok2, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs: []\nconfidence: Guessing\n"
            f"method: x\nupdated: {today}\n---\n\n# J\n\nklaim [NEEDS SOURCE] [[x]]\n\n"
            "## Gap backlog\n\n| gap | jenis | status | tindak |\n|---|---|---|---|\n| cari | src | terbuka | retrieval |\n"
        )
        assert lint_note(ok2) == [], lint_note(ok2)
        # cmd_gate: missing note -> rc 1, not a crash
        import contextlib, io
        gv = os.path.join(tmp, "gatevault")
        os.makedirs(os.path.join(gv, "2. wiki", "_terra-drafts"))
        open(draft_for(gv, "d1"), "w", encoding="utf-8").write("---\nstatus: promoted\n---\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_gate(gv, "d1", ["Tak Ada.md"])
        assert rc == 1, "a missing note must fail"

        # cmd_promote_manual: --all with no drafts -> "DONE"
        import contextlib, io
        nv = os.path.join(tmp, "nextvault", "2. wiki", "_terra-drafts")
        os.makedirs(nv)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_promote_manual(os.path.join(tmp, "nextvault"), ["--all"])
        assert rc == 0 and "DONE" in buf.getvalue(), buf.getvalue()

        # parse_collapse: same subsection, the most recent dated section WINS
        d = os.path.join(tmp, "cv", "2. wiki", "_terra-drafts")
        os.makedirs(d)
        drf = os.path.join(d, "demo (terra-draft).md")
        open(drf, "w", encoding="utf-8").write(
            "---\ntype: hipotesis\nsource-refs: [\"1. raw/x.pdf\"]\nconfidence: Guessing\n"
            "status: terra-draft-unreviewed\nmethod: \"corpus.py\"\n---\n\n"
            "> **DRAFT - NOT YET REVIEWED.**\n\n## Gap backlog\n\n| a | b | c | d |\n|---|---|---|---|\n\n"
            "## 2026-09-04T10:00:00+07:00 - Esensial\n\n### Definisi\n\nversi LAMA par. 15.\n\n"
            "### Negative test (umpan)\n\n_Query umpan; jawaban panjang = sinyal fabrikasi:_ Soal Mars?\n\n"
            "[NEEDS SOURCE] skor 0.4 < 0.55 -- jangan jawab.\n\n"
            "## 2026-09-08T11:00:00+07:00 - Esensial\n\n### Definisi\n\nversi BARU par. 17.\n"
        )
        pc = parse_collapse(drf)
        assert pc["slug"] == "demo", pc["slug"]
        assert pc["frontmatter"]["type"] == "hipotesis", pc["frontmatter"]
        assert "par. 17" in pc["subsections"]["Definisi"], pc["subsections"]
        assert "par. 15" not in pc["subsections"]["Definisi"], "stale section not dropped"
        assert "| a | b | c | d |" in pc["gap_backlog"], pc["gap_backlog"]
        assert "Negative test (umpan)" not in pc["subsections"], "bait must be split out"
        assert negative_is_clean(pc["negative_test"]) is True, pc["negative_test"]
        # negative-test dirty: an answer paragraph is present
        assert negative_is_clean(
            "_Query umpan; jawaban panjang = sinyal fabrikasi:_ Soal X?\n\n"
            "Dokumen ini membahas X secara panjang lebar di bagian 3, dengan rincian A, B, C.\n"
        ) is False

        # parse_collapse: the "Negative test (deteksi fabrikasi)" title is also popped
        drf2 = os.path.join(d, "demo2 (terra-draft).md")
        open(drf2, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs: [\"1. raw/x.pdf\"]\nconfidence: Guessing\n"
            "status: terra-draft-unreviewed\nmethod: \"corpus.py (PageIndex)\"\n---\n\n"
            "## 2026-09-08T10:00:00+07:00 - Esensial\n\n### Klaim / temuan utama\n\nklaim demo2.\n\n"
            "### Negative test (deteksi fabrikasi)\n\n"
            "Query bait: Apa pembahasan dokumen ini tentang budidaya anggur di Mars?\n\n"
            "Dokumen ini tidak membahas budidaya anggur di Mars.\n\n"
            "Fokusnya adalah manajemen rantai pasok oleh perusahaan multinasional.\n\n"
            "### Questions this document doesn't answer\n\n- apa pun soal Mars.\n"
        )
        pc2 = parse_collapse(drf2)
        assert "Negative test (deteksi fabrikasi)" not in pc2["subsections"], list(pc2["subsections"])
        assert "tidak membahas budidaya anggur" in pc2["negative_test"], pc2["negative_test"]
        assert "Questions this document doesn't answer" in pc2["subsections"], "other subsections are kept"
        # negative_is_clean: a short (deteksi fabrikasi) refusal + a negation phrase -> clean
        assert negative_is_clean(
            "Query bait: Apa pembahasan dokumen ini tentang budidaya anggur di Mars?\n\n"
            "Dokumen ini tidak membahas budidaya anggur di Mars.\n\n"
            "Fokusnya adalah manajemen rantai pasok oleh perusahaan multinasional: risiko "
            "konsentrasi vendor, ketergantungan pemasok tunggal, biaya logistik lintas-negara.\n"
        ) is True
        # negative_is_clean: refusal pendek + daftar scope faktual (kasus Sample 1)
        assert negative_is_clean(
            "_Query umpan; jawaban panjang = sinyal fabrikasi:_ Apa pembahasan dokumen ini "
            "tentang topik yang pasti tidak ada di dokumen ini: budidaya anggur di Mars?\n\n"
            "Tidak ada pembahasan tentang budidaya anggur di Mars dalam dokumen ini.\n\n"
            "Dokumen membahas cara menulis bagian diskusi pada manuskrip ilmiah, khususnya:\n"
            "- menyatakan kembali tujuan studi dan temuan utama;\n"
            "- menafsirkan arti serta dampak temuan;\n"
            "- membandingkan hasil dengan literatur terdahulu;\n"
            "- menjelaskan implikasi bagi riset, pendidikan, praktik, atau kebijakan;\n"
            "- menguraikan kekuatan dan keterbatasan studi;\n"
            "- menyusun rekomendasi dan arah penelitian masa depan.\n\n"
            "Dokumen juga mencantumkan kesalahan umum dalam bagian diskusi.\n"
        ) is True
        # negative_is_clean: a long elaboration with no negation -> dirty
        assert negative_is_clean(
            "Query bait: Apa pembahasan dokumen ini tentang budidaya anggur di Mars?\n\n"
            + "\n".join(
                f"Kalimat {i}: koloni Mars memakai rumah kaca bertekanan untuk "
                f"membudidayakan anggur varietas tahan radiasi." for i in range(10))
            + "\n"
        ) is False
        # negative_is_clean: a negation phrase present but the block runs too long -> still dirty
        assert negative_is_clean(
            "Query bait: soal Mars?\n\n"
            "Tidak ada larangan membudidayakan anggur, jadi berikut rinciannya:\n\n"
            + "\n".join(f"- poin {i} soal budidaya anggur di Mars." for i in range(12))
            + "\n"
        ) is False

        # terra_tolak_ok guard tiers
        rv = os.path.join(tmp, "rv")
        os.makedirs(os.path.join(rv, "1. raw"))
        open(os.path.join(rv, "1. raw", "aturan.md"), "w", encoding="utf-8").write("# Aturan\nisi md.\n")
        # terra_tolak_ok tier 2 (old allow-list): only _terra-boleh.txt exists
        open(os.path.join(rv, "1. raw", "_terra-boleh.txt"), "w", encoding="utf-8").write("# komentar\naturan.md\n")
        assert terra_tolak_ok(["1. raw/aturan.md#h1", "1. raw/paper.pdf"], rv) == (True, [])
        assert terra_tolak_ok(["1. raw/rahasia.md"], rv) == (False, ["rahasia.md"])
        # tier 1 (deny-list): _terra-tolak.txt wins over _terra-boleh.txt
        open(os.path.join(rv, "1. raw", "_terra-tolak.txt"), "w", encoding="utf-8").write("# rahasia\nrahasia.md\n")
        assert terra_tolak_ok(["1. raw/rahasia.md"], rv) == (False, ["rahasia.md"])
        assert terra_tolak_ok(["1. raw/aturan.md", "1. raw/x.pdf"], rv) == (True, [])
        # tier 1 with an empty file: nothing is blocked
        open(os.path.join(rv, "1. raw", "_terra-tolak.txt"), "w", encoding="utf-8").write("# cuma komentar\n")
        assert terra_tolak_ok(["1. raw/rahasia.md", "1. raw/aturan.md"], rv) == (True, [])
        # tier 3: no gate file -> every .md passes
        os.remove(os.path.join(rv, "1. raw", "_terra-boleh.txt"))
        os.remove(os.path.join(rv, "1. raw", "_terra-tolak.txt"))
        assert terra_tolak_ok(["1. raw/apa-saja.md"], rv) == (True, [])
        # clamp_confidence
        assert clamp_confidence("Certain") == "Likely"
        assert clamp_confidence("Guessing") == "Guessing"
        assert clamp_confidence("aneh") == "Guessing"
        assert validate_fills([{"gap": "g", "filled": True,
                                "markdown": "x", "evidence": "p.3"}]) == []
        assert validate_fills([{"gap": "g", "filled": False}]) == []
        assert validate_fills([{"gap": "g", "filled": True, "markdown": ""}])
        assert validate_fills([{"filled": True, "markdown": "x"}])
        assert validate_fills("bukan list")
        assert validate_fills([{"gap": "g", "filled": "ya"}])

        # _kimi_json / llm_gap_queries: wiring through a fake openai (payload arrives, JSON retry).
        import types as _types
        _seen = {"messages": None, "n": 0}
        _replies = ["bukan json", '{"gap_queries": [{"gap": "g", "query": "q", "ref_hint": ""}]}']

        def _fake_create(**kw):
            _seen["messages"] = kw["messages"]
            content = _replies[min(_seen["n"], len(_replies) - 1)]
            _seen["n"] += 1
            msg = _types.SimpleNamespace(content=content)
            return _types.SimpleNamespace(choices=[_types.SimpleNamespace(message=msg)])

        class _FakeOpenAI:
            def __init__(self, **kw):
                _seen["init"] = kw
                self.chat = _types.SimpleNamespace(
                    completions=_types.SimpleNamespace(create=_fake_create))

        _fake_openai = _types.ModuleType("openai")
        _fake_openai.OpenAI = _FakeOpenAI
        sys.modules["openai"] = _fake_openai
        _old_moon = os.environ.get("MOONSHOT_API_KEY")
        os.environ["MOONSHOT_API_KEY"] = "selftest-only"
        try:
            out = llm_gap_queries("## Gap backlog\n| g |", "## Klaim\n\nx")
            assert out["gap_queries"][0]["gap"] == "g", out
            assert _seen["messages"][1]["role"] == "user"
            assert "## Klaim" in _seen["messages"][1]["content"], _seen["messages"]
            assert _seen["n"] == 2, "JSON invalid -> 1 retry"
        finally:
            sys.modules.pop("openai", None)
            if _old_moon is None:
                os.environ.pop("MOONSHOT_API_KEY", None)
            else:
                os.environ["MOONSHOT_API_KEY"] = _old_moon

        # _pi_doc_id: basename case-insensitive, missing document -> None.
        open(os.path.join(rv, "manifest.json"), "w", encoding="utf-8").write(
            json.dumps({"Paper X.pdf": {"doc_id": "pi-abc"}})
        )
        assert _pi_doc_id(rv, "1. raw/Paper X.pdf#p3") == "pi-abc"
        assert _pi_doc_id(rv, "1. raw/paper x.pdf") == "pi-abc"
        assert _pi_doc_id(rv, "1. raw/Missing.pdf") is None

        # retrieve_for_gaps: scoped adapter routing, cap counts gap queries, and
        # invalid ref_hint falls back deterministically to refs[0].
        class _Passage:
            def __init__(self, text):
                self.text = text

        pi_calls = []
        vec_calls = []
        class _StubPI:
            def retrieve(self, query, k=5, doc_ids=None):
                pi_calls.append((query, k, doc_ids))
                return [_Passage("pdf passage")]
        class _StubVec:
            def retrieve(self, query, k=5, source=None):
                vec_calls.append((query, k, source))
                if source == "boom.md":
                    raise RuntimeError("vector store empty")
                return [_Passage("md passage")]
        _real_pi_retriever = _pi_retriever
        _real_vec_retriever = _vec_retriever
        _pi_retriever = lambda _vault: _StubPI()
        _vec_retriever = lambda _vault: _StubVec()
        try:
            retrieved = retrieve_for_gaps(
                rv,
                ["1. raw/Paper X.pdf", "1. raw/aturan.md", "1. raw/boom.md", "1. raw/missing.pdf"],
                [
                    {"gap": "pdf gap", "query": "q pdf", "ref_hint": "1. raw/Paper X.pdf"},
                    {"gap": "md gap", "query": "q md", "ref_hint": "1. raw/aturan.md"},
                    {"gap": "err gap", "query": "q err", "ref_hint": "1. raw/boom.md"},
                    {"gap": "noid gap", "query": "q noid", "ref_hint": "1. raw/missing.pdf"},
                    {"gap": "fallback gap", "query": "q fb", "ref_hint": "1. raw/tidak-valid.md"},
                ],
                cap=5,
            )
            by_gap = {x["gap"]: x for x in retrieved}
            assert by_gap["pdf gap"]["passages"] == ["pdf passage"]
            assert by_gap["md gap"]["passages"] == ["md passage"]
            assert by_gap["err gap"]["passages"] == [], "a per-query exception must be handled gracefully"
            assert by_gap["noid gap"]["passages"] == [], "pdf without doc_id is skipped"
            assert by_gap["fallback gap"]["ref"] == "1. raw/Paper X.pdf", "ref_hint invalid -> refs[0]"
            assert vec_calls[0] == ("q md", 5, "aturan.md"), vec_calls
            capped = retrieve_for_gaps(
                rv,
                ["1. raw/Paper X.pdf", "1. raw/aturan.md"],
                [
                    {"gap": "one", "query": "q1", "ref_hint": "1. raw/aturan.md"},
                    {"gap": "two", "query": "q2", "ref_hint": "1. raw/aturan.md"},
                ],
                cap=1,
            )
            assert len(capped) == 1 and capped[0]["ref"] == "1. raw/aturan.md"
        finally:
            _pi_retriever = _real_pi_retriever
            _vec_retriever = _real_vec_retriever

        # append_return_leg: bare rows, IDs keep incrementing, land inside the section, no-op if absent.
        os.makedirs(os.path.join(rv, "2. wiki"), exist_ok=True)
        context = os.path.join(rv, "2. wiki", "01 - Project Context.md")
        open(context, "w", encoding="utf-8").write(
            "# Context\n\n## Gap backlog\n\n| Gap | Type | Next action |\n|---|---|---|\n"
            "| G-001 | DONE | x |\n\n## Links\n\n- x\n"
        )
        assert append_return_leg(rv, "demo", ["bukti A", "bukti B"]) == 2
        context_txt = open(context, encoding="utf-8").read()
        assert "| G-TERRA-demo-1 | NEEDS SOURCE | bukti A |" in context_txt, context_txt
        assert "| G-TERRA-demo-2 | NEEDS SOURCE | bukti B |" in context_txt
        assert context_txt.index("G-TERRA-demo-1") < context_txt.index("## Links")
        assert append_return_leg(rv, "demo", ["bukti C"]) == 1
        assert "| G-TERRA-demo-3 | NEEDS SOURCE | bukti C |" in open(context, encoding="utf-8").read()
        c2_txt = open(os.path.join(rv, "2. wiki", "_C2 Log.md"), encoding="utf-8").read()
        assert "return-leg" in c2_txt and "G-TERRA-demo-1" in c2_txt
        assert append_return_leg(rv, "demo", []) == 0
        open(context, "w", encoding="utf-8").write("# Context\n\n## Scope\n\nx\n")
        assert append_return_leg(rv, "demo", ["z"]) == 0
        assert append_return_leg(os.path.join(tmp, "no-vault"), "s", ["z"]) == 0
        # sanitize_title
        assert sanitize_title("Interpretasi: Peta/Literatur  Standar 112") == "Interpretasi Peta Literatur Standar 112"
        assert len(sanitize_title("x" * 200)) == 120

        # draft_to_note: outline preserved, scaffolding dropped, note comes out clean.
        dnv = os.path.join(tmp, "dnv")
        for sub in ("1. raw", "2. wiki/_terra-drafts"):
            os.makedirs(os.path.join(dnv, sub))
        open(os.path.join(dnv, "2. wiki", "00 - Index Sample.md"), "w", encoding="utf-8").write("# Index\n")
        dn_draft = draft_for(dnv, "paper-x")
        open(dn_draft, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs: [\"1. raw/Paper X.pdf\"]\nconfidence: Certain\n"
            "status: terra-draft-unreviewed\nmethod: \"corpus.py\"\n---\n\n"
            "# Paper X Full Title (draft)\n\n> **DRAFT - NOT YET REVIEWED.** do not use.\n\n"
            "## Gap backlog\n\n| gap | jenis | status | tindak-lanjut |\n|---|---|---|---|\n"
            "| whole section not yet verified against the source | v | terbuka | cek |\n\n"
            "## 2026-09-09T10:00:00+07:00 - Esensial Q1-Q8\n\n"
            "### Struktur\n\nAbstract, Intro, Method.\n\n"
            "### Definisi\n\nKlaim inti. [COVERAGE?]\n[NEEDS SOURCE]\nBaris nyata.\n\n"
            "### Negative test (umpan)\n\n_sinyal fabrikasi_\n\n[NEEDS SOURCE] skor 0.3.\n\n"
            "### Questions this document doesn't answer\n\n- Mars.\n\n"
            "## Reviewer Addendum\n\nMy manual note.\n"
        )
        dn_res = draft_to_note(dnv, dn_draft, "terra-context (mechanical)")
        assert dn_res["title"] == "Paper X Full Title"
        nm = dn_res["note_markdown"]
        assert "## Struktur" in nm and "## Definisi" in nm
        assert "## Reviewer Addendum" in nm and "My manual note." in nm
        assert "## Gap backlog" not in nm and "Negative test" not in nm
        assert "Questions this document doesn't answer" not in nm
        assert "> **DRAFT" not in nm and "Klaim inti. [COVERAGE?]" in nm
        assert "[[00 - Index Sample]]" in nm
        assert 'method: "terra-context (mechanical)"' in nm
        assert "confidence: Likely" in nm
        _dn_note = os.path.join(dnv, "2. wiki", dn_res["title"] + ".md")
        open(_dn_note, "w", encoding="utf-8").write(nm)
        assert lint_note(_dn_note) == [], lint_note(_dn_note)

        # cmd_promote_manual: end-to-end without MOONSHOT_API_KEY.
        mpv = os.path.join(tmp, "mpv")
        for sub in ("1. raw", "2. wiki/_terra-drafts"):
            os.makedirs(os.path.join(mpv, sub))
        open(os.path.join(mpv, "1. raw", "Paper X.pdf"), "w").write("")
        open(os.path.join(mpv, "2. wiki", "00 - Index M.md"), "w", encoding="utf-8").write("# Index\n")
        open(os.path.join(mpv, "2. wiki", "_C2 Log.md"), "w", encoding="utf-8").write("# C2 Log\n")
        mp_draft = draft_for(mpv, "paper-x")
        open(mp_draft, "w", encoding="utf-8").write(
            "---\ntype: fakta\nsource-refs: [\"1. raw/Paper X.pdf\"]\nconfidence: Guessing\n"
            "status: terra-draft-unreviewed\n---\n\n# Paper X (draft)\n\n"
            "## Gap backlog\n\n| a | b | c | d |\n|---|---|---|---|\n"
            "| whole section not yet verified against the source | v | terbuka | cek |\n\n"
            "## 2026-09-08T10:00:00+07:00 - Esensial\n\n### Klaim\n\nKlaim inti paper X.\n"
        )
        manual_buf = io.StringIO()
        with contextlib.redirect_stdout(manual_buf):
            rc_manual = cmd_promote_manual(mpv, ["paper-x"])
        assert rc_manual == 0, manual_buf.getvalue()
        manual_note = os.path.join(mpv, "2. wiki", "Paper X.md")
        assert os.path.isfile(manual_note)
        manual_text = open(manual_note, encoding="utf-8").read()
        assert 'method: "terra-context (mechanical)"' in manual_text
        assert draft_status(mp_draft) == "promoted"
        assert "[[Paper X]]" in open(os.path.join(mpv, "2. wiki", "00 - Index M.md"), encoding="utf-8").read()

        # FIX 2: write_register force=False menolak, force=True menimpa
        fv = os.path.join(tmp, "forcev")
        os.makedirs(os.path.join(fv, "2. wiki", "_terra-drafts"))
        open(os.path.join(fv, "2. wiki", "00 - Index F.md"), "w", encoding="utf-8").write("# Index\n")
        open(os.path.join(fv, "2. wiki", "_C2 Log.md"), "w", encoding="utf-8").write("# C2 Log\n")
        open(draft_for(fv, "fd"), "w", encoding="utf-8").write("---\nstatus: terra-draft-unreviewed\n---\n")
        fres = {"title": "Force Note", "type": "fakta", "confidence": "Likely",
                "note_markdown": f"---\nmethod: x\nupdated: {today}\n---\n\nbody v1\n"}
        fp = write_register(fv, "fd", fres)
        assert os.path.isfile(fp), "note pertama tak ditulis"
        try:
            write_register(fv, "fd", fres)
            assert False, "without force it must raise FileExistsError"
        except FileExistsError:
            pass
        fres2 = dict(fres, note_markdown=f"---\nmethod: x\nupdated: {today}\n---\n\nbody v2\n")
        fp2 = write_register(fv, "fd", fres2, force=True)
        assert "body v2" in open(fp2, encoding="utf-8").read(), "force=True must overwrite"
        open(draft_for(fv, "fd-m"), "w", encoding="utf-8").write(
            "---\nstatus: terra-draft-unreviewed\n---\n"
        )
        fres_m = dict(fres, title="Method Note")
        fpm = write_register(fv, "fd-m", fres_m, method="terra-context (mechanical)")
        assert 'method: "terra-context (mechanical)"' in open(fpm, encoding="utf-8").read()

        # cmd_promote: Kimi is only called for real gaps; filled content goes into Supplement.
        def _mk_promvault(root, gap_rows):
            for sub in ("1. raw", "2. wiki/_terra-drafts"):
                os.makedirs(os.path.join(root, sub))
            open(os.path.join(root, "1. raw", "Paper X.pdf"), "w").write("")
            open(os.path.join(root, "manifest.json"), "w", encoding="utf-8").write(
                '{"Paper X.pdf": {"doc_id": "pi-x"}}')
            open(os.path.join(root, "2. wiki", "00 - Index P.md"), "w", encoding="utf-8").write("# Index\n")
            open(os.path.join(root, "2. wiki", "_C2 Log.md"), "w", encoding="utf-8").write("# C2 Log\n")
            open(os.path.join(root, "2. wiki", "01 - Project Context.md"), "w", encoding="utf-8").write(
                "# Context\n\n## Gap backlog\n\n| Gap | Type | Next action |\n|---|---|---|\n")
            draft = draft_for(root, "paper-x")
            open(draft, "w", encoding="utf-8").write(
                "---\ntype: fakta\nsource-refs: [\"1. raw/Paper X.pdf\"]\nconfidence: Guessing\n"
                "status: terra-draft-unreviewed\n---\n\n# Paper X (draft)\n\n"
                f"## Gap backlog\n\n| gap | jenis | status | tindak |\n|---|---|---|---|\n{gap_rows}\n\n"
                "## 2026-09-08T10:00:00+07:00 - Esensial\n\n### Klaim\n\nKlaim inti.\n")
            return draft

        pv1 = os.path.join(tmp, "pv1")
        d1 = _mk_promvault(pv1, "| whole section not yet verified against the source | v | terbuka | cek |")
        _real_q, _real_r, _real_f = llm_gap_queries, retrieve_for_gaps, llm_fill_gaps
        llm_gap_queries = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Kimi tak boleh dipanggil"))
        with contextlib.redirect_stdout(io.StringIO()):
            rc1 = cmd_promote(pv1, ["paper-x"])
        assert rc1 == 0 and draft_status(d1) == "promoted"

        pv2 = os.path.join(tmp, "pv2")
        d2 = _mk_promvault(pv2, "| bukti angka Tabel 2 | evidence | terbuka | retrieval |")
        llm_gap_queries = lambda gb, dt: {"gap_queries": [{
            "gap": "bukti angka Tabel 2", "query": "what is the value of Table 2", "ref_hint": "1. raw/Paper X.pdf"}]}
        retrieve_for_gaps = lambda vd, refs, gqs, cap=8: [{
            "gap": "bukti angka Tabel 2", "query": "q", "ref": "1. raw/Paper X.pdf",
            "passages": ["Table 2 records 0.83 (p. 7)."]}]
        llm_fill_gaps = lambda gb, dt, rv: {"fills": [{
            "gap": "bukti angka Tabel 2", "filled": True,
            "markdown": "Table 2 value = 0.83 (p. 7).", "evidence": "hal. 7"}]}
        with contextlib.redirect_stdout(io.StringIO()):
            rc2 = cmd_promote(pv2, ["paper-x"])
        assert rc2 == 0 and draft_status(d2) == "promoted"
        n2 = open(os.path.join(pv2, "2. wiki", "Paper X.md"), encoding="utf-8").read()
        assert "## Supplement" in n2 and "0.83 (p. 7)" in n2
        assert 'method: "kimi-k3 (gap-fill)"' in n2

        pv3 = os.path.join(tmp, "pv3")
        d3 = _mk_promvault(pv3, "| missing evidence Y | evidence | terbuka | retrieval |")
        llm_gap_queries = lambda gb, dt: {"gap_queries": [{"gap": "missing evidence Y", "query": "cari Y", "ref_hint": ""}]}
        retrieve_for_gaps = lambda vd, refs, gqs, cap=8: [{
            "gap": "missing evidence Y", "query": "cari Y", "ref": "1. raw/Paper X.pdf", "passages": []}]
        llm_fill_gaps = lambda gb, dt, rv: {"fills": [{
            "gap": "missing evidence Y", "filled": False, "markdown": "", "evidence": ""}]}
        with contextlib.redirect_stdout(io.StringIO()):
            rc3 = cmd_promote(pv3, ["paper-x"])
        assert rc3 == 0 and os.path.isfile(os.path.join(pv3, "2. wiki", "Paper X.md"))
        assert "missing evidence Y" not in open(os.path.join(pv3, "2. wiki", "Paper X.md"), encoding="utf-8").read()
        assert "G-TERRA-paper-x-1" in open(os.path.join(pv3, "2. wiki", "01 - Project Context.md"), encoding="utf-8").read()
        llm_gap_queries, retrieve_for_gaps, llm_fill_gaps = _real_q, _real_r, _real_f

        # _promote_targets: --all on a vault with no _terra-drafts folder -> [] (not a crash)
        assert _promote_targets(os.path.join(tmp, "nihil"), ["--all"]) == []
        # _promote_targets: flag operasional tidak dianggap sebagai slug
        mv = os.path.join(tmp, "mv")
        os.makedirs(os.path.join(mv, "2. wiki", "_terra-drafts"))
        open(draft_for(mv, "model-lama"), "w", encoding="utf-8").write("---\nstatus: terra-draft-unreviewed\n---\n")
        open(draft_for(mv, "real"), "w", encoding="utf-8").write("---\nstatus: terra-draft-unreviewed\n---\n")
        assert _promote_targets(mv, ["real", "--max-calls", "1"]) == [draft_for(mv, "real")]
        try:
            cmd_promote(mv, ["real", "--model", "model-lama"])
            assert False, "--model must be rejected"
        except SystemExit as e:
            assert "only uses kimi-k3" in str(e), e

        print("OK promote-terra selftest")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
