#!/bin/bash
# VibeSOP Bootstrap Script (Linux / macOS / Windows Git Bash)
#
# Detects system environment, installs prerequisites (uv), and sets up the project.
# This is the recommended entry point for first-time users.
#
# Windows users without Git Bash: use bootstrap.ps1 instead.
#   .\scripts\bootstrap.ps1
#
# Usage:
#   ./scripts/bootstrap.sh                # Full bootstrap (detect + install deps)
#   ./scripts/bootstrap.sh --no-install   # Environment check only (dry-run)
#   ./scripts/bootstrap.sh --platform claude-code  # Bootstrap + deploy to platform
#   ./scripts/bootstrap.sh --help         # Show this help
#
# What this script does:
#   1. Detects your operating system (Linux / macOS / Windows)
#   2. Checks for Python 3.12+
#   3. Checks for uv — auto-installs if missing
#   4. Runs `uv sync` to install project dependencies
#   5. Guides you to the next step: deploying to your AI platform

set -e

# ── Colours (consistent with vibe-install) ──────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Print helpers ───────────────────────────────────────────────────────────
print_info()    { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()   { echo -e "${RED}❌ $1${NC}"; }
print_step()    { echo -e "\n${CYAN}${BOLD}═══ $1 ═══${NC}"; }
print_hint()    { echo -e "   ${CYAN}💡 $1${NC}"; }

# ── Banner ──────────────────────────────────────────────────────────────────
banner() {
    echo ""
    echo -e "${BOLD}  🚀 VibeSOP Bootstrap${NC}"
    echo "  ────────────────────────────────────────"
    echo "  Skill Operating System for AI-assisted development"
    echo ""
}

# ── Phase 1: OS Detection ───────────────────────────────────────────────────
detect_os() {
    print_step "Phase 1: Detecting operating system"

    local os
    os=$(uname -s 2>/dev/null || echo "Unknown")

    case "$os" in
        Linux)
            OS="linux"
            print_success "Detected: Linux"
            ;;
        Darwin)
            OS="macos"
            print_success "Detected: macOS"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            OS="windows"
            print_success "Detected: Windows (Git Bash / MSYS2)"
            print_hint "uv will be installed via PowerShell; if that fails, try: winget install astral-sh.uv"
            ;;
        *)
            print_warning "Unknown OS: $os — assuming Linux-like behaviour"
            OS="linux"
            ;;
    esac
}

# ── Helper: check if a python command is the Windows Store stub ──────────────
_is_store_stub() {
    local cmd=$1
    local output
    output=$("$cmd" --version 2>&1 || true)
    # The Windows Store stub prints "Python was not found..." or opens a dialog
    case "$output" in
        *"not found"*|*"Microsoft Store"*|*"App execution aliases"*)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

# ── Helper: find a real Python 3.12+ executable ──────────────────────────────
_find_python() {
    # Try python3, then python, skipping Windows Store stubs
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            local resolved
            resolved=$(command -v "$candidate")
            # Skip Windows Store stubs (located in WindowsApps, show "not found")
            if [ "$OS" = "windows" ] && _is_store_stub "$resolved"; then
                continue
            fi
            local maj min
            maj=$("$resolved" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
            min=$("$resolved" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
            if [ "$maj" -ge 3 ] && [ "$min" -ge 12 ]; then
                echo "$resolved"
                return 0
            fi
        fi
    done

    # On Windows, try uv-managed Python as a fallback
    if [ "$OS" = "windows" ] && command -v uv &>/dev/null; then
        local uv_python
        uv_python=$(uv python find 3.12 2>/dev/null || true)
        if [ -n "$uv_python" ] && [ -x "$uv_python" ]; then
            echo "$uv_python"
            return 0
        fi
    fi

    return 1
}

# ── Phase 2: Python Check ───────────────────────────────────────────────────
check_python() {
    print_step "Phase 2: Checking Python 3.12+"

    PYTHON=$(_find_python || true)

    if [ -z "$PYTHON" ]; then
        print_error "Python 3.12+ is not available"
        echo ""
        echo "  VibeSOP requires Python 3.12 or later. Options:"
        echo ""
        if [ "$OS" = "windows" ]; then
            echo "    1) Let uv manage it (recommended):"
            echo "       After uv is installed, run: uv python install 3.12"
            echo ""
            echo "    2) Install system-wide:"
            echo "       winget install Python.Python.3.12"
        elif [ "$OS" = "linux" ]; then
            echo "    Ubuntu/Debian:  sudo apt install python3.12 python3.12-venv"
            echo "    Fedora:         sudo dnf install python3.12"
            echo "    Arch:           sudo pacman -S python"
        elif [ "$OS" = "macos" ]; then
            echo "    brew install python@3.12"
        fi
        echo "    Or download from: https://www.python.org/downloads/"
        echo ""
        # On Windows, don't exit — uv can install Python for us later
        if [ "$OS" = "windows" ]; then
            print_info "uv can manage Python for you — proceeding to Phase 3..."
            PYTHON=""
            return 0
        fi
        echo "  Then re-run: ./scripts/bootstrap.sh"
        exit 1
    fi

    PYTHON_VERSION=$("$PYTHON" --version 2>&1 | awk '{print $2}')
    print_success "Python $PYTHON_VERSION ($PYTHON)"
}

# ── Phase 3: uv Check & Auto-Install ────────────────────────────────────────
ensure_uv() {
    print_step "Phase 3: Checking uv"

    # uv may be installed but not on the current session's PATH (e.g. Git Bash
    # on Windows doesn't always inherit ~/.local/bin). Check common locations.
    for uv_dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -d "$uv_dir" ] && { [ -x "$uv_dir/uv" ] || [ -x "$uv_dir/uv.exe" ]; }; then
            export PATH="$uv_dir:$PATH"
        fi
    done

    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>&1)
        print_success "uv found: $UV_VERSION"
        _ensure_python_via_uv
        return 0
    fi

    print_warning "uv not found — installing automatically..."

    local install_ok=false

    case "$OS" in
        linux|macos)
            print_info "Downloading uv installer (curl)..."
            if command -v curl &>/dev/null; then
                curl -LsSf https://astral.sh/uv/install.sh | sh && install_ok=true
            else
                print_error "curl is not available — cannot download uv"
                print_hint "Install curl first, or install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
                exit 1
            fi
            ;;
        windows)
            print_info "Downloading uv installer (PowerShell)..."
            if command -v powershell &>/dev/null; then
                powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" && install_ok=true
            elif command -v powershell.exe &>/dev/null; then
                powershell.exe -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" && install_ok=true
            else
                print_error "PowerShell not found — cannot install uv automatically"
                print_hint "Install uv manually: winget install astral-sh.uv"
                print_hint "Or: https://docs.astral.sh/uv/getting-started/installation/"
                exit 1
            fi
            ;;
        *)
            print_error "Unsupported OS for auto-install: $OS"
            exit 1
            ;;
    esac

    if [ "$install_ok" = true ]; then
        # Reload PATH — uv installer may put binaries in ~/.local/bin
        # (Linux/macOS) or ~/.cargo/bin (Windows via PowerShell installer) or
        # ~/.local/bin (Windows via the standalone installer).
        if [ -f "$HOME/.local/bin/env" ]; then
            # shellcheck source=/dev/null
            . "$HOME/.local/bin/env"
        fi
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

        if command -v uv &>/dev/null; then
            print_success "uv installed: $(uv --version)"
        else
            print_warning "uv installed but not on PATH — please restart your terminal"
            print_hint "  export PATH=\"\$HOME/.local/bin:\$HOME/.cargo/bin:\$PATH\""
            exit 1
        fi
    else
        print_error "uv installation failed"
        exit 1
    fi

    _ensure_python_via_uv
}

