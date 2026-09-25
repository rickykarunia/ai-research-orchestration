---
type: implikasi-desain
source-refs: []
confidence: Certain
updated: YYYY-MM-DD
---

# C2 Log - <vault name>

This file comes from `templates\C2 Log - template.md`. The automated scaffold creates it via
`scripts\new-vault.ps1`; on the manual path, save it as `2. wiki/_C2 Log.md`, change the date
and vault name, then link it from the entry index and Project Context.

Handoff channel between Claude and Codex for this vault. Append-only: new entries go on TOP,
old entries are never edited. Whoever opens the vault reads the top five entries before working.

Single-entry format:

## YYYY-MM-DD HH:MM - <claude|codex>

**Worked on:** <one line, files touched with path>
**Findings:** <what was found, with a pointer to raw if applicable>
**Open gap:** <unresolved NEEDS SOURCE / NEEDS VERIFICATION / NEEDS USER DECISION>
**For the other side:** <a concrete request, or `none`>

---
