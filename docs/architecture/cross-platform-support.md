# Cross-Platform Support

> **Version**: v4.3.0
> **Updated**: 2026-04-18

## Overview

VibeSOP is designed to work across multiple AI coding platforms. The architecture uses the **Adapter Pattern** to provide platform-specific configurations while maintaining a core SkillOS engine.

## Supported Platforms

| Platform | Status | Auto-Routing | Hooks | Session Tracking |
|----------|--------|--------------|-------|------------------|
| **Claude Code** | ✅ Full Support | ✅ Yes | ✅ Yes | ✅ Automatic |
| **Kimi Code CLI** | ✅ Full Support | ✅ Yes | ⚠️ Beta | ✅ Automatic |
| **OpenCode** | ✅ Basic Support | ✅ Yes | ❌ No | ⚠️ Manual |
| **Cursor** | 🚧 Planned | - | - | - |
| **Continue.dev** | 🚧 Planned | - | - | - |
| **Aider** | 🚧 Planned | - | - | - |
| **Generic** | ✅ Always Available | ✅ Yes | ❌ No | ⚠️ Manual |

## Architecture

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                  │
│  (Platform-specific: Claude Code, OpenCode, etc.)   │
└────────────────────┬────────────────────────────────┘
                     │
                     │ Adapter Pattern
                     │
┌────────────────────▼────────────────────────────────┐
│                  Application Layer                   │
│              (VibeSOP Core Logic)                   │
│                                                      │
│  • UnifiedRouter (7-layer routing pipeline)         │
│  • SessionContext (conversation tracking)           │
│  • SkillManager (skill discovery)                   │
│  • Preference Learning                              │
└────────────────────┬────────────────────────────────┘
                     │
                     │ Platform-agnostic APIs
                     │
┌────────────────────▼────────────────────────────────┐
│                  Infrastructure Layer                │
│              (Utilities & Integrations)              │
│                                                      │
│  • Matchers (TF-IDF, embedding, etc.)               │
│  • Converters (gstack, superpowers formats)        │
│  • Security (scanner, auditor)                     │
│  • LLM Integration (triage service)                │
└──────────────────────────────────────────────────────┘
```

### Adapter Pattern

Each platform has an adapter that implements the `PlatformAdapter` interface:

```python
class PlatformAdapter(ABC):
    """Base class for platform adapters."""

    @abstractmethod
    def platform_name(self) -> str:
        """Return platform identifier."""
        pass

    @abstractmethod
    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Generate platform-specific configuration."""
        pass

    @abstractmethod
    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install platform hooks if supported."""
        pass
