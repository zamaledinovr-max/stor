<#
.SYNOPSIS
    Initializes a local Git repository and optionally pushes it to a remote.

.DESCRIPTION
    Run from the project root:
        powershell -ExecutionPolicy Bypass -File .\scripts\init_git.ps1

    Or with a remote repository (create an EMPTY repository on GitHub/GitLab first):
        powershell -ExecutionPolicy Bypass -File .\scripts\init_git.ps1 https://github.com/<user>/<repo>.git

.NOTES
    .env is ignored by .gitignore and is never committed by this script.
    The script does not store credentials: use Git Credential Manager or a PAT.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$RemoteUrl = "",

    [string]$Branch = "main",

    [string]$Message = "Initial commit: Telegram Mini App + aiogram marketplace MVP"
)

$ErrorActionPreference = "Stop"

function Fail([string]$Text) {
    Write-Host "ERROR: $Text" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git was not found in PATH. Install Git for Windows and reopen the terminal."
}

if (-not (Test-Path "app\main.py") -or -not (Test-Path "pyproject.toml")) {
    Fail "Run this script from the project root (the folder that contains app\ and pyproject.toml)."
}

if (-not (Test-Path ".git")) {
    Write-Host "Initializing Git repository in $(Get-Location)..."
    git init | Out-Null
    git symbolic-ref HEAD "refs/heads/$Branch"
} else {
    Write-Host "Git repository already exists."
}

$identity = git config user.email
if ([string]::IsNullOrWhiteSpace($identity)) {
    Fail "Set your Git identity first: git config --global user.name `"Your Name`"; git config --global user.email `"you@example.com`""
}

if (Test-Path ".env") {
    Write-Host "Found .env - it is ignored by .gitignore and will not be committed." -ForegroundColor Yellow
}

# Fail fast if a real secret somehow becomes tracked.
git add --all
$trackedEnv = @(git ls-files ".env" ".env.*")
$leakedEnv = @($trackedEnv | Where-Object { $_ -ne ".env.example" })
if ($leakedEnv.Count -gt 0) {
    Fail ("A real environment file is staged: " + ($leakedEnv -join ", ") + ". Remove it: git rm --cached <file>")
}

if (git diff --cached --quiet) {
    Write-Host "Nothing to commit."
} else {
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) {
        Fail "git commit failed."
    }
}

if ($RemoteUrl) {
    $remotes = git remote
    if ($remotes -contains "origin") {
        git remote set-url origin $RemoteUrl
    } else {
        git remote add origin $RemoteUrl
    }
    Write-Host "Pushing branch '$Branch' to $RemoteUrl ..."
    git push -u origin $Branch
    if ($LASTEXITCODE -ne 0) {
        Fail "git push failed. Check the URL, network access and your Git credentials/PAT."
    }
    Write-Host "Done. Repository is available at $RemoteUrl" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Local repository is ready. To publish it:" -ForegroundColor Green
    Write-Host "  1. Create an EMPTY repository on GitHub/GitLab (without README/license)."
    Write-Host "  2. git remote add origin https://github.com/<user>/<repo>.git"
    Write-Host "  3. git push -u origin $Branch"
    Write-Host ""
    Write-Host "Or rerun this script with the URL:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\init_git.ps1 https://github.com/<user>/<repo>.git"
}
