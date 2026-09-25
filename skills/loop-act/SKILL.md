---
name: loop-act
description: ACT phase of the wiki->output loop. Assembles the deliverable Markdown draft in `3. output/` from the claim map in `.loop/<slug>/plan.md`, using only `2. wiki` notes. Call explicitly with /loop-act, or chained automatically by loop-engine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
disable-model-invocation: true
---

# loop-act — Phase 2: assemble the draft

Formalizes the project README's "Assemble into 3. output" step. Its output is one Markdown
file in `3. output/`.

## Standing rules

Read `~/AI-RULES.md` (the user's rules file) and the vault `AGENTS.md` before step 1.
Precedence: session instructions > vault AGENTS.md > AI-RULES.

These rules bind the ACT phase:

1. **Assemble from `2. wiki` only.** Not from `1. raw`, not from chat, not from the model's memory.
   This is the core of the "output isn't just an LLM output" claim. Breaking this voids the whole loop.
2. **No claim outside the `plan.md` claim map.** Need a new claim? Stop ACT, go back to
   `2. wiki`, synthesize it there, then rerun `/loop-plan`.
3. **Every claim carries its trace.** Insert a `[K<n>]` marker on the sentence that carries the
   claim, or a footnote pointing at the wiki note. REVIEW and VERIFY read this marker.
4. **Gaps are written, not patched over.** A claim with no source appears as `[NEEDS SOURCE]`
   in the body text. Don't invent a logical bridge to paper over it.
5. **Markdown output.** Don't produce PDF, DOCX, or LaTeX in this phase.
6. Be terse. No filler, no emoji.

## Steps

1. Read `<vault>/.loop/<slug>/state.json`. If missing, ask the user to run `/loop-plan` first.
2. Read `<vault>/.loop/<slug>/plan.md`. If missing, same: stop.
3. If `critique.md` exists from a previous iteration, read it and treat its findings as
   mandatory fixes for this draft.
4. Read every `2. wiki` note the claim map cites. Read the content, don't rely on the title.
5. Write the draft to `3. output/<name>.md`, following the chapter outline in `plan.md`. Follow
   [draft-contract.md](draft-contract.md).
6. Bump `iteration` in `state.json`, set `phase` to `ACT`, update `lastUpdated`.
7. Report: claims used, remaining `[NEEDS SOURCE]` count, and which chapter is thinnest.

## Notes

- Assembly-helper skills may be used as tools inside this phase (`document-generate`,
  `academic-paper`, `deep-research`), but the source contract above still applies in full.
- Don't run `humanizer` or a voice/style skill here. Style alignment happens at FINISH, after
  the draft passes VERIFY. Polishing a draft that hasn't passed yet just burns tokens.
- One canonical deliverable per need. Revise the same file across iterations — don't stack
  `draft-v1`, `draft-v2` in `3. output/`.
