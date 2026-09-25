# `plan.md` format

Written by the `loop-plan` phase to `<vault>/.loop/<slug>/plan.md`.

```markdown
# Deliverable plan: <Deliverable Name>

- Vault: `<vault-name>`
- Target output: `3. output/<name>.md`
- PLAN iteration: <n>
- Date: <YYYY-MM-DD>

## Thesis

<One sentence. The main claim this deliverable carries.>

## Chapter outline

1. <Chapter title> - claims K1, K2
2. <Chapter title> - claim K3
3. <Chapter title> - claims K4, K5

## Peta klaim

Full chain required. A broken chain gets `[NEEDS SOURCE]`, never guessed.

| ID | Claim | `2. wiki` note | `1. raw` file | Source section | Confidence |
|---|---|---|---|---|---|
| K1 | <one-sentence claim> | `2. wiki/<note>.md` | `1. raw/<file>.md` | <section / page / clause> | Certain |
| K2 | <claim> | `2. wiki/<note>.md` | `1. raw/<file>.md` | <section> | Likely |
| K3 | <claim> | `2. wiki/<note>.md` | [NEEDS SOURCE] | - | Guessing |

## Open gaps

| ID | Gap | Impact if the output ships anyway |
|---|---|---|
| G1 | <what has no source yet> | <concrete risk> |

## Decisions needed from the user

1. <a question evidence can't answer, only the user knows>

## Verification

The deliverable is considered passing when:

1. `loop_check.py --vault <vault>` exits with no PROV finding.
2. Every claim in the output has a row in this claim map.
3. Every `[NEEDS SOURCE]` in the output has a gap row above, or has been closed.
```

## Content rules

- The `## Peta klaim` heading is the literal section name `loop_resume.py` checks for
  (`plan.md missing or lacks a Peta klaim section`) — keep it verbatim.
- One table row = one claim. A compound claim gets split.
- The "Source section" column must be specific: a clause number, a page, or a subsection title.
  "General" is not enough.
- A `Guessing`-confidence claim may enter the output only if flagged in its body.
