---
name: loop-review
description: REVIEW phase of the wiki->output loop. Adversarially critiques the `3. output/` draft through an independent reviewer subagent, checks every claim against the claim map and wiki notes, and writes `.loop/<slug>/critique.md`. Call explicitly with /loop-review, or chained automatically by loop-engine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
disable-model-invocation: true
---

# loop-review — Phase 3: adversarial critique

The **semantic** layer of the gate. The mechanical layer is `/loop-verify`. Both must pass.

## Standing rules

Read `~/AI-RULES.md` (the user's rules file) and the vault `AGENTS.md` before step 1.

These rules bind the REVIEW phase:

1. **The reviewer must be independent.** Run the critique in a clean-context subagent, not a
   self-assessment by the context that just wrote the draft. Authors grading their own writing
   are always too generous.
2. **Adversarial.** Try to break every finding before writing it down. Report only what survives.
   One finding that survived an attempt to break it is worth more than three that weren't tested.
3. **Evidence per finding.** Cite `file:line`, a direct quote, or a claim ID. Don't state a
   plausible-sounding conclusion that wasn't actually checked.
4. **Confidence per finding:** `CONFIRMED` only once matched against a wiki note or raw file.
   Otherwise `UNVERIFIED`, stating what couldn't be checked and why.
5. **Don't edit the draft in this phase.** This phase writes `critique.md` only. Fixes happen
   in `/loop-act` on the next iteration.
6. Be terse. No filler, no emoji, no opening compliments.

## Steps

1. Read `state.json`, `plan.md`, and the draft at `3. output/<name>.md`.
2. Read the previous `critique.md` if one exists; determine the next iteration number.
3. Pick a reviewer matching the deliverable type:
   - Academic manuscript: the `academic-paper-reviewer` subagent.
   - Policy memo, report, brief: `general-purpose` subagent with the critique instructions below.
   Send the subagent: the draft, `plan.md`, and the list of wiki note paths. Don't send `1. raw`
   content unless asked, so the reviewer tests the chain instead of patching from the source.
4. Check the following and log every deviation:
   - **Unmoored claims.** A claim-bearing sentence with no `[K<n>]` ID and no `[NEEDS SOURCE]`.
   - **Claims exceeding their source.** An ID exists, but the wiki note it cites doesn't support
     that strong a claim.
   - **Logical leaps.** A chapter's conclusion doesn't follow from the claims it carries.
   - **Silently closed gaps.** A gap from `plan.md` disappeared from the draft with no new source.
   - **Dishonest confidence.** A `Guessing` claim stated with certain-sounding phrasing.
   - **Direct citation of `1. raw`.** Breaks the chain; the wiki gets skipped.
5. Write `<vault>/.loop/<slug>/critique.md` following [critique-format.md](critique-format.md).
6. Set `phase` to `REVIEW` in `state.json`, update `lastUpdated`.
7. Report the finding count per level and the verdict: `LULUS` (pass) or `ULANG ACT` (redo ACT).

## Verdict

- Any **BLOCKER**: verdict `ULANG ACT`.
- Only **MINOR** findings: verdict `LULUS`, minor findings logged for FINISH.
- Zero findings two iterations in a row: stop REVIEW, proceed to VERIFY.
