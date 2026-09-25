---
name: loop-plan
description: PLAN phase of the wiki->output loop. Reads `2. wiki` notes and builds a claim map (claim -> wiki note -> raw file -> source section) into `.loop/<slug>/plan.md`. Does not write deliverable prose yet. Call explicitly with /loop-plan, or chained automatically by loop-engine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
disable-model-invocation: true
---

# loop-plan — Phase 1: claim map

This phase formalizes the **"gate between wiki and output"** step from the project README.
Its output is one file, `plan.md`, not deliverable prose.

## Standing rules

Read `~/AI-RULES.md` (the user's rules file) before step 1 and follow it through the run.
Also read `AGENTS.md` at the vault root. Precedence: session instructions > vault AGENTS.md > AI-RULES.
If either file is missing, say so — don't proceed silently.

These rules bind the PLAN phase and win over any step below that conflicts:

1. **Don't write deliverable prose in this phase.** This phase produces `plan.md` only.
2. **Single source = `2. wiki`.** Don't build the claim map from `1. raw`, from chat, or from the
   model's memory. If a claim has no wiki note, that's a gap, not material.
3. **Every claim-map row must carry the full chain** `claim -> wiki note -> raw file ->
   source section`. A broken chain gets `[NEEDS SOURCE]`, never patched with a guess.
4. **Confidence per claim** (`Certain` / `Likely` / `Guessing`), per AI-RULES §2.
5. Be terse. No filler, no emoji, no em dash.

## Steps

1. Determine the vault. If the user doesn't name one, read `AI-INDEX.md` and match the task against
   `route-when`. Nothing matches: report it, don't guess.
2. Confirm the vault has `loop: true` in `AGENTS.md` front matter. If `false`, say loop-engine
   doesn't apply here, and stop.
3. Derive the deliverable `slug` from the name the user gives (lowercase, spaces to hyphens,
   max 50 characters). Create `<vault>/.loop/<slug>/` if it doesn't exist.
4. Inventory `2. wiki`: list every note with its `type`, `confidence`, and `source-refs`.
   Use `obsidian search` / `obsidian backlinks` if Obsidian is available; fall back to `rg`.
5. State the deliverable's thesis in one sentence. Show it to the user.
6. Build the chapter outline. Each chapter names which claims it carries.
7. For each claim, trace the chain to its wiki note, then to that note's `source-refs`, then to
   the source section in `1. raw`. A broken chain is logged as a gap.
8. Write `<vault>/.loop/<slug>/plan.md` following [plan-format.md](plan-format.md).
9. Write `<vault>/.loop/<slug>/state.json`:
   ```json
   {"deliverable":"<name>","vault":"<vault>","slug":"<slug>",
    "outputPath":"3. output/<name>.md","phase":"PLAN","iteration":0,
    "maxIterations":3,"finishStyle":"humanizer",
    "startedAt":"<ISO8601>","lastUpdated":"<ISO8601>"}
   ```
   `finishStyle` is only set to something other than `humanizer` if the user explicitly asks.
10. Report: claim count, gap count, and the thesis. Suggest `/loop-act` if the gaps are
    acceptable, or a return to `2. wiki` first if there are too many.

## Notes

- The final deliverable is **Markdown**. Don't plan a PDF output.
- `plan.md` lives in `.loop/`, not in `2. wiki`. `loop_check.py` requires every `.md` in
  `2. wiki` to carry `source-refs`; putting loop artifacts there triggers a false PROV finding.
- If `plan.md` already exists from a previous run, overwrite it and bump its iteration note.
