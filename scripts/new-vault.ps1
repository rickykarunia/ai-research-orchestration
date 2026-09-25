<#
.SYNOPSIS
  Scaffold a new vault/project in line with AI-RULES + the index_sync.py harvester.

.DESCRIPTION
  Automates the manual steps in the README ("Quick start"):
  create the loop folders, write AGENTS.md (routing front matter filled in) + a thin CLAUDE.md,
  create a wikilinked entry file + Project Context note + root .obsidian config, then regenerate AI-INDEX.md.

  Name-derived fields (vault, path, entry, title) are filled in automatically. Project-specific
  fields (domain, route-when) are filled from parameters, or written as a placeholder for you to complete.

.EXAMPLE
  .\new-vault.ps1 my-research-project

.EXAMPLE
  .\new-vault.ps1 my-project -Domain "supply chain review" -RouteWhen "supply chain, logistics, supplier audit"

.EXAMPLE
  .\new-vault.ps1 my-project -Type kajian -DependsOn "regulation-vault,related-standard-vault"

.EXAMPLE
  .\new-vault.ps1 my-project -NoRetrieval -DryRun

.EXAMPLE
  .\new-vault.ps1 draft-oped -NoLoop -NoClaude -DryRun
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory, Position = 0)]
  [string]$Name,
  [string]$Domain,
  [string]$RouteWhen,
  [string]$DependsOn,
  [string]$Root = (Join-Path $HOME "Projects"),
  [ValidateSet('paper','kajian','regulasi','app','saas','ideation','equity','oped','generic')]
  [string]$Type = 'generic',
  [string[]]$Skills,
  [switch]$NoRetrieval,
  [switch]$NoLoop,
  [switch]$NoClaude,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$HomeDir     = $HOME
$Today       = (Get-Date).ToString("yyyy-MM-dd")
$KitRoot     = Split-Path -Parent $PSScriptRoot
$Scripts     = $PSScriptRoot
$ProjectsDir = Join-Path $HomeDir "Projects"
$TemplateDir = Join-Path $KitRoot "templates"

if ($Name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
  throw "Vault name must be kebab-case (lowercase letters, digits, '-'). Got: '$Name'"
}

$VaultDir = [System.IO.Path]::GetFullPath((Join-Path $Root $Name))
if ((Test-Path $VaultDir) -and -not $DryRun) {
  throw "Folder already exists: $VaultDir (won't overwrite). Delete it first or pick another name."
}

# Prefix match needs a separator: without it "Projects-archive" would pass as "under Projects".
function Test-UnderDir($child, $parent) {
  $p = $parent.TrimEnd('\') + '\'
  return $child.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)
}

$UnderHome   = Test-UnderDir $VaultDir $HomeDir
$UnderProjects = Test-UnderDir $VaultDir $ProjectsDir

