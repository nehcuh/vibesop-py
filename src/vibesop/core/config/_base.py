"""Base for typed configuration models.

Config is merged from many sources (defaults, global/project files, legacy
preferences, env vars). Unknown keys routinely appear — renamed fields
(legacy ``routing.enable_ai``), typo'd env vars, forward-compat extras.
Pydantic's default rejection of extra fields turns every harmless stray key
into a ``ValidationError`` on the routing hot path (``get_routing_config()``
runs in ``UnifiedRouter.__init__``). Models inheriting ``TolerantConfig``
ignore extras instead, so a stale preferences file or a stray ``VIBE_*`` env
var can't crash every command.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TolerantConfig(BaseModel):
    """Base config model that ignores unknown keys (``extra='ignore'``).

    Inherit instead of ``BaseModel`` for any config model instantiated via
    ``**ConfigManager._get_section(...)``.
    """

    model_config = ConfigDict(extra="ignore")
