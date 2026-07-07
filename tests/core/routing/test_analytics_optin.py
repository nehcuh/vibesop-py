"""F-06: analytics persistence is opt-in (default off) and env-override parses bools.

The gate lives in ``UnifiedRouter._record_execution``; these tests assert the
default-off behavior and that falsy-looking ``VIBE_ANALYTICS_ENABLED`` values do
NOT accidentally enable analytics (ConfigManager.get returns env values as raw
strings, so a naive truthiness check treats 'false' as truthy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.routing.unified import UnifiedRouter


def _analytics_file(tmp_path: Path) -> Path:
    return tmp_path / ".vibe" / "analytics.jsonl"


def test_record_execution_skipped_when_analytics_disabled(tmp_path: Path) -> None:
    """F-06: default analytics.enabled=False → _record_execution writes nothing."""
    router = UnifiedRouter(project_root=tmp_path)
    assert not _analytics_file(tmp_path).exists()
    # The gate short-circuits before ``result`` is touched, so None is safe.
    router._record_execution("any query", result=None)  # type: ignore[arg-type]
    assert not _analytics_file(tmp_path).exists(), (
        "analytics.jsonl must not be created when disabled"
    )


@pytest.mark.parametrize("falsy", ["false", "0", "no", "off", "", "FALSE"])
def test_record_execution_env_falsy_string_stays_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, falsy: str
) -> None:
    """F-06 (Kimi #1): any falsy-looking VIBE_ANALYTICS_ENABLED value stays disabled.

    ConfigManager.get returns env values as raw strings; the gate must parse
    'false'/'0'/'no'/'off'/'' (and uppercase) as falsy, not truthy.
    """
    monkeypatch.setenv("VIBE_ANALYTICS_ENABLED", falsy)
    router = UnifiedRouter(project_root=tmp_path)
    router._record_execution("any query", result=None)  # type: ignore[arg-type]
    assert not _analytics_file(tmp_path).exists()
