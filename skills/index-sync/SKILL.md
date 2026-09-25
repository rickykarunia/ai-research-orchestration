---
name: index-sync
description: Regenerate ~/AI-INDEX.md, the cross-vault routing registry, by harvesting the routing front-matter from every project vault's AGENTS.md/CLAUDE.md. Use when adding a new vault, retiring or re-tiering an existing one, changing a vault's route-when, or when routing feels stale. Triggers on /index-sync, "sync vault index", "regen AI-INDEX", "register new vault".
---

# index-sync — regenerate the cross-vault routing registry

`~/AI-INDEX.md` is **DERIVED**, never hand-written. Source of truth = the routing front-matter
block in each vault's `AGENTS.md` (or `CLAUDE.md`). This skill harvests it and rewrites the
registry. Part of the orchestration system; behavior rules live in `~/AI-RULES.md`.

`<kit-root>` = the ai-research-orchestration clone (the folder containing `scripts/`; this skill
folder is `<kit-root>/skills/index-sync`).

## Regenerate the registry

Run:

```bash
py -3.13 "<kit-root>/scripts/index_sync.py"
```

If the `py` launcher isn't available, use plain `python`. Add `--dry` to print without writing:

```bash
py -3.13 "<kit-root>/scripts/index_sync.py" --dry
```

After running, read `~/AI-INDEX.md` back, confirm the active vault count matches expectations,
and report what changed.

## Registering a new vault

1. Add a routing front-matter block at the very top of that vault's `AGENTS.md` (create a thin
   one if it doesn't have one):

```yaml
---
# === routing block (blok routing) - harvested by /index-sync into ~/AI-INDEX.md. Do not remove. ===
vault: <vault-name>
path: Projects/<...>
domain: <one-phrase domain>
route-when: [<up to 5 trigger keywords>]
entry: "<opening file/folder, e.g. 2. wiki/index.md>"
tier: active            # active | dormant | archive
loop: true              # true if it runs raw->wiki->output; false otherwise
rules: [AGENTS.md, CLAUDE.md]
---
```

The comment line must contain the literal phrase `blok routing` somewhere in the front-matter
block — that's the marker `index_sync.py` scans for. Keep it exactly as shown; it isn't
translated because the parser matches on it.

2. Add a one-line pointer below the front matter (so per-workspace tools also see it):

```
> **Orchestration:** cross-project behavior in `~/AI-RULES.md`; cross-vault routing in `~/AI-INDEX.md`. Precedence: session instructions > this file > AI-RULES. This project's own file wins on conflict.
```

3. Run the regen (above). The vault appears in the registry.

## Retiring / re-tiering

Change `tier` in the vault's front matter (`active`→`dormant`/`archive`), then regen. The
registry only routes tier `active` by default.

## Rules

- Don't hand-edit `~/AI-INDEX.md`; any edit is overwritten on the next regen. Change the vault, then sync.
- `route-when` should stay to about 5 keywords max, to keep the registry thin.
- The scanner skips the `1. raw`, `2. wiki`, `3. output`, `3. draft`, `graphify-out`, backup, `.git`,
  `.obsidian` folders. The routing block must sit in the vault root's rules file, not inside those folders.
- If a vault has both AGENTS.md and CLAUDE.md carrying a routing block, the first one found wins
  (dedup by `vault`). Keep the block in one file only.
