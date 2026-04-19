# Legacy Commands Migration Guide

## Overview

The following CLI commands have been **deprecated** and will be removed in VibeSOP v5.0.0:

- `vibe deploy` - Configuration deployment
- `vibe toolchain` - Development tool management
- `vibe worktree` - Git worktree management
- `vibe checkpoint` - Session state management
- `vibe hooks` - Platform hooks management

These commands are **out of scope for a routing engine** and should be handled by platform-specific tools.

---

## Enabling Legacy Commands

To continue using deprecated commands temporarily:

### Option 1: Environment Variable (Recommended)

```bash
export VIBESOP_ENABLE_LEGACY=1
vibe deploy claude-code
```

### Option 2: Per-Command

```bash
VIBESOP_ENABLE_LEGACY=1 vibe toolchain list
```

### Option 3: Install with Extra (Documentation Only)

```bash
pip install vibesop[legacy]
# Note: This is for documentation purposes only.
# You still need to set VIBESOP_ENABLE_LEGACY=1
```

---

## Migration Paths

### 1. `vibe deploy` → Platform-Specific Methods

**Deprecated:**
```bash
vibe deploy claude-code
vibe deploy claude-code --force
```

**Use instead:**
- **Claude Code**: Copy generated config manually
  ```bash
  vibe build claude-code
  cp -r .vibe/dist/claude-code/* ~/.claude/
  ```
- **Automation**: Use shell scripts or CI/CD
  ```bash
  # Example: deploy.sh
  vibe build claude-code
  rsync -av .vibe/dist/claude-code/ ~/.claude/
  ```

### 2. `vibe toolchain` → System Package Manager

**Deprecated:**
```bash
vibe toolchain list
vibe toolchain install uv
```

**Use instead:**
- **macOS**: Homebrew
  ```bash
  brew install uv
  brew install ruff
  ```
- **Linux**: System package manager
  ```bash
  apt install python3-uv  # Debian/Ubuntu
  dnf install python3-uv   # Fedora
  ```
- **Universal**: pip
  ```bash
  pip install uv ruff pyright
  ```

### 3. `vibe worktree` → Native Git Commands

**Deprecated:**
```bash
vibe worktree list
vibe worktree create feature-x
vibe worktree remove feature-x
```

**Use instead:**
```bash
# List worktrees
git worktree list

# Create worktree
git worktree add .git/worktrees/feature-x feature-x

# Remove worktree
git worktree remove feature-x
```

### 4. `vibe checkpoint` → Git Tags/Branches

**Deprecated:**
```bash
vibe checkpoint save "my-work"
vibe checkpoint list
vibe checkpoint restore abc123
```

**Use instead:**
```bash
# Save checkpoint
git tag checkpoint-my-work
git branch checkpoint-my-work

# List checkpoints
git tag | grep checkpoint

# Restore checkpoint
git checkout checkpoint-my-work
```

### 5. `vibe hooks` → Platform Configuration

**Deprecated:**
```bash
vibe hooks install claude-code
vibe hooks verify claude-code
```

**Use instead:**
- **Claude Code**: Edit `~/.claude/settings.json`
  ```json
  {
    "hooks": {
      "preSessionEnd": "script.sh"
    }
  }
  ```
- **Manual installation**:
  ```bash
  cp my-hooks/pre-session.sh ~/.claude/hooks/
  chmod +x ~/.claude/hooks/pre-session.sh
  ```

---

## Timeline

| Version | Status |
|---------|--------|
| 4.1.0   | Commands deprecated, moved to legacy module |
| 4.2.x   | Commands disabled by default, require `VIBESOP_ENABLE_LEGACY=1` |
| 5.0.0   | **Commands removed entirely** |

---

## Questions?

If you have questions about migration:
- Check [Architecture Overview](architecture/overview.md)
- Review [CLI Documentation](cli/commands.md)
- Open an issue on [GitHub](https://github.com/nehcuh/vibesop-py/issues)
