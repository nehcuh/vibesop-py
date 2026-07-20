"""Shared utilities for CLI commands."""

from __future__ import annotations

import logging
from pathlib import Path

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def get_configured_platform() -> str | None:
    """Get platform from .vibe/config.toml (preferred) or .vibe/config.yaml.

    Returns:
        Platform string if configured, None otherwise.
    """
    for ext in [".toml", ".yaml"]:
        config_path = Path(f".vibe/config{ext}")
        if not config_path.exists():
            continue
        try:
            if ext == ".toml":
                from vibesop.utils.encoding import load_toml_with_fallback

                config = load_toml_with_fallback(config_path)
            else:
                from vibesop.utils.encoding import read_text_with_fallback

                yaml_parser = YAML()
                config = yaml_parser.load(read_text_with_fallback(config_path))
            return config.get("platform") if config else None
        except Exception as e:
            logger.debug("Failed to read %s: %s", config_path.name, e)
    return None
