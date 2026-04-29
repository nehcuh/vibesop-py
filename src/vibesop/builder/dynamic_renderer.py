"""Configuration-driven rendering system.

This module provides dynamic configuration generation
based on configuration files and templates.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


@dataclass
class RenderRule:
    """Rendering rule configuration.

    Attributes:
        name: Rule name
        condition: Condition to apply this rule
        template: Template file to use
        output_path: Output file path
        context_vars: Variables for template rendering
        enabled: Whether rule is enabled
    """

    name: str
    condition: str
    template: str
    output_path: str
    context_vars: dict[str, Any]
    enabled: bool = True


class ConfigDrivenRenderer:
    """Configuration-driven renderer.

    Generates configuration files dynamically based on
    rendering rules and conditions.

    Example:
        >>> renderer = ConfigDrivenRenderer()
        >>> result = renderer.render_with_rules(
        ...     manifest,
        ...     rules_config="rules.yaml"
        ... )
    """

    def __init__(self) -> None:
        """Initialize the config-driven renderer."""
        self._env: Environment | None = None
        self._rules: list[RenderRule] = []

    def load_rules(
        self,
        rules_config: Path,
    ) -> list[RenderRule]:
        """Load rendering rules from configuration.

        Args:
            rules_config: Path to rules configuration file

        Returns:
            List of RenderRule instances
        """
        if not rules_config.exists():
            return []

        try:
            yaml_parser = YAML()
            with rules_config.open() as f:
                config: dict[str, Any] = yaml_parser.load(f)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]

            rules: list[RenderRule] = []
            rules_list = config.get("rules", [])  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            for rule_data in rules_list:  # pyright: ignore[reportUnknownVariableType]
                rd = cast("dict[str, Any]", rule_data)
                rule = RenderRule(
                    name=str(rd.get("name", "")),
                    condition=str(rd.get("condition", "")),
                    template=str(rd.get("template", "")),
                    output_path=str(rd.get("output_path", "")),
                    context_vars=rd.get("context", {}),
                    enabled=bool(rd.get("enabled", True)),
                )
                rules.append(rule)

            return rules

        except Exception as e:
            logger.warning("Failed to load rules from %s: %s", rules_config, e)
            return []

    def render_with_rules(
        self,
        manifest: Any,
        output_dir: Path,
        rules_config: Path | None = None,
    ) -> dict[str, Any]:
        """Render configuration with rules.

        Args:
            manifest: Configuration manifest
            output_dir: Output directory
            rules_config: Path to rules configuration

        Returns:
            RenderResult with files created
        """
        result: dict[str, Any] = {
            "success": False,
            "files_created": [],
            "errors": [],
            "rules_applied": [],
        }

        try:
            # Load rules
            if rules_config and rules_config.exists():
                self._rules = self.load_rules(rules_config)
            else:
                # Use default rules
                self._rules = self._get_default_rules(manifest)

            # Apply each rule
            for rule in self._rules:
                if not rule.enabled:
                    continue

                # Check condition
                if not self._evaluate_condition(rule.condition, manifest):
                    continue

                # Render template
                content = self._render_template(
                    rule.template, {**rule.context_vars, "manifest": manifest}
                )

                # Write to file
                output_path = output_dir / rule.output_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding="utf-8")

                result["files_created"].append(str(output_path))
                result["rules_applied"].append(rule.name)

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Rendering failed: {e}")

        return result

    def _get_default_rules(self, manifest: Any) -> list[RenderRule]:
        """Get default rendering rules.

        Args:
            manifest: Configuration manifest

        Returns:
            List of default RenderRule instances
        """
        platform = manifest.metadata.platform

        if platform == "claude-code":
            return [
                RenderRule(
                    name="claude-md",
                    condition="platform == 'claude-code'",
                    template="adapters/templates/claude-code/CLAUDE.md.j2",
                    output_path="CLAUDE.md",
                    context_vars={},
                ),
                RenderRule(
                    name="settings-json",
                    condition="platform == 'claude-code'",
                    template="adapters/templates/claude-code/settings.json.j2",
                    output_path="settings.json",
                    context_vars={},
                ),
            ]
        elif platform == "opencode":
            return [
                RenderRule(
                    name="config-yaml",
                    condition="platform == 'opencode'",
                    template="adapters/templates/opencode/config.yaml.j2",
                    output_path="config.yaml",
                    context_vars={},
                ),
            ]
        else:
            return []

    _SAFE_VARIABLES: ClassVar[set[str]] = {"platform", "version"}

    def _evaluate_condition(self, condition: str, manifest: Any) -> bool:
        """Evaluate a rule condition safely.

        Supports only simple equality comparisons:
            variable == 'value'

        Args:
            condition: Condition string
            manifest: Configuration manifest

        Returns:
            True if condition evaluates to True
        """
        if not condition or not condition.strip():
            return True

        condition = condition.strip()

        try:
            context: dict[str, Any] = {
                "platform": manifest.metadata.platform,
                "version": manifest.metadata.version,
            }

            return self._parse_simple_equality(condition, context)
        except Exception as e:
            logger.debug(f"Failed to evaluate condition '{condition}': {e}")
            return False

    @staticmethod
    def _parse_simple_equality(condition: str, context: dict[str, Any]) -> bool:
        """Parse a simple equality condition: variable == 'value'.

        Args:
            condition: Condition string like "platform == 'claude-code'"
            context: Available variables

        Returns:
            Boolean result
        """
        if "==" not in condition:
            return False

        left, right = condition.split("==", 1)
        left = left.strip()
        right = right.strip()

        if left not in context:
            return False

        if (not right.startswith("'") or not right.endswith("'")) and (
            not right.startswith('"') or not right.endswith('"')
        ):
            return False

        expected_value = right[1:-1]
        actual_value = str(context[left])

        return actual_value == expected_value

    def _render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template.

        Args:
            template_name: Template file name
            context: Template context variables

        Returns:
            Rendered content
        """
        if self._env is None:
            # Setup Jinja2 environment
            templates_dir = Path("src/vibesop/adapters/templates")
            self._env = Environment(
                loader=FileSystemLoader(templates_dir),
                autoescape=False,
            )

        try:
            template = self._env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            raise Exception(f"Template rendering failed: {e}") from e

    def render_dynamic_config(
        self,
        manifest: Any,
        config_spec: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        """Render dynamic configuration based on spec.

        Args:
            manifest: Configuration manifest
            config_spec: Configuration specification
            output_dir: Output directory

        Returns:
            RenderResult
        """
        result: dict[str, Any] = {
            "success": False,
            "files_created": [],
            "errors": [],
        }

        try:
            for file_spec in config_spec.get("files", []):
                # Check if file should be generated
                if not self._should_generate_file(file_spec, manifest):
                    continue

                # Render content
                content = self._render_file_content(file_spec, manifest)

                # Write file
                output_path = output_dir / file_spec["path"]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding="utf-8")

                result["files_created"].append(str(output_path))

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Dynamic rendering failed: {e}")

        return result

    def _should_generate_file(self, file_spec: dict[str, Any], manifest: Any) -> bool:
        """Check if file should be generated.

        Args:
            file_spec: File specification
            manifest: Configuration manifest

        Returns:
            True if file should be generated
        """
        # Check conditions
        conditions: dict[str, Any] = file_spec.get("conditions", {})
        if conditions:
            platform = conditions.get("platform")
            if platform and platform != manifest.metadata.platform:
                return False

        # Check if file is enabled
        return file_spec.get("enabled", True)

    def _render_file_content(self, file_spec: dict[str, Any], manifest: Any) -> str:
        """Render file content.

        Args:
            file_spec: File specification
            manifest: Configuration manifest

        Returns:
            Rendered content
        """
        template = file_spec.get("template")
        if template:
            # Use template
            return self._render_template(template, {"manifest": manifest})
        else:
            # Use static content
            return file_spec.get("content", "")
