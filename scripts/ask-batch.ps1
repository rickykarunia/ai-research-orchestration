<#
.SYNOPSIS
    Run a batch of retrieval questions against corpus.py / vcorpus.py, write a Markdown evidence packet.

.DESCRIPTION
    Bridges "1. raw" to "2. wiki". One question file = one evidence packet.
    An evidence packet is WORK IN PROGRESS, not a wiki note and not a fact. Read it, filter
    it, then write the "2. wiki" note with source-refs.

    Question file format (.md or .txt), example:

        # Fact - Tax-holiday effectiveness literature
        tool: corpus.py

        What are the corpus papers' main findings on tax-holiday effectiveness?
        What is the main critique of tax holidays regarding incentive redundancy?

    Parser rules:
      - the first "# ..." line -> packet title (if none, title = file name)
      - a "tool: corpus.py" or "tool: vcorpus.py" line -> engine for that file
      - any other non-blank line -> one question (leading "- " or "1. " is stripped)
      - lines starting with "//", ">" or "<!--" are ignored

.EXAMPLE
    cd "$HOME\Projects\<vault-name>"
    ..\ai-orchestration\scripts\ask-batch.ps1

.EXAMPLE
    ..\ai-orchestration\scripts\ask-batch.ps1 -Questions "tmp\ask-batch\01-literature.md" -Tool corpus.py
