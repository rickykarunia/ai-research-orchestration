# Thin CLAUDE.md template (pointer)

Copy **from the `# <Project Name>` line to the end** into a `CLAUDE.md` file at the vault root.
Replace `<Project Name>`. Don't add rules here - all rules live in `AGENTS.md`
(the multi-harness canonical file, harvested by `index_sync.py`). This CLAUDE.md only points there, to avoid drift.

Deliberately **without routing front matter**: front matter belongs only in `AGENTS.md`.

---

<!-- ================= COPY STARTS HERE ================= -->

```markdown
# <Project Name>

This project's rules live in **`AGENTS.md`** (vault root, multi-harness canonical).
Read `AGENTS.md` first before working. Don't duplicate rules in this file.

Cross-project anchors:
- Behavior: `~/AI-RULES.md`
- Cross-vault routing: `~/AI-INDEX.md`

Precedence: session instructions > project `AGENTS.md` > `AI-RULES.md`.
```

<!-- ================= COPY ENDS HERE ================= -->