$Title = ($Name -split '-' | ForEach-Object { if ($_) { $_.Substring(0,1).ToUpper() + $_.Substring(1) } }) -join ' '
# `path` front matter is relative to home when possible; outside home it uses the absolute path (don't blindly chop it).
$RelPath = if ($UnderHome) { $VaultDir.Substring($HomeDir.TrimEnd('\').Length + 1) -replace '\\','/' } else { $VaultDir }
$LoopVal  = if ($NoLoop) { "false" } else { "true" }
$EntryRel = "2. wiki/00 - Index $Title.md"

if ($RouteWhen) {
  $rw = "[" + (($RouteWhen -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ', ') + "]"
} else {
  $rw = "[<trigger 1>, <trigger 2>, <trigger 3>]"
}
if ($DependsOn) {
  $dep = "[" + (($DependsOn -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ', ') + "]"
} else {
  $dep = $null
}
$dom = if ($Domain) { $Domain } else { "<one sentence: what this vault is for>" }

# Project-type -> default skill map. obsidian-cli is added to EVERY type so the "2. wiki"
# folder is immediately navigable via search/backlinks/tags. humanizer is added to EVERY type as
# the prose floor. loop-engine is added only when the vault uses the raw->wiki->output loop.
# -Skills always overrides this manually.
$skillMap = @{
  paper    = @('academic-paper','academic-paper-reviewer','deep-research')
  kajian   = @('deep-research','academic-paper')
  regulasi = @('deep-research')
  app      = @('superpowers:brainstorming','superpowers:systematic-debugging','superpowers:test-driven-development')
  saas     = @('superpowers:brainstorming','superpowers:writing-plans','superpowers:systematic-debugging')
  ideation = @('mattpocock-skills:grilling','superpowers:brainstorming','mattpocock-skills:prototype')
  equity   = @('equity-research','financial-analysis','market-researcher')
  oped     = @('deep-research')
  generic  = @('deep-research')
}
$noteMap = @{
  paper    = 'Research/write -> academic-paper (+ deep-research for evidence). Review a draft -> academic-paper-reviewer. Assemble wiki->output -> loop-engine. Final prose -> humanizer.'
  kajian   = 'Retrieval + synthesis -> deep-research. Narrative draft -> academic-paper. Assemble wiki->output -> loop-engine. Final prose -> humanizer.'
  regulasi = 'Review sources/regulations -> deep-research (never from memory). Assemble wiki->output -> loop-engine. Final prose -> humanizer.'
  app      = 'Build a feature -> superpowers:brainstorming first, then test-driven-development. Bug -> systematic-debugging. Hold off on gstack until there is a deploy target.'
  saas     = 'Big plan -> superpowers:writing-plans. Build -> brainstorming + TDD. Bug -> systematic-debugging. Once deploy starts, add gstack (/review /ship /qa /canary).'
  ideation = 'Stress-test an idea -> mattpocock-skills:grilling. Explore -> superpowers:brainstorming. Quick prototype -> mattpocock-skills:prototype.'
  equity   = 'Analysis -> equity-research + financial-analysis. Sector/theme -> market-researcher. Narrative -> humanizer.'
  oped     = 'Facts -> deep-research. Assemble -> loop-engine. Prose -> humanizer.'
  generic  = 'Retrieve sources first (deep-research), never from memory. Assemble wiki->output -> loop-engine. Final prose -> humanizer.'
}
if ($Skills) { $skillsArr = $Skills }
else {
  $skillsArr = @($skillMap[$Type]) + @('obsidian-cli','humanizer')
  if (-not $NoLoop) { $skillsArr += 'loop-engine' }
}
# A vault without a loop has no wiki->output to assemble; drop the loop-engine mention from the note.
if ($NoLoop) {
  $noteMap[$Type] = $noteMap[$Type].Replace('Assemble wiki->output -> loop-engine. ','').Replace('Assemble -> loop-engine. ','')
}
$sk = "[" + ($skillsArr -join ', ') + "]"
$SkillDefault = $noteMap[$Type]
$EntryName = [System.IO.Path]::GetFileName($EntryRel)
$withRetrieval = (-not $NoLoop) -and (-not $NoRetrieval)

$CitationPresets = [ordered]@{
  apa = "apa.csl"
  ieee = "ieee.csl"
  "chicago-author-date" = "chicago-author-date.csl"
  "chicago-notes-bibliography" = "chicago-notes-bibliography.csl"
}
$CitationDefault = "apa"
$CitationTemplateDir = Join-Path $TemplateDir "csl"
$CitationSourcePaths = @($CitationPresets.Values | ForEach-Object { Join-Path $CitationTemplateDir $_ })
foreach ($citationSource in $CitationSourcePaths) {
  if (-not (Test-Path -LiteralPath $citationSource -PathType Leaf)) {
    throw "CSL preset not found: $citationSource"
  }
}

function Get-MarkdownTemplateBlock($path) {
  $raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $path
  $m = [regex]::Match($raw, '(?s)```markdown\r?\n(.*?)\r?\n```')
  if (-not $m.Success) {
    throw "Markdown template block not found: $path"
  }
  return $m.Groups[1].Value
}

function Replace-LineByPrefix($text, $prefix, $replacement) {
  $lines = $text -split "`r?`n"
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i].StartsWith($prefix)) {
      $lines[$i] = $replacement
      break
    }
  }
  return ($lines -join "`r`n")
}

function Replace-LineContaining($text, $needle, $replacement) {
  $lines = $text -split "`r?`n"
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Contains($needle)) {
      $lines[$i] = $replacement
      break
    }
  }
  return ($lines -join "`r`n")
}

