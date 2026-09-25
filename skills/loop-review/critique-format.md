# `critique.md` format

Written by the `loop-review` phase to `<vault>/.loop/<slug>/critique.md`. Each iteration
overwrites the previous file. Findings already fixed are not repeated.

```markdown
# Draft critique: <Deliverable Name>

- Iteration: <n>
- Reviewer: <subagent used>
- Putusan: LULUS | ULANG ACT
- Date: <YYYY-MM-DD>

## Summary

| Level | Count |
|---|---|
| BLOCKER | <n> |
| MAJOR | <n> |
| MINOR | <n> |

## Findings index

1. [T1] <short title> - BLOCKER
2. [T2] <short title> - MAJOR

## Findings

### T1 - <short title>

- Level: BLOCKER
- Confidence: CONFIRMED
- Location: `3. output/<name>.md:<line>`
- Related claim: K3
- Evidence: <quote from the draft> vs. `2. wiki/<note>.md`, which only states <what>
- Problem: <one sentence>
- Fix: <what to do in the next ACT iteration>

### T2 - <short title>

- Level: MAJOR
- Confidence: UNVERIFIED
- Couldn't check: <what and why>
...

## Could not verify

- <what the reviewer couldn't confirm, and why>
```

The `Putusan:` line and its `LULUS | ULANG ACT` values are the literal tokens `loop_resume.py`
parses (`^\s*-\s*Putusan:\s*(LULUS|ULANG ACT|GAGAL)\s*$`) — keep them verbatim (`LULUS` = pass,
`ULANG ACT` = redo ACT, `GAGAL` = fail).

## Finding levels

| Level | Meaning |
|---|---|
| BLOCKER | Unsourced claim, claim exceeding its source, or a skipped wiki link in the chain. The draft can't proceed. |
| MAJOR | A logical leap, dishonest confidence, or a chapter that doesn't support the thesis. Must be fixed. |
| MINOR | Style, ordering, redundancy. Can be deferred to FINISH. |
