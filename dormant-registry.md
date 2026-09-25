# Dormant registry

Vaults outside `~/Projects/` are not harvested by `scripts/index_sync.py`. List them here to
include them in `~/AI-INDEX.md`.

Format: one row per vault, between the `data` markers below, four fields separated by `|`
(no leading or trailing pipe, no header row):

```
vault | path | tier | domain
```

Example (kept outside the markers, so it is never harvested):

```
old-thesis | D:/archive/old-thesis | dormant | finished thesis, kept for reference
```

Every line between the markers that contains `|` is read as a vault, so put nothing else there.
A vault already harvested from `~/Projects/` wins over a row with the same name here.

<!-- data -->
<!-- /data -->
