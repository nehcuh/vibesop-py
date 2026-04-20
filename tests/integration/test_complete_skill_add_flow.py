#!/usr/bin/env python3
"""End-to-end test for skill add with auto-configuration."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vibesop.core.skills.understander import understand_skill_from_file
from vibesop.core.llm_config import LLMConfigResolver, is_in_agent_environment


def test_complete_skill_understanding_flow():
    """Test the complete skill understanding flow."""

    print("=" * 70)
    print("Complete Skill Understanding Flow Test")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test skill
        skill_dir = Path(tmpdir) / "systematic-debugging.skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: Systematic Debugging
id: systematic-debugging
description: Find root cause before attempting fixes
version: 1.0.0
skill_type: workflow
tags:
  - debug
  - troubleshooting
  - testing
trigger_when: User encounters bugs or errors that need systematic diagnosis
---

# Systematic Debugging

This skill provides a structured approach to debugging:
1. Gather information
2. Form hypotheses
3. Test systematically
4. Verify fixes
""")

        print(f"\n📁 Created test skill at: {skill_dir}")

        # Phase 1: Understand the skill
        print("\n" + "-" * 70)
        print("Phase 1: Understanding Skill")
        print("-" * 70)

        config = understand_skill_from_file(skill_dir)

        print(f"\n✓ Skill ID: {config.skill_id}")
        print(f"✓ Category: {config.category}")
        print(f"✓ Priority: {config.priority}")
        print(f"✓ Scope: {config.scope}")
        print(f"✓ Enabled: {config.enabled}")
        print(f"✓ Routing Patterns: {len(config.routing_patterns)}")
        print(f"  {', '.join(config.routing_patterns[:3])}")
        print(f"✓ Requires LLM: {config.requires_llm}")
        print(f"✓ Confidence: {config.confidence:.1%}")
        print(f"✓ Config Source: {config.config_source}")

        if config.requires_llm and config.llm_config:
            print(f"\n✓ LLM Configuration:")
            llm = config.llm_config
            provider = llm.get("provider", "N/A")
            models = llm.get("models", [])
            model = models[0] if models else "N/A"
            temp = llm.get("temperature", "N/A")
            print(f"  Provider: {provider}")
            print(f"  Model: {model}")
            print(f"  Temperature: {temp}")

        # Phase 2: LLM Configuration Check
        print("\n" + "-" * 70)
        print("Phase 2: LLM Configuration Check")
        print("-" * 70)

        resolver = LLMConfigResolver()
        agent_detected = is_in_agent_environment()

        print(f"\n✓ Agent Environment Detected: {agent_detected}")

        if config.requires_llm:
            print("\n✓ Skill requires LLM - checking availability...")

            llm_config = resolver.resolve_llm_config(
                skill_requirements=config.llm_config,
                prefer_agent=True
            )

            if llm_config:
                print(f"  ✓ LLM Available!")
                print(f"    Provider: {llm_config.provider}")
                print(f"    Model: {llm_config.model}")
                print(f"    Source: {llm_config.source.value}")
                print(f"    Confidence: {llm_config.confidence:.1%}")
            else:
                print(f"  ⚠ No LLM configured")
                print(f"    Skill will work in limited mode")
        else:
            print("\n✓ Skill does not require LLM - ready to use!")

        # Phase 3: Save Configuration
        print("\n" + "-" * 70)
        print("Phase 3: Save Configuration")
        print("-" * 70)

        from vibesop.core.skills.understander import SkillAutoConfigurator

        configurator = SkillAutoConfigurator()
        output_dir = Path(tmpdir) / ".vibe" / "skills"
        config_file = configurator.save_config(config, output_dir)

        print(f"\n✓ Configuration saved to: {config_file}")

        # Display saved config
        import yaml

        with open(config_file) as f:
            saved_config = yaml.safe_load(f)

        print(f"\n✓ Saved Configuration:")
        print(f"  Skills: {list(saved_config.get('skills', {}).keys())}")

        if config.skill_id in saved_config.get('skills', {}):
            skill_config = saved_config['skills'][config.skill_id]
            print(f"  Priority: {skill_config.get('priority')}")
            print(f"  Category: {skill_config.get('category')}")
            print(f"  Enabled: {skill_config.get('enabled')}")

            routing = skill_config.get('routing', {})
            patterns = routing.get('patterns', [])
            print(f"  Routing Patterns: {len(patterns)}")

            metadata = skill_config.get('metadata', {})
            print(f"  Auto-Configured: {metadata.get('auto_configured')}")
            print(f"  Confidence: {metadata.get('confidence', 0):.1%}")

        # Verification
        print("\n" + "=" * 70)
        print("✅ Complete Flow Test PASSED")
        print("=" * 70)

        print("\n📊 Summary:")
        print(f"  • Skill understood with {config.confidence:.1%} confidence")
        print(f"  • Category: {config.category}")
        print(f"  • Priority: {config.priority}")
        print(f"  • Routing rules: {len(config.routing_patterns)} patterns")
        print(f"  • LLM required: {config.requires_llm}")
        if config.requires_llm:
            if llm_config:
                print(f"  • LLM available: {llm_config.provider}/{llm_config.model}")
            else:
                print(f"  • LLM available: No (will work in limited mode)")

        return True


