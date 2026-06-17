#Requires -RunAsAdministrator
<#
.SYNOPSIS
  One-shot installer for the `daily-refresh` GitHub Actions self-hosted runner
  on this PC (Kejjeh/PLV_Clone).

.HOW TO RUN
  Open PowerShell **as Administrator**, then:

      powershell -ExecutionPolicy Bypass -File scripts\ci\install_self_hosted_runner.ps1

.WHAT IT DOES (hands-off up to the service prompts)
  1. Downloads the latest actions/runner for win-x64 into C:\actions-runner.
  2. Fetches a fresh registration token via the gh CLI (nothing to copy/paste).
  3. Runs config.cmd to register the runner against Kejjeh/PLV_Clone.

.WHEN config.cmd PROMPTS YOU
  - Runner group / name / work folder : press Enter for defaults.
  - Additional labels                 : press Enter (self-hosted, Windows, X64
                                         are added automatically; the workflow
                                         targets [self-hosted, Windows]).
  - "Run runner as service (Y/N)"     : Y
  - "User account to use for service" : enter YOUR Windows account so the runner
                                         inherits your Python (heavy deps) + git
                                         credentials, e.g.
                                             $($env:USERDOMAIN)\$($env:USERNAME)
                                         then your password.
                                         (NETWORK SERVICE will NOT have your
                                         Python / git creds - the daily refresh
                                         would fail.)

  After it finishes, confirm the runner shows "Idle" under
  GitHub -> PLV_Clone -> Settings -> Actions -> Runners, then trigger
  "Daily full refresh" once via Actions -> Run workflow to smoke-test it.
#>

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo      = 'Kejjeh/PLV_Clone'
$RunnerDir = 'C:\actions-runner'

# --- preflight ------------------------------------------------------------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "gh CLI not found on PATH. Install GitHub CLI or open a shell where 'gh' resolves."
}
& gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    throw "gh is not authenticated in this (elevated) shell. Run 'gh auth login' here first."
}

if (Test-Path (Join-Path $RunnerDir '.runner')) {
    Write-Host "A runner is already configured at $RunnerDir. Remove it first with " `
               "'.\config.cmd remove' if you want a clean reinstall." -ForegroundColor Yellow
    return
}

# --- 1. download + extract latest runner ----------------------------------
$tag = (& gh api repos/actions/runner/releases/latest --jq '.tag_name').Trim()   # e.g. v2.319.1
$ver = $tag.TrimStart('v')
$zip = "actions-runner-win-x64-$ver.zip"
$url = "https://github.com/actions/runner/releases/download/$tag/$zip"

New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
$zipPath = Join-Path $RunnerDir $zip
Write-Host "Downloading $url ..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $url -OutFile $zipPath
Write-Host "Extracting to $RunnerDir ..." -ForegroundColor Cyan
Expand-Archive -Path $zipPath -DestinationPath $RunnerDir -Force
Remove-Item $zipPath -Force

# --- 2. fresh registration token (short-lived; not echoed) ----------------
Write-Host "Requesting registration token via gh ..." -ForegroundColor Cyan
$token = (& gh api -X POST "repos/$Repo/actions/runners/registration-token" --jq '.token').Trim()
if (-not $token) { throw "Failed to obtain a registration token." }

# --- 3. configure (interactive for the service prompts) -------------------
Push-Location $RunnerDir
try {
    Write-Host "`nLaunching config.cmd - answer the service prompts as noted in the header.`n" -ForegroundColor Green
    & .\config.cmd --url "https://github.com/$Repo" --token $token --labels "self-hosted,Windows,X64"
}
finally {
    Pop-Location
}

Write-Host "`nDone. Verify 'Idle' under PLV_Clone -> Settings -> Actions -> Runners," `
           "then run the 'Daily full refresh' workflow once to smoke-test." -ForegroundColor Green
