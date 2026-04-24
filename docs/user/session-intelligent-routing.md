# Session Intelligent Routing

> **Feature**: v4.2.1+
> **Status**: Stable
> **Purpose**: Enable AI agents to intelligently suggest skill switches during ongoing conversations, with persistent session state across CLI invocations
> **Platforms**: Claude Code (hooks), OpenCode (CLI), Generic (CLI)

---

## ⚠️ Opt-In Design

**会话智能追踪默认关闭（`VIBESOP_CONTEXT_TRACKING=false`）**，这是有意的设计选择。

### Why Disabled by Default?

- **🚀 Performance**: Zero overhead when disabled - no impact on normal usage
- **🔒 Privacy**: No tool usage history is recorded without explicit consent
- **🎛️ User Control**: Fully opt-in - you decide when to enable this feature

### How to Enable?

See platform-specific instructions below to enable session tracking.

---

## Overview

VibeSOP's Session Intelligent Routing monitors conversation context and suggests when to switch skills, enabling AI agents across multiple platforms to provide adaptive workflow guidance.

## Problem Solved

**Before**: You start with "review my code" → get `gstack/review`. But when you follow up with "based on feedback, let's redesign the architecture", the AI continues using review skill instead of suggesting planning mode.

**After**: The AI detects the context shift and suggests: "This looks like a design task. Would you like to switch to `planning-with-files` or `riper-workflow`?"

**Works with**:
- ✅ **Claude Code** - Automatic via hooks
- ✅ **OpenCode** - Manual via CLI commands
- ✅ **Any platform** - Manual via CLI commands

## Platform Support

### Claude Code (Automatic)

Claude Code supports hooks, enabling automatic session tracking:

```bash
# Enable automatic tracking
vibe session enable-tracking

# Rebuild config to install hooks
vibe build claude-code
```

**How it works**:
- PreToolUse hook fires before each tool use
- Automatically records tool usage
- Periodically checks for re-routing opportunities
- Outputs suggestions directly to Claude Code

### OpenCode (Manual)

OpenCode doesn't support hooks yet, so use manual CLI commands:

```bash
# Manually record tool usage (call this after each tool use)
vibe session record-tool --tool "read" --skill "systematic-debugging"

# Check for re-routing suggestions
vibe session check-reroute "design new architecture" --skill "systematic-debugging"
```

**Note**: OpenCode support will be improved when hooks are added to the platform.

### Generic / Other Platforms (Manual)

For platforms without hooks, use the generic tracker:

```bash
# Manually record tool usage
vibe session record-tool --tool "read" --skill "systematic-debugging"

# Check for re-routing suggestions
vibe session check-reroute "design new architecture" --skill "systematic-debugging"
```

## How It Works

### Architecture

```
Claude Code Conversation
     ↓
[Pre-Tool Hook] monitors tool usage
     ↓
SessionContext tracks patterns
     ↓
Detects: phase change, topic shift
     ↓
UnifiedRouter routes new message
     ↓
Suggests skill switch if appropriate
     ↓
Claude Code suggests to user
```

### Detection Signals

1. **Tool Usage Patterns**
   - Implementation phase: `edit`, `write` dominant
   - Review phase: `read` dominant
   - Testing phase: `bash`, `run` dominant

2. **Keyword Analysis**
   - Planning: "plan", "design", "architecture", "approach"
   - Implementation: "implement", "code", "write", "add", "fix"
   - Review: "review", "check", "verify", "validate"
   - Testing: "test", "debug", "error", "failing"
   - Brainstorming: "brainstorm", "ideas", "explore", "consider"

3. **Transition Phrases**
   - "now let's..."
   - "next we should..."
   - "moving on to..."
   - "switch to..."

## Usage

### 1. Enable Session Tracking

```bash
vibe session enable-tracking
```

This adds to your shell profile:
```bash
export VIBESOP_CONTEXT_TRACKING="true"
```

Restart your shell or run:
```bash
source ~/.zshrc  # or ~/.bash_profile
```

### 2. Install Pre-Tool Hook

When you run `vibe build claude-code`, the hook is automatically installed to:
```
~/.claude/hooks/pre-tool-use.sh
```

### 3. Configure Environment Variables