function Remove-LineContaining($text, $needle) {
  $lines = $text -split "`r?`n"
  $kept = foreach ($line in $lines) {
    if (-not $line.Contains($needle)) { $line }
  }
  return ($kept -join "`r`n")
}

function Build-AgentsTemplate() {
  $t = Get-MarkdownTemplateBlock (Join-Path $TemplateDir "AGENTS - template.md")
  $t = Replace-LineByPrefix $t "vault:" "vault: $Name"
  $t = Replace-LineByPrefix $t "path:" "path: $RelPath"
  $t = Replace-LineByPrefix $t "domain:" "domain: $dom"
  $t = Replace-LineByPrefix $t "route-when:" "route-when: $rw"
  if ($dep) {
    $t = Replace-LineByPrefix $t "depends-on:" "depends-on: $dep"
  } else {
    $t = Remove-LineContaining $t "depends-on:"
  }
  $t = Replace-LineByPrefix $t "entry:" "entry: `"$EntryRel`""
  $t = Replace-LineByPrefix $t "loop:" "loop: $LoopVal"
  $t = Replace-LineByPrefix $t "skills:" "skills: $sk"
  $t = Replace-LineByPrefix $t "# AGENTS.md" "# AGENTS.md - $Title"
  $t = Replace-LineByPrefix $t 'cd "<vault-dir>"' "cd `"$VaultDir`""
  $t = Replace-LineContaining $t "> <e.g. paper:" "> $SkillDefault"
  $t = Replace-LineContaining $t "- <YYYY-MM-DD>: Vault created." "- ${Today}: Vault created via new-vault.ps1. Registered in AI-INDEX via /index-sync."
  if ($NoLoop) {
    $t = Replace-LineContaining $t "## 1. Role in the loop" "## 1. Vault structure"
    $t = Remove-LineContaining $t '| `1. raw/` |'
    $t = Remove-LineContaining $t '| `<.pageindex/ or .vector/ or graphify-out/>` |'
    $t = Remove-LineContaining $t '| `3. output/` |'
    $t = Remove-LineContaining $t '| `.loop/` |'
    $t = Remove-LineContaining $t '| `loop-engine` |'
    $t = Replace-LineContaining $t "2. Make sure the derived layers are current" "2. Use whatever explicit sources are available; don't fill claims from memory."
    $t = Remove-LineContaining $t "5. Return-leg:"
  }
  return $t
}

function Build-ClaudeTemplate() {
  $t = Get-MarkdownTemplateBlock (Join-Path $TemplateDir "CLAUDE - template.md")
  $t = Replace-LineByPrefix $t "# " "# $Title"
  return $t
}

function Build-ProjectContextTemplate() {
  $t = Get-MarkdownTemplateBlock (Join-Path $TemplateDir "Project Context - template.md")
  $t = Replace-LineByPrefix $t "updated:" "updated: $Today"
  $t = Replace-LineContaining $t "**Project:**" "**Project:** $Title"
  $t = Replace-LineContaining $t "- [[00 - Index <Vault>]]" "- [[00 - Index $Title]]"
  if ($NoLoop) {
    $t = Replace-LineContaining $t '| G-001 | NEEDS SOURCE | Add an initial primary source to `1. raw/`' "| G-001 | NEEDS SOURCE | Add an explicit source before a substantive claim is written as fact. |"
  }
  return $t
}

