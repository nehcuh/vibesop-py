# Session Intelligent Routing - Implementation Summary

> **Date**: 2026-04-18
> **Feature**: Claude Code Internal Session Intelligent Routing
> **Status**: ✅ Implemented (Experimental)
> **Version**: v4.3.0

## Problem Statement

The user's actual need (from message #152):

> "我疑问的在智能体里面，譬如我们在 claude 内部，譬如我们在 claude code 的对话中，第一次说评审，claude code 调用了 route，然后我们继续询问问题的时候，譬如根据评审意见进行重构优化，此时可能用 brain storm 或者 plan 模式会更好，claude code 能够智能识别出来？"

**Translation**: The user wants Claude Code to intelligently recognize when to suggest switching skills during an ongoing conversation, based on dialogue context.

**Key Insight**: This is NOT about CLI session management. It's about **Claude Code's internal mechanism** for detecting conversation context changes and suggesting appropriate skill switches.

## Solution Architecture

### How It Works

```
Claude Code Conversation
     ↓
[Pre-Tool Hook] monitors each tool use
     ↓
SessionContext tracks patterns
     ↓
Detects: phase change, topic shift, transition signals
     ↓
UnifiedRouter routes the new user message
     ↓
If different skill + high confidence → Suggest switch
     ↓
Claude Code presents suggestion to user
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

## Implementation Details

### Components Created

1. **`src/vibesop/core/sessions/context.py`** (369 lines)
   - `SessionContext` - Main class for tracking conversation state
   - `RoutingSuggestion` - Data class for re-routing recommendations
   - `ContextChange` - Enum for change severity (NONE, MODERATE, SIGNIFICANT)
   - `ToolUseEvent` - Record of tool usage

2. **`src/vibesop/core/sessions/__init__.py`**
   - Module exports for session management

3. **`src/vibesop/cli/commands/session_cmd.py`** (247 lines)
   - `vibe session record-tool` - Record tool usage
   - `vibe session check-reroute` - Check if re-routing is suggested
   - `vibe session summary` - Show session statistics
   - `vibe session set-skill` - Set current skill
   - `vibe session enable-tracking` - Enable session tracking
   - `vibe session disable-tracking` - Disable session tracking

4. **`src/vibesop/hooks/templates/pre-tool-use.sh.j2`** (Updated)
   - Enhanced hook to support intelligent re-routing
   - Records tool usage
   - Periodically checks for re-routing opportunities
   - Outputs suggestions to Claude Code

5. **`src/vibesop/cli/subcommands/__init__.py`** (Updated)
   - Added session_app subcommand group
   - Registered all session subcommands

6. **`tests/core/sessions/test_context.py`** (347 lines)
   - 18 comprehensive tests covering all functionality
   - Unit tests for individual components
   - Integration tests for common scenarios

7. **`docs/user/session-intelligent-routing.md`**
   - Complete user documentation
   - Usage examples
   - Configuration guide
   - Troubleshooting section

### Key Features

1. **Context Detection**
   - Analyzes recent tool usage (configurable window)
   - Detects phase transitions (debugging → planning → review → testing)
   - Identifies topic shifts from user message keywords

2. **Intelligent Suggestions**
   - Only suggests when confidence > threshold (default 0.7)
   - Respects cooldown period (default 30s between checks)
   - Provides clear reasons for suggestions

3. **Thread-Safe**
   - Uses locks for concurrent access
   - Safe for multi-threaded environments

4. **Configurable**
   - Environment variables for runtime configuration
   - Adjustable thresholds and intervals
   - Can be enabled/disabled per session

## Usage Example

### Scenario: Debugging → Planning Transition

```bash
# Initial: debugging database error
$ export VIBESOP_CURRENT_SKILL=systematic-debugging

# ... conversation with bash, read tools ...

# User: "let's redesign the schema"
$ vibe session check-reroute "let's redesign the schema" --skill systematic-debugging

# Output:
💡 Consider switching skills

From: systematic-debugging
To: planning-with-files
Confidence: 82%

Reason: Context shift detected: systematic-debugging → planning-with-files.
Recent tool usage suggests a phase change.
```

## Integration with Claude Code

### How Claude Code Uses This

1. **Initial Request**
   - User: "review my code"
   - Claude Code: `vibe route "review my code"` → gets `gstack/review`
   - Sets `VIBESOP_CURRENT_SKILL=gstack/review`

2. **During Conversation**
   - Pre-tool hook fires before each tool use
   - Records tool usage asynchronously
   - Every N tool uses, checks for re-routing
   - If change detected, outputs suggestion

3. **Follow-up Request**
   - User: "based on feedback, let's redesign"
   - Hook detects context shift
   - Calls `vibe session check-reroute`
   - Claude Code: "💡 This looks like a design task. Would you like to switch to planning mode?"

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBESOP_CONTEXT_TRACKING` | `false` | Enable/disable session tracking |
| `VIBESOP_REROUTE_CHECK_INTERVAL` | `5` | Check every N tool uses |
| `VIBESOP_REROUTE_THRESHOLD` | `0.7` | Confidence threshold (0.0-1.0) |
| `VIBESOP_CURRENT_SKILL` | `None` | Current active skill |

