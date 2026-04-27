# VibeSOP Agent Integration Guide

> **⚠️ Critical Distinction**: This guide describes **in-process Python API integration**. The `set_llm()` method only works when the Agent imports VibeSOP as a Python library and calls the API directly within the same process. It does **NOT** work with CLI subprocess calls (`vibe route`), which require separate LLM configuration. See [README](../README.md) for CLI setup.

This guide shows how to integrate VibeSOP routing into AI Agents (like Claude Code) using the Agent's internal LLM for semantic skill selection.

## Quick Start

```python
from vibesop.agent import AgentRouter, SimpleLLM, SimpleResponse

# 1. Define your LLM wrapper
class AgentLLM(SimpleLLM):
    def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1):
        # Use your Agent's internal LLM here
        response = agent.generate(prompt)
        return SimpleResponse(content=response)

# 2. Create router and inject LLM
router = AgentRouter()
router.set_llm(AgentLLM())

# 3. Route queries (works for multilingual input)
result = router.route("帮我审查代码质量")
if result.has_match:
    print(f"Matched: {result.primary.skill_id}")
    print(f"Confidence: {result.primary.confidence:.0%}")
```

## How It Works

> **⚠️ This requires in-process Python integration.** The `set_llm()` API passes the LLM object by reference within the Python process. CLI subprocess calls (`vibe route`) operate in a separate process and cannot access the Agent's LLM.

1. **LLM Injection**: The Agent injects its internal LLM via `set_llm()`
2. **AI Triage**: When routing, VibeSOP uses the injected LLM for semantic understanding
3. **Multilingual Support**: Works with Chinese, English, and other languages
4. **No API Keys Needed** (in-process only): Uses Agent's existing LLM, no separate configuration

## Multi-Turn Conversations

```python
# Check if re-routing is needed during conversation
reroute = router.check_reroute(
    new_message="帮我审查代码质量",
    current_skill="systematic-debugging"
)

if reroute["should_reroute"]:
    print(f"Switch to: {reroute['recommended_skill']}")
    print(f"Reason: {reroute['reason']}")
```

## Claude Code Integration

For Claude Code, create a custom skill that uses this API:

```python
# File: skills/vibesop-router/SKILL.md
---
id: vibesop-router
name: VibeSOP Router
description: Route user queries to appropriate skills using semantic understanding
intent: Route queries to skills when the user asks for help with a specific task
trigger_mode: suggest
---

# VibeSOP Router

When the user asks for help, use VibeSOP to find the best skill:

```python
from vibesop.agent import AgentRouter, SimpleLLM, SimpleResponse

class ClaudeLLM(SimpleLLM):
    def call(self, prompt, max_tokens=100, temperature=0.1):
        # I'll generate a response based on the prompt
        return SimpleResponse(content=self._route_from_prompt(prompt))

router = AgentRouter()
router.set_llm(ClaudeLLM())
result = router.route("<user_query>")
```

Then follow the matched skill's instructions.
```

## API Reference

### AgentRouter

Main router class for Agent integration.

**Methods:**
- `set_llm(llm_provider)` - Inject Agent's LLM for AI triage
- `route(query, enable_ai_triage=True)` - Route a query to best matching skill
- `check_reroute(new_message, current_skill)` - Check if re-routing is suggested
- `get_session_summary()` - Get session statistics

### SimpleLLM

Base class for LLM wrappers.

**Methods:**
- `configured() -> bool` - Check if LLM is ready (default: True)
- `call(prompt, max_tokens, temperature) -> SimpleResponse` - Call the LLM

### SimpleResponse

Response wrapper for LLM output.

**Attributes:**
- `content: str` - The LLM response text
- `model: str` - Model identifier
- `input_tokens: int` - Input token count (optional)
- `output_tokens: int` - Output token count (optional)

## Benefits

1. **No External API Keys** (in-process only): Uses Agent's internal LLM
2. **Semantic Understanding**: AI triage understands intent, not just keywords
3. **Multilingual**: Works with Chinese, English, and other languages
4. **Session Awareness**: Tracks conversation context for multi-turn scenarios
5. **Python Native**: Direct API integration **within the same process** — not via subprocess