Optional customization:

```bash
# How often to check for re-routing (in tool uses)
export VIBESOP_REROUTE_CHECK_INTERVAL="5"

# Confidence threshold for suggestions
export VIBESOP_REROUTE_THRESHOLD="0.7"
```

### 4. Use in Claude Code

No additional setup needed! The hook automatically:

1. Tracks tool usage during conversation
2. Detects context changes
3. Suggests skill switches when appropriate

### 5. Session State Persistence (Automatic)

Starting from v4.2.1, session state is **automatically persisted** between CLI calls:

```bash
# Turn 1: route selects a skill
$ vibe route "help me debug this error"
→ systematic-debugging (confidence: 82%)
# Session saved: current_skill = "systematic-debugging"

# Turn 2: same project, next query — session loaded automatically
$ vibe route "now test the fix"
→ systematic-debugging (confidence: 85%, session stickiness applied)
```

Sessions are isolated per project (derived from project path hash). To isolate further:

```bash
# Terminal A
$ VIBESOP_SESSION_ID=terminal-a vibe route "debug this"

# Terminal B (same project, different session)
$ VIBESOP_SESSION_ID=terminal-b vibe route "test that"
```

To disable session awareness for a single query:

```bash
$ vibe route "one-off query" --no-session
```

## Manual Commands

### Record Tool Use

```bash
vibe session record-tool --tool "read" --skill "systematic-debugging"
```

### Check Re-routing

```bash
vibe session check-reroute "design new architecture" --skill "systematic-debugging"
```

Output:
```
💡 Consider switching skills

From: systematic-debugging
To: planning-with-files
Confidence: 85%

Reason: Context shift detected: systematic-debugging → planning-with-files.
Recent tool usage suggests a phase change.
```

### Session Summary

```bash
vibe session summary
```

Output:
```
Session Summary

Duration: 15.3m
Current skill: systematic-debugging
Tool uses: 23

Tool breakdown:
  • read: 12
  • bash: 8
  • edit: 3

Recent tools:
  • bash (systematic-debugging)
  • read (systematic-debugging)
  • bash (systematic-debugging)
```

### Set Current Skill

```bash
vibe session set-skill "gstack/review"
```

## Platform-Specific Integration

### Claude Code Integration

**How Claude Code Uses This**:

1. **Initial Request**: User says "review my code"
   - Claude Code calls `vibe route "review my code"`
   - Gets recommendation: `gstack/review`
   - Sets `VIBESOP_CURRENT_SKILL=gstack/review`

2. **During Conversation**: Pre-tool hook fires before each tool use
   - Records tool usage automatically
   - Every N tool uses, checks for re-routing
   - If significant change detected, suggests switch

3. **Follow-up Request**: User says "based on feedback, let's redesign"
   - Hook detects context shift
   - Calls `vibe session check-reroute`
   - Claude Code suggests: "💡 Consider switching to planning mode"

### OpenCode Integration

**How OpenCode Users Use This**:

1. **Initial Request**: User says "review my code"
   - OpenCode calls `vibe route "review my code"`
   - Gets recommendation: `gstack/review`

2. **During Conversation**: Manual recording
   - After each tool use, call `vibe session record-tool`
   - Or batch record at key points
   - Check for re-routing when context changes

3. **Follow-up Request**: User says "based on feedback, let's redesign"
   - Call `vibe session check-reroute`
   - OpenCode displays suggestion
   - User decides to switch or continue

### Example Session Flow

```
User: review my authentication code

Claude: [calls vibe route] → gstack/review
      [sets VIBESOP_CURRENT_SKILL=gstack/review]
      I'll review your authentication code...

[Hook fires: record_tool use("read", skill="gstack/review")]

User: the JWT validation looks wrong

Claude: [uses Edit tool]
      [Hook fires: record_tool use("edit", skill="gstack/review")]
      You're right, let me fix that...

User: now let's completely redesign the auth flow

[Hook fires: detects phase change]
[Checks: vibe session check-reroute "redesign auth flow" --skill "gstack/review"]

Claude: 💡 This looks like a design task. Would you like to switch to
      planning mode? I can help you design the new auth flow architecture.
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBESOP_CONTEXT_TRACKING` | `false` | Enable/disable session tracking |
| `VIBESOP_SESSION_ID` | `project-{hash}` | Override session ID for multi-terminal isolation |
| `VIBESOP_REROUTE_CHECK_INTERVAL` | `5` | Check for re-routing every N tool uses |
| `VIBESOP_REROUTE_THRESHOLD` | `0.7` | Confidence threshold for suggestions (0.0-1.0) |
| `VIBESOP_CURRENT_SKILL` | `None` | Current active skill (set by Claude Code) |

