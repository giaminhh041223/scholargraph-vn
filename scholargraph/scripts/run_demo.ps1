<# ScholarGraph 5-minute offline demo launcher (SG-041).
Steps: 1) venv + src import check, 2) release verification (hashes, models,
snapshots), 3) offline smoke (HF offline, 5 pinned queries, export, graph hub),
4) summary with pointers. Fails loudly (exit 1) on any gap. No network calls. #>
param(
    [string]$VenvPython = ".venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location -LiteralPath $Root

function Fail([string]$msg) { Write-Error "FAIL: $msg"; exit 1 }

Write-Output "== [1/4] Python environment =="
if (-not (Test-Path -LiteralPath $VenvPython)) { Fail "venv python not found: $VenvPython (see docs/REPRODUCE.md step 1)" }
& $VenvPython -c "import sys; print(sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { Fail "venv python broken" }

Write-Output "== [2/4] Release verification =="
& $VenvPython scripts/verify_release.py
if ($LASTEXITCODE -ne 0) { Fail "verify_release.py reported gaps (see output above)" }

Write-Output "== [3/4] Offline smoke (no network) =="
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:PYTHONPATH = "src"
& $VenvPython scripts/offline_smoke.py
if ($LASTEXITCODE -ne 0) { Fail "offline_smoke.py failed" }

Write-Output "== [4/4] Demo pointers =="
Write-Output "5-minute script: docs/DEMO_SCRIPT.md"
Write-Output "Sealed results : artifacts/reports/main_results.md"
Write-Output "Release manifest: docs/RELEASE_MANIFEST.md (regenerate: python scripts/verify_release.py --write-manifest docs/RELEASE_MANIFEST.md)"
Write-Output "DEMO OK"
