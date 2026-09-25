[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ScriptPath = Join-Path $PSScriptRoot '..\scripts\new-vault.ps1'
$Types = @('paper','kajian','regulasi','app','saas','ideation','equity','oped','generic')
$Presets = @('apa.csl','ieee.csl','chicago-author-date.csl','chicago-notes-bibliography.csl')
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-orchestration-citation-test-" + [guid]::NewGuid().ToString('N'))
$VaultName = 'citation-test-vault'
$VaultDir = Join-Path $TempRoot $VaultName

function Assert-True($condition, $message) {
  if (-not $condition) { throw "ASSERTION FAILED: $message" }
}

try {
  foreach ($type in $Types) {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath $type -Type $type -Root $TempRoot -DryRun 2>&1 | Out-String
    Assert-True ($LASTEXITCODE -eq 0) "dry-run failed for type '$type'"
    Assert-True ($output -match 'citation\s+:.*default apa') "default APA not visible for type '$type'"
    foreach ($preset in $Presets) {
      Assert-True ($output -match [regex]::Escape($preset)) "preset '$preset' not visible for type '$type'"
    }
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath $VaultName -Type generic -Root $TempRoot -NoRetrieval | Out-Null
  Assert-True ($LASTEXITCODE -eq 0) 'scaffold loop -NoRetrieval failed'
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $VaultDir '3. output\refs.bib'))) 'refs.bib must not be created by the scaffold'
  foreach ($preset in $Presets) {
    Assert-True (Test-Path -LiteralPath (Join-Path $VaultDir "3. output\csl\$preset") -PathType Leaf) "preset '$preset' not copied"
  }
  $agents = Get-Content -Raw -LiteralPath (Join-Path $VaultDir 'AGENTS.md')
  $readme = Get-Content -Raw -LiteralPath (Join-Path $VaultDir 'README.md')
  $context = Get-Content -Raw -LiteralPath (Join-Path $VaultDir '2. wiki\01 - Project Context.md')
  foreach ($needle in @('[@citekey]','@citekey','3. output/refs.bib','output.pdf','output.docx','chicago-notes-bibliography.csl','Zotero','Pandoc','pdflatex')) {
    Assert-True (($agents + $readme + $context).Contains($needle)) "text '$needle' not found in the scaffold output"
  }

  $NoLoopRoot = Join-Path $TempRoot 'no-loop'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath 'citation-test-no-loop' -Type generic -Root $NoLoopRoot -NoLoop | Out-Null
  Assert-True ($LASTEXITCODE -eq 0) 'scaffold -NoLoop failed'
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $NoLoopRoot 'citation-test-no-loop\3. output\csl'))) '-NoLoop created a CSL folder'
  Write-Host 'PASS: universal citation scaffold' -ForegroundColor Green
}
finally {
  if (Test-Path -LiteralPath $TempRoot) {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force
  }
}
