---
name: loop-engine
description: Orchestrator for the wiki->output loop. Chains PLAN -> ACT -> REVIEW -> VERIFY with gates and bounded loop-back, then FINISH with the humanizer style pass (or another style if the user asks). Produces a Markdown deliverable in `3. output/` where every claim traces back to a `2. wiki` note. Call explicitly with /loop-engine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, Skill
disable-model-invocation: true
---

# loop-engine — wiki -> output loop orchestrator

Runs four sequential phases plus FINISH. The point: a deliverable in `3. output/` that
isn't just a one-shot LLM output, but the result of a claim map, independent critique, and
a mechanical gate.

```
PLAN -> ACT -> REVIEW -> VERIFY -> gate -> FINISH
          ^                          |
          +---- gap to 2. wiki ------+   (max 3 iterations)
```

## Standing rules

Read `~/AI-RULES.md` (the user's rules file) then `AGENTS.md` at the vault root before step 1.
Precedence: session instructions > vault AGENTS.md > AI-RULES. If either file is missing, say so.

These rules bind the whole run and win over any step below that conflicts:

1. **Phases cannot be skipped.** A draft that hasn't passed REVIEW and VERIFY is never reported as done.
2. **ACT's only source is `2. wiki`.** Breaking this voids the entire value of the loop.
3. **Independent reviewer.** REVIEW runs in a clean-context subagent.
4. **The deterministic gate wins.** A `loop_check.py` failure is a failure, whatever the model thinks.
5. **The loop is capped at 3 iterations.** Hit the cap: stop, report the remaining gaps, hand off
   to the user. Don't force a flawed output through, and don't spin indefinitely.
5b. **A recognized gap is a logged gap.** Every gap that surfaces must be either closed OR demoted
   to the durable backlog (see "Gap cycle"). The danger isn't looping once vs. several times, it's a
   recognized gap silently disappearing. A gap must never be dropped without a trace.
6. **Markdown output.** The final deliverable is `.md` in `3. output/`. Do not produce a PDF.
7. Be terse. No filler, no emoji.

## Steps

1. Determine the vault and deliverable name. If the vault isn't named, match the task against
   `route-when` in `AI-INDEX.md`. Nothing matches: report it, don't guess.
2. Confirm `loop: true` in the vault's `AGENTS.md`. If not, say loop-engine doesn't apply here, stop.
3. Create one todo per phase: PLAN, ACT, REVIEW, VERIFY, FINISH.
4. **PLAN.** Run `loop-plan`. Start with the **COVERAGE** sub-step (see "Gap cycle"):
   confirm each source's core thesis is already a spine in `2. wiki`, flag uncited sections
   `[COVERAGE?]`. Then build the claim map and triage each gap (retrieval vs. source). If the
   number of gaps exceeds the number of sourced claims, stop and suggest more synthesis in
   `2. wiki` first. The loop can't conjure material that doesn't exist yet.
5. **ACT.** Run `loop-act`.
6. **REVIEW.** Run `loop-review`. Verdict `ULANG ACT` (redo ACT) and under 3 iterations:
   write the BLOCKER findings as gaps to `2. wiki`, then return to step 5.
7. **VERIFY.** Run `loop-verify`. Verdict `GAGAL` (fail) and under 3 iterations:
   return to step 5.
8. **Gate.** Proceed to FINISH only if REVIEW is `LULUS` (pass) and VERIFY is `LULUS`.
   Iterations capped at 3 without passing: stop, write the remaining gaps to `2. wiki`, report to
   the user what's unresolved. Do not call FINISH.
9. **FINISH.**
   - Default: apply the prose style defined in the user's `~/AI-RULES.md` (default: a
     `humanizer` skill) to the `3. output/<name>.md` draft.
   - If the user asks for a dedicated voice/style skill for this deliverable explicitly, or
     `finishStyle` in `state.json` names one: run that style skill instead, and **don't** run
     the default humanizer pass afterward. Stacking both overwrites one style's calibration with
     the other's.
   - Set `status: final` in the draft's front matter. Keep it as `.md`.
10. Set `phase` to `FINISH` in `state.json`. Report: iterations used, claim count, remaining
    gaps, the FINISH style used, and the deliverable path.

