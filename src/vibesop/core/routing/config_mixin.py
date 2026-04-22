"""Router configuration mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibesop.core.config import ConfigManager
    from vibesop.core.config import RoutingConfig as ConfigRoutingConfig


class RouterConfigMixin:
    """Mixin providing configuration management methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - project_root: Path
    """

    def _create_config_manager_from_config(
        self, config: ConfigRoutingConfig
    ) -> ConfigManager:
        from vibesop.core.config import ConfigManager

        manager = ConfigManager(project_root=self.project_root)  # type: ignore[attr-defined]
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager
