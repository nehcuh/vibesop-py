"""Project-level routing configuration loader.

Loads and merges project-specific routing overrides from .vibe/skill-routing.yaml
on top of the global core/registry.yaml configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from vibesop.core.routing.scenario_layer import (
    load_scenario_config as load_registry_scenario_config,
)

yaml = YAML()
yaml.preserve_quotes = True

logger = logging.getLogger(__name__)

# Default project-level routing configuration
DEFAULT_PROJECT_ROUTING = """# Project-Level Skill Routing Configuration
# This file allows you to customize routing behavior for this specific project.
# Changes here override the global core/policies/task-routing.yaml settings.

schema_version: 1

# Override scenario patterns for this project
# These take precedence over global configuration
scenario_overrides:
  # Example: Override the debugging scenario for this project
  # - id: error_detected
  #   skill_id: "my-custom/debugger"
  #   message: "Use project-specific debugger"

# Add project-specific scenario patterns
scenario_patterns:
  # Example: Add a new scenario for this project
  # - id: deploy_staging
  #   name: "Deploy to Staging"
  #   trigger_mode: suggest
  #   description: "User wants to deploy to staging environment"
  #   keywords:
  #     - "deploy staging"
  #     - "staging deploy"
  #     - "发布到测试"
  #   skill_id: "project/deploy-staging"
  #   priority: P1
  #   message: "建议使用项目部署流程"

# Project-specific routing hints
routing_hints:
  # Example: Add routing hints for this project
  # - keywords: ["数据库", "database", "schema"]
  #   suggest: "project/db-migration"
  #   message: "数据库变更建议使用 db-migration 技能"

# Disable specific global scenarios for this project
disabled_scenarios:
  # Example: Disable a global scenario
  # - "consecutive_failures"

# Conflict resolution overrides
conflict_resolution:
  # Example: Override conflict resolution for this project
  # strategies:
  #   - scenario: debugging
  #     primary: my-custom/debugger
  #     primary_source: project
  #     reason: "Use project-specific debugger"

# Override or extend scenario keywords
scenario_keywords:
  # Example: Add project-specific keywords to an existing scenario
  # debugging:
  #   - "crashed"
  #   - " segfault"

# Override keywords
override_keywords:
  # Example: Add project-specific override keywords
  # "用项目": project
  # "use project": project
"""


def load_project_routing(project_root: str | Path = ".") -> dict[str, Any]:
    """Load project-level routing configuration.

    Args:
        project_root: Path to project root directory

    Returns:
        Dictionary with project routing configuration
    """
    config_path = Path(project_root) / ".vibe" / "skill-routing.yaml"

    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = cast("Any", yaml.load(f))  # type: ignore[reportUnknownMemberType]

        return cast("dict[str, Any]", data) if isinstance(data, dict) else {}

    except (OSError, Exception) as e:
        logger.debug(f"Failed to load project routing config from {config_path}: {e}")
        return {}


def merge_scenarios(
    global_scenarios: list[dict[str, Any]],
    project_routing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge global scenarios with project-specific overrides.

    Args:
        global_scenarios: Scenarios from core/registry.yaml
        project_routing: Project-specific routing configuration

    Returns:
        Merged list of scenarios
    """
    if not project_routing:
        return global_scenarios

    # Start with a copy of global scenarios
    merged = list(global_scenarios)

    # Get disabled scenarios
    disabled = set(project_routing.get("disabled_scenarios", []))

    # Filter out disabled scenarios
    merged = [s for s in merged if s.get("name") not in disabled and s.get("id") not in disabled]

    # Apply scenario overrides
    overrides = project_routing.get("scenario_overrides", [])
    for override in overrides:
        if not isinstance(override, dict):
            continue

        override = cast("dict[str, Any]", override)
        scenario_id = override.get("id")
        if not scenario_id:
            continue

        # Find and update the scenario
        for i, scenario in enumerate(merged):
            if scenario.get("id") == scenario_id or scenario.get("name") == scenario_id:
                # Update the scenario with override values
                merged[i] = {**scenario, **override}
                break
        else:
            # If not found, add as new scenario (though this is unusual)
            merged.append(override)

    # Add project-specific scenarios
    project_scenarios = project_routing.get("scenario_patterns", [])
    for scenario in project_scenarios:
        if isinstance(scenario, dict) and "id" in scenario:
            merged.append(cast("dict[str, Any]", scenario))

    return merged


def merge_scenario_keywords(
    global_keywords: dict[str, list[str]],
    project_routing: dict[str, Any],
) -> dict[str, list[str]]:
    """Merge global scenario keywords with project-specific overrides.

    Project-level keywords are merged (union) with global keywords.

    Args:
        global_keywords: Keywords from core/registry.yaml
        project_routing: Project-specific routing configuration

    Returns:
        Merged keyword mapping
    """
    merged = dict(global_keywords)

    project_keywords = project_routing.get("scenario_keywords", {})
    if not isinstance(project_keywords, dict):
        return merged

    for scenario_name, extra_keywords in project_keywords.items():
        if not isinstance(extra_keywords, list):
            continue
        existing = set(merged.get(scenario_name, []))
        existing.update(str(kw) for kw in extra_keywords)
        merged[scenario_name] = list(existing)

    return merged


def get_project_routing_hints(project_root: str | Path = ".") -> list[dict[str, Any]]:
    """Get routing hints from project configuration.

    Args:
        project_root: Path to project root directory

    Returns:
        List of routing hints from project config
    """
    project_routing = load_project_routing(project_root)
    return project_routing.get("routing_hints", [])


def create_default_project_routing(project_root: str | Path = ".") -> Path | None:
    """Create default project-level routing configuration file.

    Args:
        project_root: Path to project root directory

    Returns:
        Path to created file, or None if file already exists
    """
    config_path = Path(project_root) / ".vibe" / "skill-routing.yaml"

    if config_path.exists():
        return None

    # Ensure .vibe directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(DEFAULT_PROJECT_ROUTING, encoding="utf-8")
    return config_path


def load_merged_scenario_config(project_root: str | Path = ".") -> dict[str, Any]:
    """Load scenarios and keywords with project-level overrides applied.

    This is the main entry point for getting scenario configuration with overrides.

    Args:
        project_root: Path to project root directory

    Returns:
        Dictionary with "strategies" and "keywords" keys.
    """
    # Load global config from core/registry.yaml
    global_config = load_registry_scenario_config(Path(project_root) / "core" / "registry.yaml")

    # Load project routing
    project_routing = load_project_routing(project_root)

    # Merge configurations
    merged_scenarios = merge_scenarios(global_config.get("strategies", []), project_routing)
    merged_keywords = merge_scenario_keywords(global_config.get("keywords", {}), project_routing)

    return {"strategies": merged_scenarios, "keywords": merged_keywords}


def load_merged_scenarios(project_root: str | Path = ".") -> list[dict[str, Any]]:
    """Load scenarios with project-level overrides applied.

    Backward-compatible wrapper that returns only the strategies list.

    Args:
        project_root: Path to project root directory

    Returns:
        List of scenarios with project overrides applied
    """
    return load_merged_scenario_config(project_root).get("strategies", [])