function Build-C2LogTemplate() {
  $t = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TemplateDir "C2 Log - template.md")
  $t = Replace-LineByPrefix $t "updated:" "updated: $Today"
  $t = Replace-LineByPrefix $t "# C2 Log" "# C2 Log - $Title"
  return $t
}

function Get-ObsidianCorePlugins() {
  return @'
{
  "file-explorer": true,
  "global-search": true,
  "switcher": true,
  "graph": true,
  "backlink": true,
  "canvas": true,
  "outgoing-link": true,
  "tag-pane": true,
  "footnotes": false,
  "properties": true,
  "page-preview": true,
  "daily-notes": true,
  "templates": true,
  "note-composer": true,
  "command-palette": true,
  "slash-command": false,
  "editor-status": true,
  "bookmarks": true,
  "markdown-importer": false,
  "zk-prefixer": false,
  "random-note": false,
  "outline": true,
  "word-count": true,
  "slides": false,
  "audio-recorder": false,
  "workspaces": false,
  "file-recovery": true,
  "publish": false,
  "sync": true,
  "bases": true,
  "webviewer": false
}
'@
}

function Build-ObsidianWorkspace() {
  $entryJson = $EntryRel.Replace('\','/')
  return @"
{
  "main": {
    "id": "main",
    "type": "split",
    "children": [
      {
        "id": "main-tabs",
        "type": "tabs",
        "children": [
          {
            "id": "entry-note",
            "type": "leaf",
            "state": {
              "type": "markdown",
              "state": {
                "file": "$entryJson",
                "mode": "source",
                "source": false
              },
              "icon": "lucide-file",
              "title": "$EntryName"
            }
          }
        ]
      }
    ],
    "direction": "vertical"
  },
  "left": {
    "id": "left",
    "type": "split",
    "children": [
      {
        "id": "left-tabs",
        "type": "tabs",
        "children": [
          {
            "id": "files",
            "type": "leaf",
            "state": {
              "type": "file-explorer",
              "state": {
                "sortOrder": "alphabetical",
                "autoReveal": false,
                "showSearch": false,
                "searchQuery": ""
              },
              "icon": "lucide-folder-closed",
              "title": "Files"
            }
          },
          {
            "id": "search",
            "type": "leaf",
            "state": {
              "type": "search",
              "state": {
                "query": "",
                "matchingCase": false,
                "explainSearch": false,
                "collapseAll": false,
                "extraContext": false,
                "sortOrder": "alphabetical"
              },
              "icon": "lucide-search",
              "title": "Search"
            }
          }
        ]
      }
    ],
    "direction": "horizontal",
    "width": 300
  },
  "right": {
    "id": "right",
    "type": "split",
    "children": [
      {
        "id": "right-tabs",
        "type": "tabs",
        "children": [
          {
            "id": "backlinks",
            "type": "leaf",
            "state": {
              "type": "backlink",
              "state": {
                "file": "$entryJson",
                "collapseAll": false,
                "extraContext": false,
                "sortOrder": "alphabetical",
                "showSearch": false,
                "searchQuery": "",
                "backlinkCollapsed": false,
                "unlinkedCollapsed": true
              },
              "icon": "links-coming-in",
              "title": "Backlinks"
            }
          },
          {
            "id": "outgoing-links",
            "type": "leaf",
            "state": {
              "type": "outgoing-link",
              "state": {
                "file": "$entryJson",
                "linksCollapsed": false,
                "unlinkedCollapsed": true
              },
              "icon": "links-going-out",
              "title": "Outgoing links"
            }
          },
          {
            "id": "tags",
            "type": "leaf",
            "state": {
              "type": "tag",
              "state": {
                "sortOrder": "frequency",
                "useHierarchy": true,
                "showSearch": false,
                "searchQuery": ""
              },
              "icon": "lucide-tags",
              "title": "Tags"
            }
          }
        ]
      }
    ],
    "direction": "horizontal",
    "width": 300,
    "collapsed": true
  },
  "active": "entry-note",
  "lastOpenFiles": [
    "$entryJson",
    "2. wiki/01 - Project Context.md",
    "2. wiki/_C2 Log.md"
  ]
}
"@
}

function Build-CorpusTemplate() {
  $t = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TemplateDir "retrieval-per-vault\corpus.py")
  $t = Replace-LineByPrefix $t 'WIKI_NOTE   = ' "WIKI_NOTE   = `"$EntryName`""
  $t = $t.Replace('__AIO_KIT__', $KitRoot)
  return $t
}

function Build-VCorpusTemplate() {
  $t = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TemplateDir "retrieval-per-vault\vcorpus.py")
  $t = $t.Replace('__AIO_KIT__', $KitRoot)
  return $t
}

function Get-RetrievalFile($name) {
  $t = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TemplateDir "retrieval-per-vault\$name")
  $t = $t.Replace('__AIO_KIT__', $KitRoot)
  return $t
}

# Remove one Markdown section: from the heading to the next heading at the same level.
function Remove-Section($text, $heading) {
  $lines = $text -split "`r?`n"
  $out = New-Object System.Collections.Generic.List[string]
  $skip = $false
  foreach ($line in $lines) {
    if ($line -eq $heading) { $skip = $true; continue }
    if ($skip -and $line.StartsWith("## ")) { $skip = $false }
    if (-not $skip) { $out.Add($line) }
  }
  return ($out -join "`r`n")
}

function Build-ReadmeTemplate() {
  $t = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TemplateDir "README - template.md")
  $t = [regex]::Replace($t, '(?s)\A<!--.*?-->\r?\n', '')
  $t = $t.Replace('__TITLE__', $Title).
          Replace('__VAULT__', $Name).
          Replace('__VAULTDIR__', $VaultDir).
          Replace('__DOMAIN__', $dom).
          Replace('__ENTRY__', $EntryRel)
  if (-not $withRetrieval) {
    foreach ($h in "## Commands","## Retrieval: flat rules","## Batch synthesis") { $t = Remove-Section $t $h }
    $t = $t.Replace('2. Ingest: `.\rag.ps1 ingest` for `.md`, `.\rag.ps1 ingest -Page` for PDF.', '2. The retrieval wrapper isn''t installed in this vault; use whatever explicit sources are available.')
    $t = [regex]::Replace($t, '(?m)^3\. Per-document synthesis:.*(\r?\n   .*)*', '3. Quote directly from the source, never from memory.')
  }
  return $t
}

# `source-refs` is required on every "2. wiki" note (loop_check.py check_provenance, AI-RULES sec. 6).
# The index note hasn't cited any raw source yet -> an empty list, honest and passes the check.
$entryTpl = @'
---
type: index
source-refs: []
confidence: Certain
updated: __TODAY__
---

# 00 - Index __TITLE__

Vault entry point. Link wiki notes from here.

- [[01 - Project Context]]
- [[_C2 Log]]
'@

# Free-text user tokens (__TODAY__/__TITLE__) used for templates still embedded here.
function Expand-Tpl($t) {
  $t.Replace('__TITLE__', $Title).
     Replace('__TODAY__', $Today)
}

$agents = Build-AgentsTemplate
$claude = Build-ClaudeTemplate
$entry  = Expand-Tpl $entryTpl
if ($withRetrieval) {
  $entry = $entry.TrimEnd() + "`r`n`r`n" + @'
## Active Retrieval Decisions

- [Certain] Flat routing by extension: `.pdf` to `corpus.py`/PageIndex (`-Page`), `.md` to `vcorpus.py`. No content judgment, no file in two indexes.
- [Certain] A confidential or unstructured PDF is converted via `.\rag.ps1 convert`; the original PDF is parked in `1. raw/_source-pdf/`, outside both engines' sweep.
- [Certain] `ask-file` and `ask-essential` write automatically to `tmp/retrieval-packets/` and `2. wiki/_terra-drafts/`, append-only. Promotion to a wiki note stays manual.
- [Certain] Cross-document synthesis (`ask`, `synth`) writes no draft. Cross-source claims are written by a human.
- [Certain] A thematic note is created when an output needs it, not ahead of time. `2. wiki/` is a grounding base, not a stockpile of finished conclusions.
- [Certain] Terra assembles the vector result for every `.md` in `1. raw/` EXCEPT those listed as confidential in `1. raw/_terra-tolak.txt` (deny-list). A confidential file goes through the mechanical path with no API.

## PDF Corpus (PageIndex)

<!-- corpus:docs -->
| # | PDF name | doc_id | Ingested on |
|---|---|---|---|
| - | _(empty corpus)_ | - | - |
<!-- /corpus:docs -->
'@ + "`r`n"
}
$context = Build-ProjectContextTemplate
$c2log = Build-C2LogTemplate
$obsidianApp = "{}"
$obsidianAppearance = "{}"
$obsidianCorePlugins = Get-ObsidianCorePlugins
$obsidianWorkspace = Build-ObsidianWorkspace
$readme = Build-ReadmeTemplate
if ($withRetrieval) {
  $corpus = Build-CorpusTemplate
  $vcorpus = Build-VCorpusTemplate
  $rag = Get-RetrievalFile "rag.ps1"
  $askStarter = Get-RetrievalFile "ask-batch-starter.md"
}

if ($DryRun) {
  Write-Host "DRY RUN -- no file written." -ForegroundColor Yellow
  Write-Host "Vault dir : $VaultDir"
  Write-Host "path (rel): $RelPath"
  Write-Host "entry     : $EntryRel"
  Write-Host "loop      : $LoopVal | under Projects: $UnderProjects"
  Write-Host "type      : $Type | skills: $sk"
  Write-Host "retrieval : $(if ($withRetrieval) { 'corpus.py + vcorpus.py' } else { 'skip' })"
  Write-Host "citation  : $(if (-not $NoLoop) { 'default ' + $CitationDefault + ' | presets: ' + ($CitationPresets.Keys -join ', ') } else { 'skip (NoLoop, no 3. output)' })"
  Write-Host "`n--- AGENTS.md ---" -ForegroundColor Cyan
  Write-Host $agents
  if (-not $NoClaude) { Write-Host "`n--- CLAUDE.md ---" -ForegroundColor Cyan; Write-Host $claude }
  Write-Host "`n--- $EntryRel ---" -ForegroundColor Cyan; Write-Host $entry
  Write-Host "`n--- 2. wiki/01 - Project Context.md ---" -ForegroundColor Cyan; Write-Host $context
  Write-Host "`n--- 2. wiki/_C2 Log.md ---" -ForegroundColor Cyan; Write-Host $c2log
  Write-Host "`n--- .obsidian/core-plugins.json ---" -ForegroundColor Cyan; Write-Host $obsidianCorePlugins
  Write-Host "`n--- README.md ---" -ForegroundColor Cyan; Write-Host $readme
  if ($withRetrieval) {
    Write-Host "`n--- supporting files ---" -ForegroundColor Cyan
    Write-Host "rag.ps1, manifest.json (empty), tmp\ask-batch\00-example-packet.md"
  }
  if (-not $NoLoop) { Write-Host ".loop\.gitkeep" }
  if ($withRetrieval) {
    Write-Host "`n--- corpus.py (CONFIG) ---" -ForegroundColor Cyan
    Write-Host (($corpus -split "`r?`n" | Select-Object -First 45) -join "`n")
    Write-Host "`n--- vcorpus.py (CONFIG) ---" -ForegroundColor Cyan
    Write-Host (($vcorpus -split "`r?`n" | Select-Object -First 24) -join "`n")
  }
  if (-not $NoLoop) {
    Write-Host "`n--- CSL presets ---" -ForegroundColor Cyan
    Write-Host (($CitationPresets.Values | ForEach-Object { "3. output\csl\$_" }) -join "`n")
  }
  return
}

