<# 
.SYNOPSIS
    VibeSOP Bootstrap Script (Windows PowerShell)
.DESCRIPTION
    Detects system environment, installs prerequisites (uv), and sets up the project.
    This is the recommended entry point for Windows users.
.PARAMETER NoInstall
    Skip 'uv sync' (environment check only)
.PARAMETER Platform
    Auto-deploy to the specified platform after bootstrap
    Valid values: claude-code, opencode, kimi-cli, pi
.PARAMETER Help
    Show this help
.EXAMPLE
    .\scripts\bootstrap.ps1
    Full bootstrap (detect + install deps)
.EXAMPLE
    .\scripts\bootstrap.ps1 -NoInstall
    Environment check only (dry-run)
.EXAMPLE
    .\scripts\bootstrap.ps1 -Platform claude-code
    Bootstrap + deploy to Claude Code
#>

param(
    [switch]$NoInstall,
    [string]$Platform,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# -- Help -------------------------------------------------------------------
if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

# -- Helpers -----------------------------------------------------------------
function Write-Step($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}
function Write-OK($msg) {
    Write-Host "  OK  $msg" -ForegroundColor Green
}
function Write-Warn($msg) {
    Write-Host "  WARN  $msg" -ForegroundColor Yellow
}
function Write-Fail($msg) {
    Write-Host "  FAIL $msg" -ForegroundColor Red
}
function Write-Hint($msg) {
    Write-Host "       Hint: $msg" -ForegroundColor Cyan
}

# -- Banner ------------------------------------------------------------------
Write-Host ""
Write-Host "  VibeSOP Bootstrap (Windows)" -ForegroundColor White
Write-Host "  Skill Operating System for AI-assisted development"
Write-Host ""

# -- Phase 1: Refresh PATH ---------------------------------------------------
# uv may be installed but not visible in the current session's PATH.
# Read machine + user PATH from the registry to pick it up.
function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine") -split ";"
    $userPath    = [Environment]::GetEnvironmentVariable("PATH", "User")    -split ";"
    $currentPath = $env:PATH -split ";"

    $env:PATH = ($currentPath + $userPath + $machinePath |
        Where-Object { $_ } |
        Select-Object -Unique) -join ";"

    # Standalone installer puts uv in ~/.local/bin
    $localBin = Join-Path (Join-Path $env:USERPROFILE ".local") "bin"
    if (Test-Path $localBin) {
        $env:PATH = "$localBin;$env:PATH"
    }
    # PowerShell installer puts uv in ~/.cargo/bin
    $cargoBin = Join-Path (Join-Path $env:USERPROFILE ".cargo") "bin"
    if (Test-Path $cargoBin) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
}

Refresh-Path

# -- Phase 2: Find a real Python 3.12+ ---------------------------------------
# The Windows Store stub at %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe
# prints a "not found" message instead of a real version. Skip it.
function Find-RealPython {
    $storeStubDir = Join-Path (Join-Path $env:LOCALAPPDATA "Microsoft") "WindowsApps"

    foreach ($name in @("python3", "python")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { continue }

        $exePath = $found.Source
        if ($exePath -like "$storeStubDir\*") {
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $verOutput = & $exePath --version 2>&1 | Out-String
            $ErrorActionPreference = $prevEAP
            if ($verOutput -match "not found|Microsoft Store|App execution aliases") {
                Write-Host "       (skipping Store stub: $exePath)" -ForegroundColor DarkGray
                continue
            }
        }

        try {
            $maj = & $exePath -c "import sys; print(sys.version_info.major)" 2>$null
            $min = & $exePath -c "import sys; print(sys.version_info.minor)" 2>$null
            if ([int]$maj -ge 3 -and [int]$min -ge 12) {
                return $exePath
            }
        } catch { }
    }

    # Fallback: check if uv has Python available
    $uvExe = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvExe) {
        try {
            $uvPython = uv python find 3.12 2>$null | Out-String | ForEach-Object { $_.Trim() }
            if ($uvPython -and (Test-Path $uvPython)) {
                return $uvPython
            }
        } catch { }
    }

    return $null
}

Write-Step "Phase 1: Checking Python 3.12+"

$PYTHON = Find-RealPython

if (-not $PYTHON) {
    Write-Warn "Python 3.12+ not found on PATH"
    Write-Host "         uv will manage Python for you in the next phase."
} else {
    $ver = & $PYTHON --version 2>&1
    Write-OK "Python found: $ver"
}

# -- Phase 3: uv Check & Auto-Install ----------------------------------------
Write-Step "Phase 2: Checking uv"

$uvExe = Get-Command uv -ErrorAction SilentlyContinue

if (-not $uvExe) {
    Write-Warn "uv not found -- installing automatically..."

    try {
        Write-Host "         Downloading uv installer..."
        $installScript = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1"
        Invoke-Expression $installScript

        Refresh-Path
        $uvExe = Get-Command uv -ErrorAction SilentlyContinue

        if ($uvExe) {
            Write-OK "uv installed: $(uv --version)"
        } else {
            Write-Fail "uv installed but not found on PATH -- please restart PowerShell"
            Write-Hint "Or install manually: winget install astral-sh.uv"
            exit 1
        }
    } catch {
        Write-Fail "uv installation failed: $_"
        Write-Hint "Install manually: winget install astral-sh.uv"
        Write-Hint "Or: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
} else {
    Write-OK "uv found: $(uv --version)"
}

# -- Phase 4: Ensure Python 3.12 via uv --------------------------------------
if (-not $PYTHON) {
    Write-Step "Phase 3: Installing Python 3.12 via uv"
    Write-Host "         Running: uv python install 3.12"
    uv python install 3.12

    try {
        $uvPython = uv python find 3.12 2>$null | Out-String | ForEach-Object { $_.Trim() }
        if ($uvPython -and (Test-Path $uvPython)) {
            $PYTHON = $uvPython
            Write-OK "Python 3.12 installed via uv"
        } else {
            Write-Fail "Failed to install Python via uv"
            exit 1
        }
    } catch {
        Write-Fail "Failed to find Python after uv install: $_"
        exit 1
    }
}

# -- Phase 5: Install Project Dependencies -----------------------------------
if (-not $NoInstall) {
    Write-Step "Phase 4: Installing project dependencies"

    $projectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
    Push-Location $projectRoot

    try {
        if (-not (Test-Path "pyproject.toml")) {
            Write-Fail "pyproject.toml not found at $projectRoot"
            Write-Hint "Run this script from the VibeSOP project directory"
            exit 1
        }

        Write-Host "         Running: uv sync"
        uv sync
        Write-OK "Dependencies installed"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "         (skipped: -NoInstall)" -ForegroundColor Blue
}

# -- Phase 6: Next Steps -----------------------------------------------------
Write-Step "Phase 5: Next steps"
Write-Host ""
Write-Host "  Environment ready! Deploy VibeSOP to your AI platform:"
Write-Host ""
Write-Host "    bash scripts/vibe-install claude-code    # Claude Code"
Write-Host "    bash scripts/vibe-install opencode       # OpenCode"
Write-Host "    bash scripts/vibe-install kimi-cli       # Kimi Code CLI"
Write-Host "    bash scripts/vibe-install pi             # Pi Coding Agent"
Write-Host ""
Write-Host "  Or use the interactive wizard:"
Write-Host ""
Write-Host "    uv run vibe quickstart"
Write-Host ""

if ($Platform) {
    Write-Host "Auto-deploying to: $Platform" -ForegroundColor Blue
    $projectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
    $installScript = Join-Path (Join-Path $projectRoot "scripts") "vibe-install"
    & bash $installScript $Platform
}