### SessionContext Parameters

```python
ctx = SessionContext(
    project_root=".",
    reroute_threshold=0.7,      # Confidence threshold
    tool_use_window=10,         # Track recent N tool uses
    reroute_cooldown=30.0,      # Seconds between checks
)
```

## Test Coverage

```
tests/core/sessions/test_context.py::TestToolUseEvent::test_create_event PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_init PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_record_tool_use PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_set_current_skill PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_history_window_limit PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_check_reroute_needed_no_history PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_check_reroute_same_skill PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_check_reroute_cooldown PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_get_session_summary PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_detect_context_change_no_tools PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_phase_transition_detection PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_tool_pattern_analysis PASSED
tests/core/sessions/test_context.py::TestSessionContext::test_phase_inference_from_tools PASSED
tests/core/sessions/test_context.py::TestRoutingSuggestion::test_create_suggestion PASSED
tests/core/sessions/test_context.py::TestRoutingSuggestion::test_create_suggestion_minimal PASSED
tests/core/sessions/test_context.py::TestIntegrationScenarios::test_debugging_to_planning_transition PASSED
tests/core/sessions/test_context.py::TestIntegrationScenarios::test_review_to_brainstorm_transition PASSED
tests/core/sessions/test_context.py::TestIntegrationScenarios::test_implementation_to_testing_transition PASSED

18 passed in 7.96s
```

## Files Modified/Created

### New Files (7)
1. `src/vibesop/core/sessions/context.py` - Core session tracking logic
2. `src/vibesop/core/sessions/__init__.py` - Module exports
3. `src/vibesop/cli/commands/session_cmd.py` - CLI commands
4. `tests/core/sessions/test_context.py` - Comprehensive tests
5. `docs/user/session-intelligent-routing.md` - User documentation
6. `docs/superpowers/summaries/2026-04-18-session-intelligent-routing.md` - This summary

### Modified Files (3)
1. `src/vibesop/hooks/templates/pre-tool-use.sh.j2` - Enhanced hook with intelligent routing
2. `src/vibesop/cli/subcommands/__init__.py` - Added session subcommands
3. `README.md` - Added feature to Quick Start section

## How This Solves the User's Need

The user asked for Claude Code to intelligently recognize when to suggest switching skills during ongoing conversations.

**What I Built:**
- ✅ Session context tracking that monitors tool usage patterns
- ✅ Context change detection (phase transitions, topic shifts)
- ✅ Integration with Claude Code's hooks system
- ✅ Intelligent suggestions with confidence scoring
- ✅ Configurable behavior via environment variables

**How It Works in Practice:**
1. User starts with "review my code" → Claude Code routes to `gstack/review`
2. During conversation, pre-tool hook tracks tool usage (read, edit, bash)
3. User says "let's redesign the architecture based on feedback"
4. Hook detects context shift (review → planning)
5. Calls `vibe session check-reroute` → gets `planning-with-files` with 85% confidence
6. Claude Code suggests: "💡 This looks like a design task. Would you like to switch to planning mode?"

## Next Steps

### For Users
1. Enable tracking: `vibe session enable-tracking`
2. Rebuild Claude Code config: `vibe build claude-code`
3. Start using - suggestions will appear automatically

### For Developers
1. Test with real conversations to tune thresholds
2. Add more sophisticated pattern detection
3. Implement persistent session storage (future)
4. Add user feedback integration (accept/reject)

## Limitations

1. **No Persistent State** - Session context is in-memory only
2. **Single Session** - Doesn't track across multiple Claude Code sessions
3. **Cooldown Period** - Minimum 30 seconds between re-routing checks
4. **Confidence Dependency** - Only suggests when confidence > threshold

## Future Enhancements

- [ ] Persistent session storage across restarts
- [ ] Multi-session pattern learning
- [ ] User feedback integration (learn from accept/reject)
- [ ] Custom trigger rules per project
- [ ] Integration with Claude Code's memory system

## Sources

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)
- [All 12 Hook Events Reference](https://www.pixelmojo.io/blogs/claude-code-hooks-production-quality-ci-cd-patterns)
- [Advanced Best Practices 2026](https://smartscope.blog/en/generative-ai/claude/claude-code-best-practices-advanced-2026/)

---

**Implementation Complete**: All components implemented, tested (18/18 passing), and documented.
**Ready for**: User testing and feedback
**Status**: Experimental - API may change based on usage patterns
