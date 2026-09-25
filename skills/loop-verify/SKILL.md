---
name: loop-verify
description: VERIFY phase of the wiki->output loop. The mechanical gate. Runs loop_check.py, matches every claim marker in the draft against the claim map, then writes `.loop/<slug>/verify.md` and a return-leg update to `2. wiki`. Call explicitly with /loop-verify, or chained automatically by loop-engine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
disable-model-invocation: true
---

# loop-verify — Phase 4: mechanical gate + return leg

Formalizes the project README's return-leg and verification sections.

`<kit-root>` = the ai-research-orchestration clone (the folder containing `scripts/`; this skill
folder is `<kit-root>/skills/loop-verify`).

## The honest limit

`loop_check.py` checks that `source-refs` **exists**, not that the claim's content **matches**
its source. Content matching is tested by `/loop-review`. Don't claim the mechanical gate proves
substance is correct. It proves the traceability chain exists, and only that.

## Standing rules

Read `~/AI-RULES.md` (the user's rules file) and the vault `AGENTS.md` before step 1.

These rules bind the VERIFY phase:

1. **Don't declare a pass without running the command and showing its output.**
   AI-RULES §12: done means verified.
2. **The exit code is the verdict.** Don't reinterpret `loop_check.py`'s output to make it pass.
3. **The return leg is mandatory.** New gaps and questions get written to `2. wiki`, not just
   reported in chat. Without the return leg, the loop isn't done.
4. Be terse. Quote the decisive output line, not the whole log.

## Steps

1. Read `state.json`, `plan.md`, `critique.md`, and the draft `3. output/<name>.md`.
2. **Check A - claim markers.** Collect every `[K<n>]` in the draft. Compare against the IDs in
   the claim map.
   - An ID in the draft not in the map: fail.
   - An ID in the map not used by the draft: log it, not a failure.
3. **Check B - gaps.** Every `[NEEDS SOURCE]` in the draft must have a matching gap row in
   `plan.md`. Missing: fail.
4. **Check C - return leg.** Write or update a `2. wiki` note with new gaps, decisions made, and
   questions the current evidence can't answer. This note must carry the full AI-RULES §6a
   front matter (`type`, `source-refs`, `confidence`, `updated`).
5. **Check D - mechanical gate.** Run and show the output:
   ```powershell
   py -3.13 "<kit-root>\scripts\loop_check.py" --vault <vault>
   ```
   A `PROV` or `RATCHET` finding = fail.
6. Write `<vault>/.loop/<slug>/verify.md` following [verify-report-format.md](verify-report-format.md).
7. Set `phase` in `state.json` to `VERIFY`, update `lastUpdated`.
8. Report the verdict: `LULUS` (pass, all four checks clean) or `GAGAL` (fail, name which check).

## Notes

- Check C runs **before** Check D deliberately. `loop_check.py` flags "output more than 24h
  newer than wiki" as an unwritten return leg; writing the return leg first makes that gate
  meaningful instead of just something to route around.
- If `RATCHET` cites "wiki too thin," that's about the vault as a whole, not this deliverable.
  Report it as-is, don't paper over it with empty notes.
