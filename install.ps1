<#
.SYNOPSIS
  Install ai-research-orchestration for the current user. Safe to re-run.
.PARAMETER SkipPip
  Do not install Python dependencies.
.PARAMETER SkipSkills
  Do not link skills into ~/.claude/skills (use when the skills come from the plugin).
.PARAMETER UserHome
  Target home folder (default: $HOME). Used for testing.
#>
param([switch]$SkipPip, [switch]$SkipSkills, [string]$UserHome = $HOME)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Kit = $PSScriptRoot
$SkillsDir = Join-Path $UserHome ".claude\skills"

if (-not $SkipPip) {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    & $py.Source -3.13 -m pip install -r (Join-Path $Kit "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
  }
  else { Write-Warning "Python launcher 'py' not found. Install Python 3.13, then run: py -3.13 -m pip install -r requirements.txt" }
}

if ($SkipSkills) { Write-Host "skills: skipped (-SkipSkills)" }
else {
New-Item -ItemType Directory -Force $SkillsDir | Out-Null
foreach ($s in Get-ChildItem -Directory (Join-Path $Kit "skills")) {
  $dest = Join-Path $SkillsDir $s.Name
  if (Test-Path -LiteralPath $dest) {
    $item = Get-Item -LiteralPath $dest -Force
    if ($item.LinkType -eq "Junction") {
      $target = $item.Target
      if ($target -is [array]) { $target = $target[0] }
      $normTarget = $target.TrimEnd('\').ToLowerInvariant()
      $normKit = $s.FullName.TrimEnd('\').ToLowerInvariant()
      if ($normTarget -eq $normKit) { Write-Host "skill $($s.Name): already linked"; continue }
      Write-Warning "skill $($s.Name): junction points to $target, not this kit; skipped"; continue
    }
    Write-Warning "skill $($s.Name): $dest exists and is not a junction; skipped"; continue
  }
  New-Item -ItemType Junction -Path $dest -Target $s.FullName | Out-Null
  Write-Host "skill $($s.Name): linked"
}
}

$rules = Join-Path $UserHome "AI-RULES.md"
if (Test-Path -LiteralPath $rules) { Write-Host "~/AI-RULES.md exists; left unchanged" }
else { Copy-Item (Join-Path $Kit "RULES.template.md") $rules; Write-Host "created ~/AI-RULES.md from template" }

Write-Host "`nNext:"
Write-Host "  1. Create a vault:   & '$Kit\scripts\new-vault.ps1' my-research -Type generic"
Write-Host "  2. Build the index:  py -3.13 '$Kit\scripts\index_sync.py'"
