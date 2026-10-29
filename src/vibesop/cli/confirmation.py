"""User confirmation flow for routing decisions."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import questionary

if TYPE_CHECKING:
    from rich.console import Console

from vibesop.cli.render import single_skill_availability
from vibesop.cli.routing_report import render_routing_report
from vibesop.core.models import RoutingResult

logger = logging.getLogger(__name__)


def _safe_questionary_select(
    message: str,
    choices: list[questionary.Choice],
    default: str = "confirm",
) -> str | None:
    """Call ``questionary.select``, falling back to *default* on console errors.

    On Windows, ``prompt_toolkit`` requires a real console screen buffer
    (``Win32Output``).  Environments like Grok Build or CI runners may
    provide a PTY (so ``sys.stdin.isatty()`` returns ``True``) but lack
    an actual Windows console — ``questionary`` raises
    ``NoConsoleScreenBufferError`` in that case.  This wrapper catches
    the error, logs a warning, and returns *default* so the caller can
    proceed without blocking.
    """
    try:
        return questionary.select(message, choices=choices).ask()
    except Exception:
        # prompt_toolkit raises ``NoConsoleScreenBufferError`` (a plain
        # ``Exception`` subclass from its win32 module).  We catch broadly
        # because the exact exception class is an implementation detail of
        # prompt_toolkit and may change across versions.
        logger.warning("Interactive prompt unavailable (no console); auto-selecting %r.", default)
        return default


def _safe_questionary_confirm(  # pyright: ignore[reportUnusedFunction]  # used by cli.main
    message: str,
    default: bool = True,
) -> bool:
    """Call ``questionary.confirm``, falling back to *default* on console errors.

    See :func:`_safe_questionary_select` for the rationale.
    """
    try:
        return questionary.confirm(message, default=default).ask()
    except Exception:
        logger.warning(
            "Interactive prompt unavailable (no console); auto-answering %s.",
            "yes" if default else "no",
        )
        return default


def _safe_questionary_text(  # pyright: ignore[reportUnusedFunction]  # used by cli.main
    message: str,
    default: str = "",
) -> str:
    """Call ``questionary.text``, falling back to *default* on console errors.

    See :func:`_safe_questionary_select` for the rationale.
    """
    try:
        return questionary.text(message, default=default).ask()
    except Exception:
        logger.warning("Interactive prompt unavailable (no console); using default %r.", default)
        return default


def _needs_confirmation(  # pyright: ignore[reportUnusedFunction]
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


def _run_confirmation_flow(  # pyright: ignore[reportUnusedFunction]
    result: Any,
    console: Console,
    already_rendered: bool = False,
    source_lookup: Any = None,
    availability: dict[str, Any] | None = None,
) -> None:
    """Interactive confirmation: confirm / alternative / skip."""
    availability = single_skill_availability(
        result,
        source_lookup=source_lookup,
        expected_binding=availability.get("_source_binding") if availability is not None else None,
    )
    if availability.get("demoted_skill_id"):
        result.primary = None
        console.print("[yellow]Selected skill changed or is unavailable — route again.[/yellow]")
    if availability.get("has_match") is not True:
        return
    if not already_rendered:
        routing_result = RoutingResult(
            primary=result.primary,
            alternatives=result.alternatives,
            routing_path=result.routing_path,
            layer_details=result.layer_details,
            query=result.original_query,
            duration_ms=result.duration_ms,
        )
        render_routing_report(
            routing_result, console=console, source_lookup=source_lookup, availability=availability
        )

    choices = [
        questionary.Choice("✅ Confirm selected skill", value="confirm"),
        questionary.Choice("🔀 Choose a different skill", value="alternative"),
        questionary.Choice("📝 Skip skill, use raw LLM", value="skip"),
    ]
    choice = _safe_questionary_select(
        "How would you like to proceed?", choices=choices, default="confirm"
    )

    if choice == "alternative" and result.alternatives:
        _choose_alternative(result)
    elif choice == "skip":
        result.primary = None

    if result.primary is not None:
        # Confirm/back retain only the exact file/body the user was shown.
        # An explicitly chosen different alternative gets its own full scan.
        shown = availability["_source_binding"]
        chose_different = choice == "alternative" and result.primary.skill_id != shown["skill_id"]
        expected = None if chose_different else shown
        selected = single_skill_availability(
            result, source_lookup=source_lookup, expected_binding=expected
        )
        if selected.get("has_match") is not True:
            result.primary = None
            console.print(
                "[yellow]Selected skill changed or is unavailable — do not read or execute it.[/yellow]"
            )


def _choose_alternative(result: Any) -> None:
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
    alt_id = _safe_questionary_select("Select a skill:", choices=alt_choices, default="back")

    if alt_id and alt_id != "back":
        for alt in result.alternatives:
            if alt.skill_id == alt_id:
                result.primary = alt
                break