New-Item -ItemType Directory -Force $VaultDir | Out-Null
New-Item -ItemType Directory -Force (Join-Path $VaultDir ".obsidian") | Out-Null
if (-not $NoLoop) {
  foreach ($d in "1. raw","2. wiki","3. output") { New-Item -ItemType Directory -Force (Join-Path $VaultDir $d) | Out-Null }
  $citationDir = Join-Path $VaultDir "3. output\csl"
  New-Item -ItemType Directory -Force $citationDir | Out-Null
  foreach ($citationFile in $CitationPresets.Values) {
    Copy-Item -LiteralPath (Join-Path $CitationTemplateDir $citationFile) -Destination (Join-Path $citationDir $citationFile) -Force
  }
  # Park the original PDF produced by `rag.ps1 convert`. A subfolder keeps it invisible to
  # both engines' ingest sweep (both use non-recursive os.listdir), so a confidential PDF never gets sent.
  New-Item -ItemType Directory -Force (Join-Path $VaultDir "1. raw\_source-pdf") | Out-Null
} else {
  New-Item -ItemType Directory -Force (Join-Path $VaultDir "2. wiki") | Out-Null
}

# UTF-8 WITHOUT BOM: the Python harvester checks text.startswith("---"); a BOM (from
# Set-Content -Encoding utf8 on PS 5.1) breaks that check.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8NoBom($path, $content) { [System.IO.File]::WriteAllText($path, $content, $Utf8NoBom) }