# ── Helper: ensure Python 3.12 is available via uv (Windows fallback) ────────
_ensure_python_via_uv() {
    # If we already have a real system Python, nothing to do
    if [ -n "$PYTHON" ]; then
        return 0
    fi

    # On Windows, uv can download and manage Python for us
    if [ "$OS" = "windows" ]; then
        print_info "No system Python found — using uv to install Python 3.12..."
        uv python install 3.12
        PYTHON=$(uv python find 3.12 2>/dev/null || true)
        if [ -n "$PYTHON" ] && [ -x "$PYTHON" ]; then
            print_success "Python 3.12 installed via uv: $PYTHON"
        else
            print_error "Failed to install Python via uv"
            exit 1
        fi
    fi
}

# ── Phase 4: Install Project Dependencies ───────────────────────────────────
install_deps() {
    print_step "Phase 4: Installing project dependencies"

    # Find project root (where pyproject.toml lives)
    PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
    cd "$PROJECT_ROOT"

    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found at $PROJECT_ROOT"
        print_hint "Make sure you're running this script from the VibeSOP project directory"
        exit 1
    fi

    print_info "Running: uv sync"
    uv sync

    # Install vibesop as a global CLI tool so `vibe` is on PATH.
    # Required by platform hooks (e.g. Grok Build JSON hooks call `vibe route --hook`).
    print_info "Running: uv tool install . (installs 'vibe' CLI globally)"
    uv tool install . --force 2>/dev/null || print_warning "'uv tool install .' failed — hooks may need 'uv run vibe' instead"

    print_success "Dependencies installed successfully"
}

# ── Phase 5: Next Steps ─────────────────────────────────────────────────────
show_next_steps() {
    print_step "Phase 5: Next steps"

    echo ""
    echo "  ✨ Environment ready! Now deploy VibeSOP to your AI platform:"
    echo ""
    echo "     ./scripts/vibe-install claude-code   # Claude Code"
    echo "     ./scripts/vibe-install opencode      # OpenCode"
    echo "     ./scripts/vibe-install kimi-cli      # Kimi Code CLI"
    echo "     ./scripts/vibe-install pi            # Pi Coding Agent"
    echo ""
    echo "  Or use the interactive wizard:"
    echo ""
    echo "     uv run vibe quickstart"
    echo ""

    if [ -n "$AUTO_PLATFORM" ]; then
        print_info "Automatically deploying to: $AUTO_PLATFORM"
        PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
        "$PROJECT_ROOT/scripts/vibe-install" "$AUTO_PLATFORM"
    fi
}

# ── Main ────────────────────────────────────────────────────────────────────
main() {
    banner

    RUN_INSTALL=true
    AUTO_PLATFORM=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-install)
                RUN_INSTALL=false
                shift
                ;;
            --platform)
                AUTO_PLATFORM="$2"
                shift 2
                ;;
            -h|--help)
                echo "VibeSOP Bootstrap Script"
                echo ""
                echo "Usage:"
                echo "  $0                    Full bootstrap"
                echo "  $0 --no-install       Environment check only (dry-run)"
                echo "  $0 --platform <name>  Bootstrap + deploy to platform"
                echo ""
                echo "Options:"
                echo "  --no-install     Skip 'uv sync' (check environment only)"
                echo "  --platform NAME  Auto-deploy to platform after bootstrap"
                echo "                   (claude-code | opencode | kimi-cli | pi)"
                echo ""
                exit 0
                ;;
            *)
                print_warning "Unknown option: $1"
                shift
                ;;
        esac
    done

    detect_os
    check_python
    ensure_uv

    if [ "$RUN_INSTALL" = true ]; then
        install_deps
    else
        print_info "Skipping dependency installation (--no-install)"
    fi

    show_next_steps
}

main "$@"
