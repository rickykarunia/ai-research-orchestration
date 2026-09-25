<#
.SYNOPSIS
  Single entry point for this vault's retrieval.

.DESCRIPTION
  Wraps corpus.py (PageIndex, structured PDFs) and vcorpus.py (local embedding,
  internal PDFs + every .md in "1. raw"). This script solves two operational problems:
  the full Python path never needs retyping, and the engine choice has a fixed default
  (vector), so it doesn't need deciding every command.

  Default engine = vcorpus.py (local, free, indexes .md). Add -Page to
  use corpus.py/PageIndex on a structured PDF.

.EXAMPLE
  .\rag.ps1 check
.EXAMPLE
  .\rag.ps1 ingest            # vcorpus: every .md in "1. raw" (PDF: -Page, or convert first)
.EXAMPLE
  .\rag.ps1 ingest -Page      # corpus/PageIndex: structured PDFs
.EXAMPLE
  .\rag.ps1 ask "What's the legal basis for X?"
.EXAMPLE
  .\rag.ps1 ask "What did the paper find about Y?" -Page
.EXAMPLE
  .\rag.ps1 synth             # batch: tmp\ask-batch\*.md -> tmp\retrieval-packets\
.EXAMPLE
  .\rag.ps1 synth "tmp\ask-batch\01-literature.md" -DryRun
.EXAMPLE
  .\rag.ps1 convert "meeting minutes.pdf"   # Marker -> "1. raw\meeting minutes.md", original PDF parked
.EXAMPLE
  .\rag.ps1 ask-file "paper.pdf" "What's the identification method?" -Page
.EXAMPLE
  .\rag.ps1 ask-essential "regulation.md"      # essential set, 1 .md file (vcorpus)
.EXAMPLE
  .\rag.ps1 ask-essential "paper.pdf" -Page    # Q1-Q8, 1 PDF (corpus)
.EXAMPLE
  .\rag.ps1 ask-essential --new                # only .md without a draft yet
.EXAMPLE
  .\rag.ps1 ask-essential --new -Page          # only PDFs without a draft yet
.EXAMPLE
  .\rag.ps1 ask-essential --all                # every indexed .md
.EXAMPLE
  .\rag.ps1 review-draft "paper.pdf"     # flag candidate contradictions across draft entries
.EXAMPLE
  .\rag.ps1 promote-terra "slug"                       # LLM: verify + write note + gate
.EXAMPLE
  .\rag.ps1 promote-terra --all                        # LLM: every unreviewed draft
.EXAMPLE
  .\rag.ps1 terra-context "slug"                       # mechanical: draft_to_note + gate, no Kimi
.EXAMPLE
  .\rag.ps1 terra-gate "slug" --note "Foo.md"          # mechanical lint of a manual note
.EXAMPLE
  .\rag.ps1 status            # loop_check + vault content counts
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory, Position = 0)]
  [ValidateSet('check','ingest','list','ask','ask-file','ask-essential','remove','synth','status','convert','review-draft','promote-terra','terra-context','terra-gate')]
  [string]$Command,

  [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
  [string[]]$Rest,

  # Use corpus.py/PageIndex instead of vcorpus.py.
  [switch]$Page,

  # For 'synth' and 'promote-terra': show the plan without calling the engine/API.
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Vault = $PSScriptRoot
$VaultName = Split-Path -Leaf $Vault
$Orchestration = "__AIO_KIT__\scripts"
$Pdf2Md = $env:AIO_PDF2MD   # optional PDF->Markdown converter script; PDF conversion is skipped when unset

# Old pain point: `py` sometimes isn't resolvable in this shell. Resolve it once here,
# instead of in every command block that gets hand-pasted.
function Resolve-Python {
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe",
    "C:\Windows\py.exe"
  )
  foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return @($c, '-3.13') } }
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) { return @($cmd.Source, '-3.13') }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return @($cmd.Source) }
  throw "Python not found. Set the launcher path in Resolve-Python."
}

$PyParts = Resolve-Python
$Py = $PyParts[0]
$PyArgs = @($PyParts | Select-Object -Skip 1)
# Only corpus.py implements remove, so it always goes there.
$Engine = if ($Page -or $Command -eq "remove") { "corpus.py" } else { "vcorpus.py" }

