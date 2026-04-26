"""User confirmation flow for routing decisions."""

from __future__ import annotations

import sys
from typing import Any

import questionary
from rich.console import Console

from vibesop.cli.routing_report import render_routing_report
from vibesop.core.models import RoutingResult


def _needs_confirmation(
    result: Any,
    router: Any,
    yes: bool = False,
    json_output: bool = False,
    validate: bool = False,
    is_orchestrated: bool = False,
) -> bool:
    """Determine if user confirmation is needed for a routing result."""
    if yes or json_output or validate:
        return False
    confirmation_mode = router._config.confirmation_mode
    if confirmation_mode == "never" or not sys.stdin.isatty():
        return False
    if is_orchestrated:
        if confirmation_mode == "ambiguous_only" and result.execution_plan:
            all_confident = all(
                getattr(step, "confidence", 0) >= router._config.auto_select_threshold
                for step in result.execution_plan.steps
            )
            return not all_confident
        return True
    return not (
        confirmation_mode == "ambiguous_only"
        and result.primary
        and result.primary.confidence >= router._config.auto_select_threshold
    )


def _run_confirmation_flow(result: Any, console: Console) -> None:
    """Interactive confirmation: confirm / alternative / skip."""
    routing_result = RoutingResult(
        primary=result.primary,
        alternatives=result.alternatives,
        routing_path=result.routing_path,
        layer_details=result.layer_details,
        query=result.original_query,
        duration_ms=result.duration_ms,
    )
    render_routing_report(routing_result, console=console)

    choices = [
        questionary.Choice("✅ Confirm selected skill", value="confirm"),
        questionary.Choice("🔀 Choose a different skill", value="alternative"),
        questionary.Choice("📝 Skip skill, use raw LLM", value="skip"),
    ]
    choice = questionary.select("How would you like to proceed?", choices=choices).ask()

    if choice == "alternative" and result.alternatives:
        _choose_alternative(result, console)
    elif choice == "skip":
        result.primary = None


def _choose_alternative(result: Any, console: Console) -> None:
    """Let user choose from alternative skills."""
    alt_choices = [
        questionary.Choice(
            f"{alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})"
            f"{(' — ' + alt.description[:40]) if alt.description else ''}",
            value=alt.skill_id,
        )
        for alt in result.alternatives[:5]
    ]
    alt_choices.append(questionary.Choice("↩️  Back", value="back"))
    alt_id = questionary.select("Select a skill:", choices=alt_choices).ask()

    if alt_id and alt_id != "back":
        for alt in result.alternatives:
            if alt.skill_id == alt_id:
                result.primary = alt
                break