### Routing Config

```yaml
# .vibe/config.yaml
routing:
  session_aware: true              # Enable session-state-aware routing
  session_stickiness_boost: 0.03   # Confidence boost for current skill (0.0–0.2)
```

### SessionContext Parameters

```python
from vibesop.core.sessions import SessionContext

ctx = SessionContext(
    project_root=".",
    reroute_threshold=0.7,      # Confidence threshold
    tool_use_window=10,         # Track recent N tool uses
)
```

## Detection Logic

### Context Change Levels

1. **NONE** - No significant change, continue with current skill
2. **MODERATE** - Some shift, worth considering
3. **SIGNIFICANT** - Strong signal to re-route

### Phase Detection

The system infers current phase from tool patterns:

```python
phase_indicators = {
    "planning": ["read"],
    "implementation": ["edit", "write"],
    "review": ["read"],
    "testing": ["bash", "run"],
}
```

### Decision Flow

```
Check cooldown period
     ↓
Get recent tool usage (last N events)
     ↓
Analyze tool patterns
     ↓
Detect phase from user message keywords
     ↓
Compare current phase vs detected phase
     ↓
Route new message through UnifiedRouter
     ↓
If different skill + high confidence → Suggest switch
```

## Examples

### Scenario 1: Debugging → Planning

```bash
# Initial: debugging database error
$ VIBESOP_CURRENT_SKILL=systematic-debugging

# ... conversation with bash, read tools ...

# User: "let's redesign the schema"
$ vibe session check-reroute "let's redesign the schema" --skill systematic-debugging

# Output:
💡 Consider switching skills
From: systematic-debugging
To: planning-with-files
Confidence: 82%
```

### Scenario 2: Review → Brainstorm

```bash
# Initial: reviewing PR
$ VIBESOP_CURRENT_SKILL=gstack/review

# ... conversation with read tools ...

# User: "let's brainstorm alternative approaches"
$ vibe session check-reroute "brainstorm alternatives" --skill gstack/review

# Output:
💡 Consider switching skills
From: gstack/review
To: superpowers/brainstorm
Confidence: 78%
```

### Scenario 3: Implementation → Testing

```bash
# Initial: implementing feature
$ VIBESOP_CURRENT_SKILL=planning-with-files

# ... conversation with edit, write tools ...

# User: "the tests are failing"
$ vibe session check-reroute "tests failing" --skill planning-with-files

# Output:
💡 Consider switching skills
From: planning-with-files
To: systematic-debugging
Confidence: 91%
```

## Troubleshooting

### Hook Not Firing

**Problem**: Tool usage not being tracked

**Solutions**:
1. Check hook is executable: `ls -la ~/.claude/hooks/pre-tool-use.sh`
2. Enable tracking: `export VIBESOP_CONTEXT_TRACKING="true"`
3. Check hook permissions: `chmod +x ~/.claude/hooks/pre-tool-use.sh`

### No Suggestions

**Problem**: Context changes not being detected

**Solutions**:
1. Lower threshold: `export VIBESOP_REROUTE_THRESHOLD="0.6"`
2. Increase check frequency: `export VIBESOP_REROUTE_CHECK_INTERVAL="3"`
3. Check session summary: `vibe session summary`

### Too Many Suggestions

**Problem**: Annoying frequent suggestions

**Solutions**:
1. Raise threshold: `export VIBESOP_REROUTE_THRESHOLD="0.8"`
2. Decrease check frequency: `export VIBESOP_REROUTE_CHECK_INTERVAL="10"`
3. Disable tracking: `vibe session disable-tracking`

## API Reference

### SessionContext

