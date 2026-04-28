# Hooks System - Complete Guide

## Overview

The VibeSOP hooks system provides platform-specific hooks that trigger at key points during AI sessions. Unlike traditional shell hooks, these hooks are integrated with the AI workflow and can be managed via CLI commands.

## Available Hooks

### Claude Code Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `pre-session-end` | Before session ends | Flush memory, save session state |
| `pre-tool-use` | Before tool execution | Log tool usage, add validation |
| `post-session-start` | After session starts | Initialize session logging |

### OpenCode Status

⚠️ **OpenCode does not support traditional shell hooks.** However, the AI-based triggers (`memory-flush.md`, `skill-triggers.md`) work on all platforms.

## CLI Commands

### Install Hooks

```bash
# Install hooks for a specific platform
vibe hooks install claude-code

# Install for OpenCode (will show message about no shell hooks)
vibe hooks install opencode
```

### Uninstall Hooks

```bash
# Remove hooks from a platform
vibe hooks uninstall claude-code
```

### Verify Hooks

```bash
# Check hook installation status
vibe hooks verify claude-code
```

### Status Overview

```bash
# Show all platforms and their hook status
vibe hooks status
```

## Integration with AI Workflow

### Session-end Workflow

When a user says "结束了" or "That's all for now":

1. **AI Level** (all platforms):
   - AI reads `rules/memory-flush.md`
   - AI reads `rules/skill-triggers.md`
   - **AI triggers memory flush** automatically
   - No shell hook required

2. **Shell Level** (Claude Code only):
   - `pre-session-end` shell hook executes
    - Can trigger automated cleanup and learning tasks
   - Performs additional cleanup

### Dual-Layer Protection

```
User: "结束了"
    ↓
AI Layer (all platforms):
    ├─ Reads memory-flush.md
    ├─ Triggers session-end skill
    └─ Saves to memory/session.md
    ↓
Shell Layer (Claude Code only):
    ├─ Executes pre-session-end.sh
    ├─ Runs session-end cleanup and retention checks
    └─ Performs cleanup
```

## Hook File Structure

```
~/.claude/hooks/
├── pre-session-end.sh      # Session cleanup
├── pre-tool-use.sh          # Tool validation
└── post-session-start.sh    # Session initialization
```

## Hook Templates

Hooks are generated from Jinja2 templates in:
```
src/vibesop/hooks/templates/
└── pre-session-end.sh.j2
```

## Platform Compatibility

| Feature | Claude Code | OpenCode |
|---------|------------|----------|
| AI Triggers (memory-flush.md) | ✅ | ✅ |
| AI Triggers (skill-triggers.md) | ✅ | ✅ |
| Shell Hooks (pre-session-end.sh) | ✅ | ❌ |
| Hook Installation CLI | ✅ | ✅* |

*OpenCode shows "No hooks defined" message

## Best Practices

1. **Always install hooks after deployment:**
   ```bash
   vibe build claude-code --output ~/.claude
   ```

2. **Verify hooks before important sessions:**
   ```bash
   vibe hooks verify claude-code
   ```

3. **Use AI triggers as primary mechanism:**
   - Work on all platforms
   - No additional setup required
   - Triggered by natural language

4. **Use shell hooks as enhancement:**
   - Platform-specific (Claude Code only)
   - Can run CLI commands
   - Additional cleanup

## Troubleshooting

### Hooks not executing

1. **Check hook permissions:**
   ```bash
   ls -la ~/.claude/hooks/
   ```

2. **Verify hook status:**
   ```bash
   vibe hooks verify claude-code
   ```

3. **Test hook manually:**
   ```bash
   ~/.claude/hooks/pre-session-end.sh
   ```

### AI triggers not working

1. **Check rules deployment:**
   ```bash
   ls ~/.claude/rules/
   ```

2. **Verify memory-flush.md:**
   ```bash
   cat ~/.claude/rules/memory-flush.md
   ```

3. **Rebuild and redeploy:**
   ```bash
   vibe build claude-code --output ~/.claude
   ```

## Migration from Ruby Version

The Python version provides equivalent functionality:

| Feature | Ruby | Python |
|---------|------|--------|
| Hook installation | Manual + bin/vibe-install | `vibe hooks install` |
| Hook management | Manual file editing | CLI commands |
| Hook verification | Manual checks | `vibe hooks verify` |
| Platform support | Claude Code only | Claude Code + OpenCode* |

*OpenCode has no shell hooks but AI triggers work

## Implementation Details

### Hook Installer

Located in `src/vibesop/hooks/installer.py`:
- `install_hooks()` - Install hooks for a platform
- `uninstall_hooks()` - Remove hooks
- `verify_hooks()` - Check installation status

### Hook Points

Defined in `src/vibesop/hooks/points.py`:
- `PRE_SESSION_END` - Before session ends
- `PRE_TOOL_USE` - Before tool execution
- `POST_SESSION_START` - After session starts

### Templates

Located in `src/vibesop/hooks/templates/`:
- `pre-session-end.sh.j2` - Session cleanup template
- `pre-tool-use.sh.j2` - Tool logging template
- `post-session-start.sh.j2` - Session init template
