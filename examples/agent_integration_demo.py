#!/usr/bin/env python3
"""Demo: VibeSOP Agent Integration.

This shows how an AI Agent (like Claude Code) can use VibeSOP routing
with its internal LLM for semantic skill selection.

Usage:
    python examples/agent_integration_demo.py
"""


from vibesop.agent import AgentRouter, SimpleLLM, SimpleResponse


class DemoAgentLLM(SimpleLLM):
    """Demo LLM wrapper that simulates Agent's internal LLM.

    In a real Agent, this would wrap the Agent's actual LLM call.
    """

    def __init__(self, model_name: str = "claude-sonnet-4"):
        self.model_name = model_name
        self._demo_responses = {
            "帮我审查代码质量": '{"skill_id": "gstack/review", "confidence": 0.92}',
            "帮我调试这个错误": '{"skill_id": "systematic-debugging", "confidence": 0.95}',
            "code review": '{"skill_id": "superpowers/review", "confidence": 0.88}',
            "debug this error": '{"skill_id": "systematic-debugging", "confidence": 0.91}',
            "设计新架构": '{"skill_id": "gstack/architect", "confidence": 0.87}',
            "optimize performance": '{"skill_id": "superpowers/optimize", "confidence": 0.85}',
        }

    def call(self, prompt: str, _max_tokens: int = 100, _temperature: float = 0.1) -> SimpleResponse:
        """Simulate LLM call for routing.

        In production, this would call the Agent's actual LLM.
        For demo, we return pre-defined responses based on query keywords.
        """
        # Check if any keyword matches our demo responses
        for keyword, response in self._demo_responses.items():
            if keyword.lower() in prompt.lower() or prompt.lower() in keyword.lower():
                return SimpleResponse(content=response, model=self.model_name)

        # Default fallback response
        return SimpleResponse(
            content='{"skill_id": "fallback-llm", "confidence": 0.5}',
            model=self.model_name
        )


def demo_basic_routing():
    """Demo 1: Basic routing with Agent's LLM."""
    print("=" * 60)
    print("Demo 1: Basic Semantic Routing")
    print("=" * 60)

    # Create router with Agent's LLM
    router = AgentRouter(project_root=".")
    router.set_llm(DemoAgentLLM())

    # Test queries in different languages
    queries = [
        "帮我审查代码质量",  # Chinese: code review
        "帮我调试这个错误",  # Chinese: debug error
        "code review",      # English
        "debug this error", # English
    ]

    for query in queries:
        result = router.route(query, enable_ai_triage=True)
        if result.has_match:
            print(f"\nQuery: {query}")
            print(f"  → Matched: {result.primary.skill_id}")
            print(f"  → Confidence: {result.primary.confidence:.0%}")
            print(f"  → Layer: {result.primary.layer.value}")
        else:
            print(f"\nQuery: {query}")
            print("  → No match found")


def demo_multi_turn_reroute():
    """Demo 2: Multi-turn conversation with re-routing detection."""
    print("\n" + "=" * 60)
    print("Demo 2: Multi-Turn Re-routing Detection")
    print("=" * 60)

    router = AgentRouter(project_root=".")
    router.set_llm(DemoAgentLLM())

    # Simulate a multi-turn conversation
    conversation = [
        ("帮我调试这个错误", "systematic-debugging"),  # Turn 1: debugging
        ("继续排查", "systematic-debugging"),         # Turn 2: continue debugging
        ("帮我审查代码质量", None),                   # Turn 3: switch to review
    ]

    for i, (query, current_skill) in enumerate(conversation, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {query}")

        if current_skill:
            print(f"Current skill: {current_skill}")

            # Check if re-routing is suggested
            reroute_info = router.check_reroute(query, current_skill)
            if reroute_info["should_reroute"]:
                print(f"💡 Suggestion: Switch to {reroute_info['recommended_skill']}")
                print(f"   Reason: {reroute_info['reason']}")
            else:
                print(f"✓ Continue with {current_skill}")
        else:
            # First turn - do initial routing
            result = router.route(query)
            if result.has_match:
                print(f"→ Routed to: {result.primary.skill_id}")


def demo_session_tracking():
    """Demo 3: Session tracking and analytics."""
    print("\n" + "=" * 60)
    print("Demo 3: Session Tracking")
    print("=" * 60)

    router = AgentRouter(project_root=".")

    # Get session summary
    summary = router.get_session_summary()
    print(f"\nSession Duration: {summary['duration_seconds']:.1f}s")
    print(f"Current Skill: {summary['current_skill'] or 'None'}")
    print(f"Tool Uses: {summary['tool_use_count']}")

    if summary["tool_breakdown"]:
        print("\nTool Breakdown:")
        for tool, count in summary["tool_breakdown"].items():
            print(f"  • {tool}: {count}")


def main():
    """Run all demos."""
    print("\n" + "🚀" * 30)
    print("\nVibeSOP Agent Integration Demo")
    print("This demo shows how AI Agents can use VibeSOP routing")
    print("with their internal LLM for semantic skill selection.\n")

    demo_basic_routing()
    demo_multi_turn_reroute()
    demo_session_tracking()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("  1. Agent can inject its internal LLM for AI triage")
    print("  2. Semantic routing works for multilingual queries")
    print("  3. Multi-turn conversations can detect intent shifts")
    print("  4. Session tracking provides conversation analytics")
    print("\nFor integration:")
    print("  from vibesop.agent import AgentRouter, SimpleResponse")
    print("  router = AgentRouter()")
    print("  router.set_llm(YourLLMWrapper())")
    print("  result = router.route(user_query)")


if __name__ == "__main__":
    main()
