# scripts/refresh.ps1 — one-command data refresh + GitHub Pages deploy
#
# Usage:
#   .\scripts\refresh.ps1              # full refresh, commit, and push
#   .\scripts\refresh.ps1 -NoPush      # refresh locally, skip commit/push
#   .\scripts\refresh.ps1 -Year 2025   # target a different season year

param(
    [switch]$NoPush,
    [int]$Year = 2026
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$end = (Get-Date).AddDays(-2).ToString("yyyy-MM-dd")

Write-Host ""
Write-Host "=== PLV Clone data refresh ==="
Write-Host "  Year   : $Year"
Write-Host "  Through: $end (today minus 2-day Statcast lag)"
if ($NoPush) { Write-Host "  Mode   : local only (no push)" }
else         { Write-Host "  Mode   : refresh + push to GitHub Pages" }
Write-Host ""

# plv update handles: pull new Statcast, rebuild full-season features,
# score PLV + Process+, build all export CSVs.
if ($NoPush) {
    plv update --year $Year
} else {
    plv update --year $Year --push
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "plv update failed (exit $LASTEXITCODE)"
    exit 1
}

# Generate the HTML report (reads CSVs, fetches live ESPN data).
plv generate-report --year $Year
if ($LASTEXITCODE -ne 0) {
    Write-Error "plv generate-report failed (exit $LASTEXITCODE)"
    exit 1
}

# If not pushing via plv update --push, commit the HTML separately.
if ($NoPush) {
    Write-Host ""
    Write-Host "Done. Run without -NoPush to commit and deploy."
} else {
    # Commit the freshly-generated HTML (plv update already pushed the CSVs).
    git add "data/outputs/process_report_$Year.html"
    $msg = "report: regenerate $Year through $end"
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git commit -m $msg
        git push origin main
        Write-Host ""
        Write-Host "Pushed. GitHub Pages will redeploy in ~60s."
        Write-Host "  https://kejjeh.github.io/PLV_Clone/"
    } else {
        Write-Host "HTML unchanged — nothing extra to push."
    }
}
