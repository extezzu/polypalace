# launch.ps1 — Sunday automation script for PolyPalace v0.1
# Usage: open PowerShell, cd to project root, run: .\launch.ps1
#
# This script handles ONLY the user-gated tasks that need credentials.
# Everything else (code, README, posts) is already done.
#
# Prerequisites:
#   1. Run `gh auth login` ONCE before this script (interactive browser)
#   2. Make sure Claude Desktop is QUIT (not just minimized — quit from tray)
#      so mempalace-mcp.exe is unlocked

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " PolyPalace v0.1 Launch Script" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Verify gh auth ---
Write-Host "Step 1/5: Checking GitHub CLI auth..." -ForegroundColor Yellow
$ghStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ gh CLI not authenticated." -ForegroundColor Red
    Write-Host "  Run this first (interactive browser flow):" -ForegroundColor Yellow
    Write-Host "    gh auth login" -ForegroundColor White
    Write-Host "  Pick: GitHub.com → HTTPS → Login with web browser → done." -ForegroundColor Yellow
    Write-Host "  Then re-run .\launch.ps1" -ForegroundColor Yellow
    exit 1
}
Write-Host "  ✓ gh authenticated." -ForegroundColor Green
Write-Host ""

# --- Step 2: Uninstall old mempalace if present ---
Write-Host "Step 2/5: Uninstalling old mempalace package (if present)..." -ForegroundColor Yellow
$mempalaceShow = pip show mempalace 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Found mempalace 3.3.3, uninstalling..."
    Write-Host "  (If this fails with file lock, close Claude Desktop completely first)"
    pip uninstall -y mempalace 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Uninstall failed — close Claude Desktop fully (kill from system tray)" -ForegroundColor Red
        Write-Host "  Then re-run this script." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✓ Old mempalace uninstalled." -ForegroundColor Green
} else {
    Write-Host "  ✓ mempalace not installed (or already uninstalled)." -ForegroundColor Green
}
Write-Host ""

# --- Step 3: Install polypalace in dev mode ---
Write-Host "Step 3/5: Installing polypalace (editable mode)..." -ForegroundColor Yellow
pip install -e . 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ pip install failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ polypalace installed." -ForegroundColor Green
Write-Host ""

# --- Step 4: Verify MCP server boots with new tools ---
Write-Host "Step 4/5: Verifying MCP server boots and registers new tools..." -ForegroundColor Yellow
$toolListJson = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
$response = $toolListJson | & polypalace-mcp 2>$null | Select-Object -First 1
$parsed = $response | ConvertFrom-Json
$toolCount = $parsed.result.tools.Count
$hasWhatsNew = $parsed.result.tools | Where-Object { $_.name -eq "whats_new" }
$hasSurface = $parsed.result.tools | Where-Object { $_.name -eq "surface_ideas" }

if ($toolCount -ge 31 -and $hasWhatsNew -and $hasSurface) {
    Write-Host "  ✓ Server boots, $toolCount tools registered (29 MemPalace + 2 PolyPalace)" -ForegroundColor Green
} else {
    Write-Host "  ✗ Tool registration check failed" -ForegroundColor Red
    Write-Host "    Tool count: $toolCount (expected 31+)"
    Write-Host "    whats_new found: $($hasWhatsNew -ne $null)"
    Write-Host "    surface_ideas found: $($hasSurface -ne $null)"
    exit 1
}
Write-Host ""

# --- Step 5: GitHub repo create + push ---
Write-Host "Step 5/5: Creating GitHub repo + pushing code..." -ForegroundColor Yellow

$repoExists = gh repo view extezzu/polypalace 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Repo extezzu/polypalace already exists. Updating remote + pushing..."
    git remote set-url origin https://github.com/extezzu/polypalace.git
    git push origin develop 2>&1 | Select-Object -Last 5
} else {
    Write-Host "  Creating extezzu/polypalace as public repo..."
    git remote set-url origin https://github.com/extezzu/polypalace.git
    gh repo create extezzu/polypalace --public `
        --description "Personal AI assistant for Claude Desktop. Synthesizes activity across multi-project folder, Brave bookmarks, Telegram saved messages. Fork of MemPalace." `
        --source . `
        --push
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Repo published: https://github.com/extezzu/polypalace" -ForegroundColor Green
} else {
    Write-Host "  ✗ Repo create/push failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# --- Done ---
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " ✅ PUBLISHED — PolyPalace v0.1 is live" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next (your call, no urgency):"
Write-Host "  - Update Claude Desktop config (see SUNDAY_CHECKLIST.md step 3)"
Write-Host "  - Record Loom (script in LAUNCH_POSTS.md, ~90s)"
Write-Host "  - Post Twitter / LinkedIn / HN / Reddit (drafts in LAUNCH_POSTS.md)"
Write-Host "  - Submit to PulseMCP / Smithery directories"
Write-Host "  - Optional: pip publish via twine"
Write-Host ""
Write-Host "Code is live. Everything else is content + distribution that can wait."
Write-Host ""