```

**Implementations**:
- `ClaudeCodeAdapter` - Generates CLAUDE.md, rules/, skills/, hooks/
- `KimiCliAdapter` - Generates config.toml, skills/
- `OpenCodeAdapter` - Generates config.yaml, skills/
- Future: `CursorAdapter`, `ContinueAdapter`, etc.

## Session Tracking Across Platforms

### Platform Abstraction Layer

Session tracking uses the `SessionTracker` interface to provide platform-agnostic functionality:

```python
class SessionTracker(ABC):
    """Abstract base class for platform-specific session tracking."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if tracking is available."""
        pass

    @abstractmethod
    def record_tool_use(self, tool_name: str, skill: str | None = None) -> None:
        """Record a tool use event."""
        pass

    @abstractmethod
    def check_reroute(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing should be suggested."""
        pass
```

**Implementations**:

1. **`HookBasedSessionTracker`** (Claude Code)
   - Uses PreToolUse hooks for automatic tracking
   - No manual intervention required
   - In-memory state (current session only)

2. **`GenericSessionTracker`** (Kimi Code CLI, OpenCode, Others)
   - Uses CLI commands for manual tracking
   - User calls `vibe session record-tool`
   - Persistent state (saved to ~/.vibesop/session-state.json)

   Note: Kimi Code CLI supports hooks via inline `[[hooks]]` arrays in
   config.toml, but the current implementation uses the generic tracker
   for simplicity. Future versions may add hook-based tracking.

### Auto-Detection

```python
def get_tracker(platform: str = "auto") -> SessionTracker:
    """Get the appropriate session tracker for a platform."""
    if platform == "auto":
        platform = _detect_platform()

    if platform == "claude-code":
        return HookBasedSessionTracker(...)
    else:
        return GenericSessionTracker(...)
```

## Platform-Specific Features

### Claude Code

**Strengths**:
- ✅ Full hooks support (12 hook events)
- ✅ SKILL.md format specification
- ✅ Rich markdown configuration (CLAUDE.md, rules/, docs/)
- ✅ Automatic session tracking via PreToolUse hook

**Configuration Output**:
```
~/.claude/
├── CLAUDE.md              # Main entry point
├── rules/                 # Always-loaded rules
│   ├── behaviors.md
│   ├── routing.md
│   └── skill-triggers.md
├── docs/                  # On-demand documentation
│   ├── safety.md
│   ├── skills.md
│   └── task-routing.md
├── skills/                # Skill definitions (symlinks)
│   ├── systematic-debugging/
│   └── gstack/
└── hooks/                 # Lifecycle hooks
    ├── pre-tool-use.sh    # Session tracking
    ├── pre-session-end.sh
    └── post-session-start.sh
```

**Usage**:
```bash
vibe build claude-code
vibe session enable-tracking  # Enable automatic tracking
```

### Kimi Code CLI

**Strengths**:
- ✅ Agent Skills open standard compatible
- ✅ Single TOML configuration file
- ✅ Skills automatically discovered from ~/.kimi/skills/
- ✅ Supports inline hooks via [[hooks]] arrays
- ✅ Fast startup (minimal files)

**Limitations**:
- ⚠️ Hooks are inline in config.toml (different mechanism from file-based hooks)
- ⚠️ No rich markdown rules system like Claude Code

**Configuration Output**:
```
~/.kimi/
├── config.toml            # Main configuration
├── skills/                # Skill definitions
│   ├── systematic-debugging/
│   └── gstack/
└── README.md              # Skill catalog
```

**Usage**:
```bash
vibe build kimi-cli
vibe switch kimi-cli
```

Kimi Code CLI uses the Agent Skills open standard, making its skill format
fully compatible with Claude Code skills. Skills are automatically loaded
from `~/.kimi/skills/` at startup.

### OpenCode

**Strengths**:
- ✅ Simple YAML configuration
- ✅ Fast startup (minimal files)
- ✅ Easy to integrate

**Limitations**:
- ❌ No hooks support (yet)
- ⚠️ Manual session tracking required

**Configuration Output**:
```
~/.opencode/
├── config.yaml            # Main configuration
├── skills/                # Skill definitions
│   ├── systematic-debugging/
│   └── gstack/
└── README.md              # Skill catalog
```

**Usage**:
```bash
vibe build opencode

# Manual tracking
vibe session record-tool --tool "read" --skill "systematic-debugging"
vibe session check-reroute "design this" --skill "systematic-debugging"
```

## Future Platform Support

### Adding a New Platform

To add support for a new platform:

1. **Create Adapter**
```python
class NewPlatformAdapter(PlatformAdapter):
    def platform_name(self) -> str:
        return "new-platform"

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        # Generate platform-specific configuration
        pass

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        # Install hooks if platform supports them
        pass
```

2. **Register Adapter**
```python
# src/vibesop/adapters/__init__.py
from .new_platform import NewPlatformAdapter

__all__ = [
    # ...
    "NewPlatformAdapter",
]
```

3. **Add CLI Command**
```python
# src/vibesop/cli/main.py
@app.command()
def build(
    platform: str = typer.Option("claude-code", "--platform", "-p")
):
    """Build configuration for specified platform."""
    # ...
```

4. **Update Documentation**
- Add platform to support matrix
- Document platform-specific features
- Provide usage examples

### Platform Roadmap

**Phase 1: Current Platforms** (v4.3.0)
- ✅ Claude Code - Full support with hooks
- ✅ Kimi Code CLI - Full support with inline hooks
- ✅ OpenCode - Basic support, manual tracking

**Phase 2: Enhanced Platforms** (v4.4.0)
- [ ] Add Kimi Code CLI hook-based session tracking
- [ ] Add OpenCode hooks support when available
- [ ] Automatic session tracking for OpenCode
- [ ] Platform-specific optimizations

**Phase 3: New Platforms** (v4.5.0+)
- [ ] Cursor support
- [ ] Continue.dev support
- [ ] Aider support
- [ ] Platform-specific UI integrations

## Unified Core, Platform-Specific Presentation

The key design principle is **"Unified Core, Platform-Specific Presentation"**:

### Core (Unified Across Platforms)

```python
# These work the same on all platforms
from vibesop.core.routing import UnifiedRouter
from vibesop.core.skills import SkillManager
from vibesop.core.sessions import get_tracker

router = UnifiedRouter()
result = router.route("debug this error")  # Same everywhere
```

### Presentation (Platform-Specific)

```python
# Claude Code
vibe build claude-code  # → CLAUDE.md, rules/, hooks/

# Kimi Code CLI
vibe build kimi-cli     # → config.toml, skills/

# OpenCode
vibe build opencode     # → config.yaml, skills/

# Future: Cursor
vibe build cursor       # → cursor.json, skills/
```

## Migration Between Platforms

Users can easily switch between platforms:

```bash
# Start with Claude Code
vibe build claude-code
# → Uses ~/.claude/

# Switch to Kimi Code CLI
vibe build kimi-cli
# → Uses ~/.kimi/
# → Same routing, same skills, different config format

# Switch to OpenCode
vibe build opencode
# → Uses ~/.opencode/
# → Same routing, same skills, different config format

# Switch back
vibe build claude-code
# → Uses ~/.claude/
# → Skills automatically synced
```

## Best Practices

### For Platform Adapter Authors

1. **Follow the Adapter interface** - Implement all required methods
2. **Document platform limitations** - Be clear about what's supported
3. **Test configuration output** - Ensure generated files work
4. **Handle missing features gracefully** - Degrade gracefully if platform lacks features

### For Users

1. **Choose the right platform** - Use the platform you actually use
2. **Test configuration** - Run `vibe doctor` after building
3. **Report issues** - File bugs for platform-specific problems
4. **Share feedback** - Help improve platform support

## Related Documentation

- [Claude Code Adapter](../adapters/claude_code.md)
- [Kimi Code CLI Adapter](../adapters/kimi_cli.md)
- [OpenCode Adapter](../adapters/opencode.md)
- [Session Intelligent Routing](../user/session-intelligent-routing.md)
- [Adapter Protocol](../dev/adapter-protocol.md)

---

**Last Updated**: 2026-04-18
**Maintained By**: VibeSOP Team
