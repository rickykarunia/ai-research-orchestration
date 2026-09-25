# Contract for the `3. output/<name>.md` draft

## Front matter

```yaml
---
type: deliverable
status: draft
loop-slug: <slug>
iteration: <n>
claims-from: ".loop/<slug>/plan.md"
updated: YYYY-MM-DD
---
```

## Claim markers

Every claim-bearing sentence from the map carries its ID marker at the end of the sentence.

```markdown
The 2021 reform raised the dividend payout ratio at listed firms. [K1]
The increase wasn't matched by an improvement in profitability. [K2]
```

An unsourced claim is written as-is:

```markdown
The effect on private companies can't yet be assessed. [NEEDS SOURCE]
```

The `[K<n>]` marker can be stripped at FINISH if the user wants a clean manuscript. Before that,
the marker must stay, since REVIEW and VERIFY read it.

## Required closing section

```markdown
## Source trace

| Claim | Wiki note | Raw |
|---|---|---|
| K1 | `2. wiki/<note>.md` | `1. raw/<file>.md` |

## Remaining gaps

- G1: <gap> - <impact>
```

This section may move to an appendix at FINISH, but must not be deleted while the loop is running.

## Prohibited

- No claim without an ID or without `[NEEDS SOURCE]`.
- No long quotes from `1. raw`. Synthesis lives in the wiki, not copy-pasted from the source.
- No extra draft files in `3. output/`. Working artifacts stay in `.loop/`.