Write-Utf8NoBom (Join-Path $VaultDir "AGENTS.md") $agents
if (-not $NoClaude) { Write-Utf8NoBom (Join-Path $VaultDir "CLAUDE.md") $claude }
Write-Utf8NoBom (Join-Path $VaultDir $EntryRel) $entry
Write-Utf8NoBom (Join-Path $VaultDir "2. wiki\01 - Project Context.md") $context
Write-Utf8NoBom (Join-Path $VaultDir "2. wiki\_C2 Log.md") $c2log
Write-Utf8NoBom (Join-Path $VaultDir ".obsidian\app.json") $obsidianApp
Write-Utf8NoBom (Join-Path $VaultDir ".obsidian\appearance.json") $obsidianAppearance
Write-Utf8NoBom (Join-Path $VaultDir ".obsidian\core-plugins.json") $obsidianCorePlugins
Write-Utf8NoBom (Join-Path $VaultDir ".obsidian\workspace.json") $obsidianWorkspace
Write-Utf8NoBom (Join-Path $VaultDir "README.md") $readme
if ($withRetrieval) {
  Write-Utf8NoBom (Join-Path $VaultDir "corpus.py") $corpus
  Write-Utf8NoBom (Join-Path $VaultDir "vcorpus.py") $vcorpus
  Write-Utf8NoBom (Join-Path $VaultDir "rag.ps1") $rag
  # corpus.py builds its own manifest.json on ingest; an empty file is created so the catalog is visible from the start.
  Write-Utf8NoBom (Join-Path $VaultDir "manifest.json") "{}"
  # Terra deny-list for the vector path. Default synthesis: every .md in '1. raw/' that is
  # NOT listed here is assembled by Terra and then verified by kimi-k3 into the wiki.
  # List ONLY confidential files. Backward compat: if this file doesn't exist but
  # _terra-boleh.txt does, the old allow-list behavior still applies.
  $terraDeny = @(
    "# Terra deny-list: .md files in '1. raw/' that are CONFIDENTIAL -- must never be sent to an API.",
    "# One file name per line, as written (case-insensitive). Lines starting with # are ignored.",
    "#",
    "# As long as an .md file EXISTS in '1. raw/' and is NOT listed here, it is synthesized",
    "# straight into a terra-draft (vcorpus.py) and then verified by kimi-k3 into the wiki (promote-terra.py).",
    "# Register ONLY confidential documents: case files, internal minutes, personal data.",
    "# A listed file -> verbatim passage with no API; promote-terra rejects it (manual lane).",
    ""
  ) -join "`r`n"
  Write-Utf8NoBom (Join-Path $VaultDir "1. raw\_terra-tolak.txt") $terraDeny
  # Batch questions use ask-batch.ps1 in the control plane; the vault only stores the question files.
  New-Item -ItemType Directory -Force (Join-Path $VaultDir "tmp\ask-batch") | Out-Null
  Write-Utf8NoBom (Join-Path $VaultDir "tmp\ask-batch\00-example-packet.md") $askStarter
}
if (-not $NoLoop) {
  New-Item -ItemType Directory -Force (Join-Path $VaultDir ".loop") | Out-Null
  Write-Utf8NoBom (Join-Path $VaultDir ".loop\.gitkeep") ""
}