#>
param(
    # Vault root. Default: current working folder.
    [string]$Vault = (Get-Location).Path,
    # Single question file, or a folder containing several. Relative to $Vault.
    [string]$Questions = "tmp\ask-batch",
    # Output folder for evidence packets. Relative to $Vault.
    [string]$OutDir = "tmp\retrieval-packets",
    # Force the engine for all files, ignoring "tool:" directives.
    [ValidateSet("corpus.py", "vcorpus.py")]
    [string]$Tool,
    # Engine used when a file has no "tool:" line and -Tool isn't given.
    [ValidateSet("corpus.py", "vcorpus.py")]
    [string]$DefaultTool = "vcorpus.py",
    # Show the plan without calling the engine.
    [switch]$DryRun,
    # Test the parser without touching the vault or Python.
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-QuestionFile {
    <# Return a hashtable: Title, Tool (may be $null), Questions (string[]). #>
    param([string]$Path)

    $title = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    $titleSeen = $false
    $tool = $null
    $questions = New-Object System.Collections.Generic.List[string]

    foreach ($rawLine in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $rawLine.Trim()
        if ($line.Length -eq 0) { continue }
        if ($line.StartsWith("//") -or $line.StartsWith(">") -or $line.StartsWith("<!--")) { continue }
        if ($line.StartsWith("#")) {
            if (-not $titleSeen) {
                $title = $line.TrimStart("#", " ").Trim()
                $titleSeen = $true
            }
            continue
        }
        if ($line -match '^tool\s*:\s*(corpus\.py|vcorpus\.py)\s*$') {
            $tool = $Matches[1]
            continue
        }
        $q = $line -replace '^[-*]\s+', '' -replace '^\d+[.)]\s+', ''
        if ($q.Trim().Length -gt 0) { $questions.Add($q.Trim()) }
    }

    return @{ Title = $title; Tool = $tool; Questions = @($questions) }
}

function Invoke-SelfTest {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ask-batch-selftest-" + [guid]::NewGuid().ToString("N") + ".md")
    $body = @(
        "# Packet Title",
        "tool: corpus.py",
        "",
        "// comment ignored",
        "> quote ignored",
        "First question?",
        "- Second question?",
        "2. Third question?"
    )
    Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
    try {
        $parsed = Read-QuestionFile -Path $tmp
        if ($parsed.Title -ne "Packet Title") { throw "wrong title: $($parsed.Title)" }
        if ($parsed.Tool -ne "corpus.py") { throw "wrong tool: $($parsed.Tool)" }
        if ($parsed.Questions.Count -ne 3) { throw "wrong question count: $($parsed.Questions.Count)" }
        if ($parsed.Questions[1] -ne "Second question?") { throw "bullet not stripped: $($parsed.Questions[1])" }
        if ($parsed.Questions[2] -ne "Third question?") { throw "number not stripped: $($parsed.Questions[2])" }
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }

    $tmp2 = Join-Path ([System.IO.Path]::GetTempPath()) ("ask-batch-selftest2-" + [guid]::NewGuid().ToString("N") + ".txt")
    Set-Content -LiteralPath $tmp2 -Value @("Just one question?") -Encoding UTF8
    try {
        $parsed2 = Read-QuestionFile -Path $tmp2
        if ($parsed2.Tool -ne $null) { throw "tool should be null" }
        if ($parsed2.Questions.Count -ne 1) { throw "fallback failed" }
        if ($parsed2.Title -notlike "ask-batch-selftest2-*") { throw "title fallback failed: $($parsed2.Title)" }
    }
    finally {
        Remove-Item -LiteralPath $tmp2 -Force -ErrorAction SilentlyContinue
    }

    Write-Host "ask-batch selftest OK"
}

function Invoke-Ask {
    <# Call the engine once. Return an array of output lines. #>
    param([string]$VaultRoot, [string]$Engine, [string]$Question)

    $prevIo = $env:PYTHONIOENCODING
    $prevUtf8 = $env:PYTHONUTF8
    $prevWarn = $env:PYTHONWARNINGS
    $prevEap = $ErrorActionPreference
    try {
        $env:PYTHONIOENCODING = "utf-8"
        $env:PYTHONUTF8 = "1"
        # fastembed spits out a UserWarning on every call; keep it out of the evidence packet.
        $env:PYTHONWARNINGS = "ignore"
        $ErrorActionPreference = "Continue"
        Push-Location -LiteralPath $VaultRoot
        try {
            $out = & py -3.13 (Join-Path "." $Engine) ask $Question 2>&1
            $code = $LASTEXITCODE
        }
        finally { Pop-Location }
    }
    finally {
        $env:PYTHONIOENCODING = $prevIo
        $env:PYTHONUTF8 = $prevUtf8
        $env:PYTHONWARNINGS = $prevWarn
        $ErrorActionPreference = $prevEap
    }

    if ($code -ne 0) {
        $detail = ($out | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        throw "$Engine ask failed (exit $code):`n$detail"
    }
    return @($out | ForEach-Object { [string]$_ })
}

if ($SelfTest) { Invoke-SelfTest; return }

# --- resolve path ---
if (-not (Test-Path -LiteralPath $Vault)) { throw "Vault not found: $Vault" }
$Vault = (Resolve-Path -LiteralPath $Vault).Path

$qPath = if ([System.IO.Path]::IsPathRooted($Questions)) { $Questions } else { Join-Path $Vault $Questions }
if (-not (Test-Path -LiteralPath $qPath)) {
    throw "Question file/folder not found: $qPath`nCreate it first; the header of this script shows the format."
}

$files = @(if (Test-Path -LiteralPath $qPath -PathType Container) {
    @(Get-ChildItem -LiteralPath $qPath -File | Where-Object { $_.Extension -in ".md", ".txt" } | Sort-Object Name)
} else {
    @(Get-Item -LiteralPath $qPath)
})
if ($files.Count -eq 0) { throw "No .md/.txt files in $qPath" }

$outPath = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $Vault $OutDir }
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

$vaultName = Split-Path -Leaf $Vault
$stamp = Get-Date -Format "yyyy-MM-dd"

foreach ($file in $files) {
    $parsed = Read-QuestionFile -Path $file.FullName
    $engine = if ($Tool) { $Tool } elseif ($parsed.Tool) { $parsed.Tool } else { $DefaultTool }

    if ($parsed.Questions.Count -eq 0) {
        Write-Warning "$($file.Name): no questions, skipping."
        continue
    }

    $enginePath = Join-Path $Vault $engine
    if (-not (Test-Path -LiteralPath $enginePath)) {
        throw "$engine not found in $Vault. Copy it from templates\retrieval-per-vault\ or run new-vault.ps1."
    }

    Write-Host "[$($file.Name)] $engine, $($parsed.Questions.Count) questions"
    if ($DryRun) {
        foreach ($q in $parsed.Questions) { Write-Host "  - $q" }
        continue
    }

    $method = if ($engine -eq "corpus.py") { "corpus.py (PageIndex, tree search)" } else { "vcorpus.py (local vector, small-to-big)" }
    $buf = New-Object System.Collections.Generic.List[string]
    $buf.Add("---")
    $buf.Add("type: retrieval-packet")
    $buf.Add("status: bukti-mentah")
    $buf.Add("vault: $vaultName")
    $buf.Add("method: $method")
    $buf.Add("questions-file: $($file.Name)")
    $buf.Add("generated: $stamp")
    $buf.Add("---")
    $buf.Add("")
    $buf.Add("# $($parsed.Title)")
    $buf.Add("")
    $buf.Add("> This packet is work in progress, not a fact and not a wiki note. Filter it first:")
    $buf.Add("> drop passages below threshold, note the locator, then write a `2. wiki` note with")
    $buf.Add("> `source-refs`, `confidence`, and `method: $engine`. Anything left uncovered goes into `## Gap backlog`.")
    $buf.Add("")

    $n = 0
    foreach ($q in $parsed.Questions) {
        $n++
        Write-Host "  Q$n ..."
        $answer = Invoke-Ask -VaultRoot $Vault -Engine $engine -Question $q
        $buf.Add("## Q$n. $q")
        $buf.Add("")
        $buf.Add('```text')
        foreach ($line in $answer) { $buf.Add($line) }
        $buf.Add('```')
        $buf.Add("")
    }

    $target = Join-Path $outPath ("$($file.BaseName).md")
    Set-Content -LiteralPath $target -Value $buf -Encoding UTF8
    Write-Host "  -> $target"
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "Done. Evidence packets at: $outPath"
    Write-Host "Next: read the packets, write a '2. wiki' note with source-refs, log any gaps."
}