```python
class SessionContext:
    def __init__(
        self,
        project_root: str = ".",
        router: UnifiedRouter | None = None,
        reroute_threshold: float = 0.7,
        tool_use_window: int = 10,
        reroute_cooldown: float = 5.0,
        session_id: str | None = None,  # Auto-derived from project hash if None
    )

    def record_tool_use(
        self,
        tool_name: str,
        skill: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None

    def set_current_skill(self, skill_id: str) -> None

    def check_reroute_needed(self, user_message: str) -> RoutingSuggestion

    def get_session_summary(self) -> dict[str, Any]

    def record_route_decision(self, query: str, skill_id: str) -> None

    def get_habit_boost(self, query: str) -> dict[str, float]

    def to_dict(self) -> dict[str, Any]

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        project_root: str = ".",
        router: UnifiedRouter | None = None,
    ) -> SessionContext

    def save(self, storage_dir: str | Path | None = None) -> Path

    @classmethod
    def load(
        cls,
        session_id: str = "default",
        project_root: str = ".",
        router: UnifiedRouter | None = None,
        storage_dir: str | Path | None = None,
    ) -> SessionContext
```

### RoutingSuggestion

```python
@dataclass
class RoutingSuggestion:
    should_reroute: bool
    recommended_skill: str | None = None
    confidence: float = 0.0
    reason: str = ""
    current_skill: str | None = None
```

## Habit Learning

### Query Pattern Recognition

Starting from v4.2.1, VibeSOP learns from your routing decisions:

**How it works**:
1. Each `route()` call records the query pattern → selected skill mapping
2. When the same pattern occurs **3+ times**, it becomes a "habit"
3. Future queries matching that pattern receive a **+0.08 confidence boost**

**Example**:
```bash
# Turn 1
$ vibe route "deploy to staging" → deploy-k8s (habit recorded)

# Turn 5 (same pattern, 3rd+ occurrence)
$ vibe route "deploy to staging" → deploy-k8s (85% → 93% with habit boost)
```

**Pattern extraction**: Uses embedding-based semantic similarity (not just keyword matching) so "deploy to staging" and "push to k8s staging" can match the same habit.

**Storage**: Habit patterns are persisted in the session file alongside `current_skill`.

---

## Quality-Based Routing

### Grade Impact on Confidence

Skill quality grades (from `vibe skills report`) directly affect routing:

| Grade | Routing Impact |
|-------|---------------|
| A | +0.05 confidence boost |
| B | +0.02 confidence boost |
| C | No change |
| D | -0.02 confidence demote |
| F | -0.05 confidence demote |

**Protection**: Only applies when a skill has `>= 3` total routes to avoid early misjudgment.

**Disable**: Set `routing.enable_quality_boost: false` in config.

---

## Limitations

### Platform-Specific

**Claude Code**:
- Session state persists across CLI calls within the same project
- Different projects are automatically isolated
- Multiple Claude Code windows on the same project share state unless `VIBESOP_SESSION_ID` is used

**OpenCode / Other Platforms**:
- Manual tool usage recording required
- No automatic tracking via hooks
- Session state persists across CLI calls

### General

- Cooldown period: Minimum 5 seconds between re-routing checks
- Confidence dependency: Only suggests when confidence > threshold
- Cross-session learning limited (pattern recognition within single session only)

## Future Enhancements

### Cross-Platform

- [ ] **OpenCode hooks support** - When OpenCode adds hooks, enable automatic tracking
- [ ] **Cursor integration** - Add Cursor platform support
- [ ] **Continue.dev integration** - Add Continue.dev platform support
- [ ] **Aider integration** - Add Aider platform support

### Features

- [x] Persistent session storage across restarts (v4.2.1)
- [ ] Session TTL — auto-reset stale sessions after inactivity
- [ ] Multi-session pattern learning
- [ ] User feedback integration (accept/reject suggestions)
- [ ] Custom trigger rules per project
- [ ] Integration with platform memory systems

## Related Documentation

- [Routing System](../architecture/routing-system.md)
- [Hooks Guide](../dev/hooks-guide.md)
- [Skill Triggers](../claude-code/rules/skill-triggers.md)

---

**Status**: Stable
**Feedback**: Report issues at https://github.com/nehcuh/vibesop-py/issues