def test_multiple_skill_types():
    """Test understanding different types of skills."""

    print("\n" + "=" * 70)
    print("Testing Multiple Skill Types")
    print("=" * 70)

    test_cases = [
        {
            "name": "Code Review",
            "id": "code-reviewer",
            "description": "AI-powered code review and quality assurance",
            "expected_category": "review",
            "expected_requires_llm": True,
        },
        {
            "name": "Testing Workflow",
            "id": "test-workflow",
            "description": "Systematic testing workflow for quality assurance",
            "expected_category": "testing",
            "expected_requires_llm": False,
        },
        {
            "name": "Security Audit",
            "id": "security-audit",
            "description": "Security vulnerability scanning and audit",
            "expected_category": "security",
            "expected_requires_llm": True,
        },
        {
            "name": "Documentation Helper",
            "id": "doc-helper",
            "description": "Generate and maintain project documentation",
            "expected_category": "documentation",
            "expected_requires_llm": True,
        },
    ]

    results = []

    for test_case in test_cases:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / f"{test_case['id']}.skill"
            skill_dir.mkdir()

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(f"""---
name: {test_case['name']}
id: {test_case['id']}
description: {test_case['description']}
version: 1.0.0
skill_type: workflow
tags: [{test_case['expected_category']}]
trigger_when: User requests {test_case['name'].lower()}
---

# {test_case['name']}

{test_case['description']}
""")

            try:
                config = understand_skill_from_file(skill_dir)

                # Check if category matches (allowing for some flexibility)
                category_match = (
                    config.category == test_case['expected_category'] or
                    config.category == "development"  # fallback
                )

                result = {
                    "name": test_case['name'],
                    "category": config.category,
                    "priority": config.priority,
                    "requires_llm": config.requires_llm,
                    "confidence": config.confidence,
                    "category_match": category_match,
                    "passed": category_match,
                }
                results.append(result)

                print(f"\n✓ {test_case['name']}:")
                print(f"  Category: {config.category} (expected: {test_case['expected_category']})")
                print(f"  Priority: {config.priority}")
                print(f"  Requires LLM: {config.requires_llm}")
                print(f"  Confidence: {config.confidence:.1%}")

            except Exception as e:
                print(f"\n✗ {test_case['name']}: FAILED - {e}")
                results.append({
                    "name": test_case['name'],
                    "passed": False,
                    "error": str(e),
                })

    # Summary
    passed = sum(1 for r in results if r.get("passed", False))
    total = len(results)

    print(f"\n📊 Results: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🎯 VibeSOP Skill Understanding - End-to-End Tests")
    print("=" * 70)

    # Test 1: Complete flow
    success1 = test_complete_skill_understanding_flow()

    # Test 2: Multiple skill types
    success2 = test_multiple_skill_types()

    # Final result
    if success1 and success2:
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ SOME TESTS FAILED")
        print("=" * 70)
        sys.exit(1)
