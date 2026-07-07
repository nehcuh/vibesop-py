"""Base for typed configuration models.

Config is merged from many sources (defaults, global/project files, legacy
preferences, env vars). Unknown keys routinely appear — renamed fields
(legacy ``routing.enable_ai``), typo'd env vars, forward-compat extras.
Pydantic's default rejection of extra fields turns every harmless stray key
into a ``ValidationError`` on the routing hot path (``get_routing_config()``
runs in ``UnifiedRouter.__init__``). Models inheriting ``TolerantConfig``
ignore extras instead, so a stale preferences file or a stray ``VIBE_*`` env
var can't crash every command. Dropped extras are logged at debug so operators
can spot typos / stale legacy fields without a crash.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)


class TolerantConfig(BaseModel):
    """Base config model that ignores unknown keys (``extra='ignore'``).

    Inherit instead of ``BaseModel`` for any config model instantiated via
    ``**ConfigManager._get_section(...)``. Unknown keys are silently dropped
    (not stored) and logged at debug level for operator visibility.
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _log_ignored_extras(cls, data: Any) -> Any:
        """Debug-log unknown keys before pydantic drops them (extra='ignore')."""
        if isinstance(data, dict):
            unknown = [k for k in data if k not in cls.model_fields]
            if unknown:
                logger.debug("Config %s ignored unknown key(s): %s", cls.__name__, unknown)
        return data
