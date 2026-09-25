# `verify.md` format

Written by the `loop-verify` phase to `<vault>/.loop/<slug>/verify.md`.

```markdown
# Verification: <Deliverable Name>

- Iteration: <n>
- Putusan: LULUS | GAGAL
- Date: <YYYY-MM-DD>

## Check results

| Check | Content | Result |
|---|---|---|
| A | Draft claim markers match the claim map | LULUS / GAGAL |
| B | Every `[NEEDS SOURCE]` has a gap row | LULUS / GAGAL |
| C | Return leg written to `2. wiki` | LULUS / GAGAL |
| D | `loop_check.py` clean | LULUS / GAGAL |

## Check A - claim markers

- IDs in the draft not in the map: <list, or "none">
- IDs in the map not used by the draft: <list, or "none">

## Check B - gaps

- `[NEEDS SOURCE]` with no gap row: <list, or "none">

## Check C - return leg

- Note written: `2. wiki/<note>.md`
- Content: <new gaps / decisions / open questions>

## Check D - mechanical gate

```
<the decisive loop_check.py output line, not the whole log>
```

Exit code: <n>

## Limit of this gate

Check D proves the traceability chain exists. It does not prove claim content matches its
source. Content matching is tested by `critique.md` iteration <n>.

## Carried into FINISH

- <MINOR findings from the critique not yet fixed>
```

`LULUS` = pass, `GAGAL` = fail — the literal tokens `loop_resume.py` parses from the `Putusan:`
line; keep them verbatim.
