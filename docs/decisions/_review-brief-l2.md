# L2 Architecture Review Brief — VibeSOP Echo Mode

You are reviewing an **architecture decision** for the VibeSOP project: evolving the system from "router + injector" (L0) to "router + injector + opt-in in-process LLM answer engine" (L2 Echo Mode).

## Why this decision is being made now

v8.2 P1 was scoped as "agent-internal span emission" but implementation revealed VibeSOP has no in-process LLM call sites — it routes queries to external agents (Claude Code / Kimi / Pi) which call LLMs themselves. So the original "wrap LLM calls in spans" plan had no emission points.

User decision after the discovery: **evolve to L2 Echo Mode** so v8.2 observability has real LLM call data to consume.

## The pivot

| Layer | Before | After |
|-------|--------|-------|
| Architecture | Router + Injector | Router + Injector + opt-in EchoEngine |
| LLM calls in process | None (all in external agent) | EchoEngine calls + classifier/orchestrator existing calls (now span-wrapped) |
| GAP-1 emission site | `plan_executor.py` / `skill_injector.py` (non-existent LLM boundaries) | `LLMProvider.call()` / `acall()` (single point covers all callers) |
| Hook response protocol | UserPromptSubmit only | UserPromptSubmit + (P3) PreToolUse with `decision:"block"` |

## EchoEngine design (L2a — v8.2 P1 scope)

**Trigger point**: `AgentRuntime.handle_query()` L461→L463, after intercept confirms `should_route=True`, before routing runs.

**Gating (all must hold)**:
- `config.echo.enabled == true` (off by default, `vibe echo enable` interactive setup)
- `query_length <= 500` chars
- Query does NOT contain complexity markers ("implement / refactor / debug / migrate")
- Query does NOT match tool-heavy skills (TDD, refactoring, debugging skill_ids)
- Rate limit: 10/min per `session_id + project_id`
- Daily budget cap: $1.00 USD default; disable until UTC midnight if exceeded

**On fire**:
- Build tight system prompt: "answer the user's question concisely (under N tokens); do not propose file changes or commands"
- Call LLM (default `claude-haiku-4-5`)
- Return `result.mode="echo"`, `result.skill_content=<answer>`
- task-span metadata gets `echo=true`, `echo_tokens`, `echo_cost_usd`

**On any failure / threshold miss**: silent fallback to normal routing path (user sees no error).

## Hook protocol reality (investigation finding)

VibeSOP runs on `UserPromptSubmit` hook. This hook has **no `decision` / `block` field** in Claude Code's protocol. Returning a `systemMessage` with the echo answer does NOT silence Claude Code — it will still generate a new turn based on the systemMessage.

**Consequence**: L2a (v8.2 P1) achieves observability closure but NOT external agent silence. L2b (P3) requires hook architecture change to `PreToolUse` + `decision:"block"`.

## Revised GAP-1 — single emission point

```python
class LLMProvider:
    def call(self, prompt: str, **kwargs) -> LLMResponse:
        with tracer.span(f"llm:{self.provider_name}", kind="llm") as span:
            span.set_input({"prompt": prompt[:500], "model": kwargs.get("model"), **kwargs})
            try:
                response = self._call_impl(prompt, **kwargs)
                span.set_output({"response": response.text[:500]})
                span.with_tokens(response.tokens_input, response.tokens_output).with_cost(response.cost_usd)
                return response
            except Exception as e:
                span.set_error(str(e))
                raise
```

This single wrap covers: EchoEngine (new), ClassifierAgent (existing), WorkflowEngine (existing), MultiIntentDetector (existing).

## Six adversarial challenges already self-ruled (§20)

1. **CH-L2-1**: Drop `predicted_routing_confidence` gate (chicken-and-egg); use query-shape + skill blacklist instead
2. **CH-L2-2**: Off-by-default + interactive setup
3. **CH-L2-3**: Per-mode p25 baselines; `echo_dominance_warning` insight at >50%
4. **CH-L2-4**: systemMessage prefix "🔊 VibeSOP Echo (informational only)" + analyzer tracks follow-up execution rate
5. **CH-L2-5**: `vibe optimize` runs on non-echo traces only; echo rate >70% sustained 7d = critical insight
6. **CH-L2-6**: Rate limit keys on session+project; daily budget cap $1 default

## What I want from you

Independent verdict on the L2 architecture decision. Be terse. Focus on what I missed.

**Section A — Verdict**: score 1-5 on each: (i) is L2 the right tier (vs L1/L3/nothing)? (ii) is EchoEngine's gating sound? (iii) is the GAP-1 single-emission-point approach correct? (iv) is the L2a/L2b split (hook architecture deferred to P3) acceptable? (v) are the 6 self-rulings in §20 correct?

**Section B — Top 3 concerns**: the three issues most likely to sink L2 if unaddressed.

**Section C — Disagreements**: any of the 6 self-rulings you'd reverse.

**Section D — Missing considerations**: things L2 should address but doesn't.

**Section E — One-sentence overall verdict**.

Do not summarize back. I wrote this. Find weaknesses.