Write-Host "Vault created: $VaultDir" -ForegroundColor Green

$idx = Join-Path $Scripts "index_sync.py"
$lc  = Join-Path $Scripts "loop_check.py"

if ($UnderProjects) {
  py -3.13 $idx
  # A native exit code doesn't trigger ErrorActionPreference=Stop; check it manually so a
  # failure isn't reported as a false success.
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "index_sync.py failed (exit $LASTEXITCODE). The vault is NOT registered in AI-INDEX.md yet. Fix it, then rerun: py -3.13 '$idx'"
  } else {
    Write-Host "Registered in AI-INDEX.md." -ForegroundColor Green
  }
} else {
  Write-Warning "Vault is OUTSIDE ~/Projects -> not auto-harvested. Register it manually in dormant-registry.md if you want it routed to."
}

Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Fill in the placeholders in AGENTS.md (domain/route-when/not-when if not already set via parameters)."
Write-Host "  2. Fill in 2. wiki\01 - Project Context.md: problem, RQ, distinctive angle, scope, required sources, neighbor vault boundary."
Write-Host "  3. Open Obsidian from the vault root, not from 2. wiki, so links to raw/wiki/output stay one graph."
if (-not $NoLoop) {
  Write-Host "  4. Citations: fill in 3. output\refs.bib yourself; pick a CSL in 3. output\csl (default: apa.csl)."
  Write-Host "     Export to Word/PDF with Pandoc --citeproc --bibliography 3. output\refs.bib --csl 3. output\csl\<preset>.csl."
}
if ($withRetrieval) {
  Write-Host "  5. Check the engines: .\rag.ps1 check. PDF -> .\rag.ps1 ingest -Page. .md file -> .\rag.ps1 ingest."
  Write-Host "     Confidential/unstructured PDF: .\rag.ps1 convert `"name.pdf`" first, then ingest."
  Write-Host "     Per-file synthesis: .\rag.ps1 ask-file `"name`" `"question`" (add -Page for PDF)."
  Write-Host "     .md files in '1. raw' are assembled by Terra right away; list any CONFIDENTIAL ones in '1. raw\_terra-tolak.txt'."
  Write-Host "     Cross-document: .\rag.ps1 ask `"...`" or fill in tmp\ask-batch\*.md then .\rag.ps1 synth."
  Write-Host "     Promote a draft: .\rag.ps1 promote-terra `"<slug>`" or manually via terra-context + terra-gate."
  if (-not $NoLoop) {
    Write-Host "     Assemble output, Claude by default: /loop-engine <name>; explicit Codex fallback: Codex, assemble output for <slug>."
    Write-Host "     Codex resumes from a valid checkpoint, claims .loop\<slug>\run.lock, and writes the canonical 3. output."
  }
} else {
  Write-Host "  5. The retrieval wrapper wasn't created (NoLoop/NoRetrieval). Add it manually later if you need ingest/query."
}
Write-Host "  6. If you change the routing, regenerate: py -3.13 '$idx'"
Write-Host "  7. Validate: py -3.13 '$lc' --vault $Name"