function Invoke-Engine([string]$EngineFile, [string[]]$EngineArgs) {
  $path = Join-Path $Vault $EngineFile
  if (-not (Test-Path -LiteralPath $path)) { throw "Engine not present in this vault: $path" }
  $prevIo = $env:PYTHONIOENCODING
  $prevUtf8 = $env:PYTHONUTF8
  try {
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"
    & $Py @PyArgs $path @EngineArgs
    if ($LASTEXITCODE -ne 0) { throw "$EngineFile $($EngineArgs -join ' ') failed (exit $LASTEXITCODE)." }
  }
  finally {
    $env:PYTHONIOENCODING = $prevIo
    $env:PYTHONUTF8 = $prevUtf8
  }
}

Set-Location -LiteralPath $Vault

switch ($Command) {
  'check' {
    foreach ($e in @("corpus.py","vcorpus.py")) {
      if (Test-Path -LiteralPath (Join-Path $Vault $e)) {
        Write-Host "== $e check ==" -ForegroundColor Cyan
        Invoke-Engine $e @('check')
      }
    }
  }
  'status' {
    $raw = @(Get-ChildItem -LiteralPath (Join-Path $Vault "1. raw") -File -ErrorAction SilentlyContinue)
    $wiki = @(Get-ChildItem -LiteralPath (Join-Path $Vault "2. wiki") -Filter *.md -ErrorAction SilentlyContinue)
    $out = @(Get-ChildItem -LiteralPath (Join-Path $Vault "3. output") -File -ErrorAction SilentlyContinue)
    Write-Host "vault  : $VaultName" -ForegroundColor Cyan
    Write-Host "1. raw : $($raw.Count) file(s) ($(@($raw | Where-Object Extension -eq '.pdf').Count) pdf, $(@($raw | Where-Object Extension -eq '.md').Count) md)"
    Write-Host "2. wiki: $($wiki.Count) note(s)"
    Write-Host "3. out : $($out.Count) file(s)"
    $ctx = Join-Path $Vault "2. wiki\01 - Project Context.md"
    if (Test-Path -LiteralPath $ctx) {
      $open = @(Select-String -LiteralPath $ctx -Pattern 'NEEDS SOURCE|NEEDS VERIFICATION|NEEDS USER DECISION')
      Write-Host "gap    : $($open.Count) flagged line(s) in Project Context"
    }
    $lc = Join-Path $Orchestration "loop_check.py"
    if (Test-Path -LiteralPath $lc) {
      Write-Host "== loop_check ==" -ForegroundColor Cyan
      & $Py @PyArgs $lc --vault $VaultName
    }
  }
  'convert' {
    # Confidential or unstructured PDF: convert it locally to .md so it can enter vcorpus,
    # then park the original PDF in a subfolder so it doesn't get swept by PageIndex ingest.
    if (-not $Rest -or $Rest.Count -lt 1) { throw 'usage: .\rag.ps1 convert "name.pdf"' }
    $raw = Join-Path $Vault "1. raw"
    $pdfName = [System.IO.Path]::GetFileName($Rest[0])
    $pdf = Join-Path $raw $pdfName
    if (-not (Test-Path -LiteralPath $pdf)) { throw "PDF not found in '1. raw': $pdf" }
    if (-not $Pdf2Md -or -not (Test-Path -LiteralPath $Pdf2Md)) { Write-Warning "Set AIO_PDF2MD to convert PDFs."; return }

    $stem = [System.IO.Path]::GetFileNameWithoutExtension($pdfName)
    $target = Join-Path $raw "$stem.md"
    # Overwriting an existing .md would discard manual edits. Stop, don't guess.
    if (Test-Path -LiteralPath $target) { throw "Already exists: $target`nDelete or rename it first; convert never overwrites." }

    $markerRoot = Join-Path $raw "marker_output"
    $before = @(Get-ChildItem -LiteralPath $markerRoot -Recurse -Filter *.md -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName)

    & $Pdf2Md $pdf
    if ($LASTEXITCODE -ne 0) { throw "PDF converter $Pdf2Md failed (exit $LASTEXITCODE). The PDF was not moved." }

    # Marker normalizes the output folder/file names, so the path can't be predicted.
    # Take the .md that's NEWLY appeared; if that's ambiguous, take the most recently written one.
    $after = @(Get-ChildItem -LiteralPath $markerRoot -Recurse -Filter *.md -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending)
    $fresh = @($after | Where-Object { $before -notcontains $_.FullName })
    $pick = if ($fresh.Count -gt 0) { $fresh[0] } elseif ($after.Count -gt 0) { $after[0] } else { $null }
    if (-not $pick) { throw "Converted .md not found under $markerRoot. The PDF was not moved." }

    Move-Item -LiteralPath $pick.FullName -Destination $target
    $park = Join-Path $raw "_source-pdf"
    New-Item -ItemType Directory -Force $park | Out-Null
    Move-Item -LiteralPath $pdf -Destination (Join-Path $park $pdfName)

    Write-Host "MD  : $target" -ForegroundColor Green
    Write-Host "PDF : $park\$pdfName  (parked; outside both engines' ingest sweep)" -ForegroundColor Green
    Write-Host "Next: .\rag.ps1 ingest"
  }
  'review-draft' {
    # An assistant for comparing entries, not a mandatory gate. Looks up the draft by the same
    # source name ask-file/ask-essential use, regardless of which engine wrote it.
    if (-not $Rest -or $Rest.Count -lt 1) { throw 'usage: .\rag.ps1 review-draft "name"' }
    $script = Join-Path $Orchestration "review-draft.py"
    if (-not (Test-Path -LiteralPath $script)) { throw "review-draft.py not found: $script" }
    $prevIo = $env:PYTHONIOENCODING; $prevUtf8 = $env:PYTHONUTF8
    try {
      $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
      & $Py @PyArgs $script $Vault $Rest[0]
      if ($LASTEXITCODE -ne 0) { throw "review-draft.py failed (exit $LASTEXITCODE)." }
    }
    finally {
      $env:PYTHONIOENCODING = $prevIo; $env:PYTHONUTF8 = $prevUtf8
    }
  }
  'promote-terra' {
    $script = Join-Path $Orchestration "promote-terra.py"
    if (-not (Test-Path -LiteralPath $script)) { throw "promote-terra.py not found: $script" }
    $prevIo = $env:PYTHONIOENCODING; $prevUtf8 = $env:PYTHONUTF8
    try {
      $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
      $extra = @($Rest)
      if ($DryRun -and ($extra -notcontains "--dry-run")) { $extra += "--dry-run" }
      & $Py @PyArgs $script "--vault" $VaultName "promote" @extra
      if ($LASTEXITCODE -ne 0) { throw "promote-terra.py promote failed (exit $LASTEXITCODE)." }
    }
    finally {
      $env:PYTHONIOENCODING = $prevIo; $env:PYTHONUTF8 = $prevUtf8
    }
  }
  'terra-context' {
    $script = Join-Path $Orchestration "promote-terra.py"
    if (-not (Test-Path -LiteralPath $script)) { throw "promote-terra.py not found: $script" }
    $prevIo = $env:PYTHONIOENCODING; $prevUtf8 = $env:PYTHONUTF8
    try {
      $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
      & $Py @PyArgs $script "--vault" $VaultName "context" @Rest
      if ($LASTEXITCODE -ne 0) { throw "promote-terra.py context failed (exit $LASTEXITCODE)." }
    }
    finally {
      $env:PYTHONIOENCODING = $prevIo; $env:PYTHONUTF8 = $prevUtf8
    }
  }
  'terra-gate' {
    if (-not $Rest -or $Rest.Count -lt 1) { throw 'usage: .\rag.ps1 terra-gate "slug" --note "title.md"' }
    $script = Join-Path $Orchestration "promote-terra.py"
    if (-not (Test-Path -LiteralPath $script)) { throw "promote-terra.py not found: $script" }
    $prevIo = $env:PYTHONIOENCODING; $prevUtf8 = $env:PYTHONUTF8
    try {
      $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
      & $Py @PyArgs $script "--vault" $VaultName "gate" @Rest
      if ($LASTEXITCODE -ne 0) { throw "promote-terra.py gate failed (exit $LASTEXITCODE)." }
    }
    finally {
      $env:PYTHONIOENCODING = $prevIo; $env:PYTHONUTF8 = $prevUtf8
    }
  }
  'synth' {
    # Delegates to ask-batch.ps1 (control plane). There's no second batch engine in the vault.
    $batch = Join-Path $Orchestration "ask-batch.ps1"
    if (-not (Test-Path -LiteralPath $batch)) { throw "ask-batch.ps1 not found: $batch" }
    $callArgs = @{ Vault = $Vault }
    if ($Rest -and $Rest.Count -gt 0) { $callArgs.Questions = $Rest[0] }
    if ($Page) { $callArgs.Tool = "corpus.py" }
    if ($DryRun) { $callArgs.DryRun = $true }
    & $batch @callArgs
  }
  default {
    Invoke-Engine $Engine (@($Command) + $Rest)
  }
}