## Choosing the FINISH style

| Condition | Skill |
|---|---|
| Default for every deliverable | the prose style defined in `~/AI-RULES.md` (default: a `humanizer` skill) |
| The user has a dedicated voice/style skill for this domain and asks for it explicitly | that skill |

A dedicated voice skill needs an explicit call and applies to a bounded domain. The default
humanizer floor is domain-agnostic. Pick one, not both.

## Gap cycle (standard for every loop)

Two markers, two directions:

- `[NEEDS SOURCE]` — forward direction: a claim in wiki/output with no valid source.
- `[COVERAGE?]` — backward direction: a source section/node not yet cited by any wiki note.
  A candidate for a main idea that synthesis missed.

### COVERAGE (sub-step in PLAN, before the claim map)

Pull each source's main idea by **position**, not a generic semantic query: abstract (front) +
conclusion (back). PageIndex: the named node on the tree. Vector/md: pages 1-2 and the last
section, or the `# Abstract` / `# Conclusion` heading in a Marker-generated md. Write each
source's core thesis to `2. wiki` as a spine before hanging detail claims off it. A source
section not reflected in any wiki note gets flagged `[COVERAGE?]`.

Why: query-driven retrieval only finds what's asked. Generic meta-queries ("main contribution")
often fail — embeddings match topic/vocabulary, not meta-role ("this is the thesis"). Structural
anchoring catches main ideas that ad-hoc queries miss.

### Gap triage (mandatory classification for every gap)

| Type | Meaning | In-loop action |
|---|---|---|
| **retrieval-gap** | The fact EXISTS in raw, the query wasn't sharp enough | Targeted re-query, **max 2 reformulations** per gap. Closed → write the claim + locator, remove the marker. Not closed within budget → demote to backlog. |
| **source-gap** | The fact does NOT exist in any corpus | Don't re-query (wasted effort). Straight to backlog: needs new raw material ingested, or an honest permanent limit. |

### Iteration policy

- Retrieval-gaps are closed **within the run**, but **bounded**: max 2 query reformulations per
  gap (total loop-back still bound by rule #5, max 3). Not unlimited re-querying.
- What's not closed within budget → a **backlog row**, never silently dropped. The backlog is
  persistent across sessions: that's what makes "follow up later" traceable instead of forgotten.
- Every gap ends in one of two states: **closed** or **logged to backlog**. No third state.

### Backlog (durable)

A `## Gap backlog` section in the vault's index note (`2. wiki/`, the entry point). One row per gap:

```
| gap | type | status | follow-up |
|---|---|---|---|
| DiD Post×Treat figure | retrieval | closed | closed 2026-08-24, p. 11 |
| effect on private companies | source | open | needs another paper / honest limit |
```

`loop_check.py` (the GAP check) flags an open `[NEEDS SOURCE]` / `[COVERAGE?]` in `2. wiki` or
`3. output` with no `## Gap backlog` section anywhere in the vault. An open gap with no backlog = failure.

## Artifacts

All working artifacts live under `<vault>/.loop/<slug>/`, outside `2. wiki`:

| File | Written by | Content |
|---|---|---|
| `plan.md` | loop-plan | claim map, gaps, verification criteria |
| `critique.md` | loop-review | adversarial findings per iteration |
| `verify.md` | loop-verify | results of the four checks + gate outcome |
| `state.json` | all phases | phase, iteration, target output, FINISH style |

The deliverable itself is at `3. output/<name>.md`. `.loop/` is derived and deletable;
the deliverable and the `2. wiki` return leg are not.

## Why artifacts don't live in `2. wiki`

`loop_check.py`'s `check_provenance` scans every `.md` under `2. wiki` and flags any without a
`source-refs` field. Putting `plan.md` or `critique.md` there would trigger a false PROV finding
on every run. The dot-folder `.loop/` sits alongside `.pageindex/` and `.vector/`: derived, hidden,
rebuildable.

## Manual mode

Each phase can be called on its own: `/loop-plan`, `/loop-act`, `/loop-review`, `/loop-verify`.
Useful for step-by-step demonstration and for redoing one phase without running the whole chain.
