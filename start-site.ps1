# start-site.ps1 — Start the StorySmith AI dev server
# Appends Node.js to PATH (so npm is found) WITHOUT replacing existing PATH.
# This preserves active Python venvs.

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check if npm is already available
$npmFound = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmFound) {
    Write-Host "npm not found on PATH, adding system paths..." -ForegroundColor Yellow
    # Append machine + user paths to existing PATH (preserves venv and other session additions)
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$env:Path;$machinePath;$userPath"

    # Verify npm is now reachable
    $npmFound = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmFound) {
        Write-Host "ERROR: npm still not found. Install Node.js and ensure it's on your system PATH." -ForegroundColor Red
        exit 1
    }
    Write-Host "npm found: $($npmFound.Source)" -ForegroundColor Green
}

# Start the Next.js dev server
Set-Location (Join-Path $projectRoot "site")
Write-Host "Starting Next.js dev server on port 3000..." -ForegroundColor Cyan
npm run dev -- --port 3000
