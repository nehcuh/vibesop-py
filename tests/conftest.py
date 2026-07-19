"""Root conftest with shared fixtures for all tests."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.spec import SkillSpec


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_llm_response() -> dict[str, object]:
    return {
        "skill_id": "/review",
        "confidence": 0.95,
        "reasoning": "Query matches code review pattern",
    }


@pytest.fixture
def mock_llm_client(mock_llm_response: dict[str, object]) -> Generator[Mock, None, None]:
    with patch("vibesop.llm.anthropic.AnthropicClient") as mock_cls:
        mock_instance = Mock()
        mock_instance.query.return_value = mock_llm_response
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def sample_skill() -> SkillSpec:
    return SkillSpec(
        id="/test",
        name="Test Skill",
        description="A test skill for unit testing",
        trigger_when="test, testing, unit test",
    )


@pytest.fixture
def sample_skills(sample_skill: SkillSpec) -> list[SkillSpec]:
    return [
        sample_skill,
        SkillSpec(
            id="/review",
            name="Code Review",
            description="Review code for issues",
            trigger_when="review, audit, check",
        ),
        SkillSpec(
            id="/debug",
            name="Debug",
            description="Debug issues in code",
            trigger_when="debug, fix bug, troubleshoot",
        ),
    ]


@pytest.fixture
def mock_skill_loader(sample_skills: list[SkillSpec]) -> Generator[Mock, None, None]:
    with patch("vibesop.core.skills.loader.SkillLoader") as mock_cls:
        mock_instance = Mock()
        mock_instance.load_skills.return_value = sample_skills
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def vibe_config_dir(tmp_path: Path) -> Path:
    """Create a temporary .vibe config directory."""
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / ".vibe" / "skills"
    skills_dir.mkdir(parents=True)
    return skills_dir


def _redirect_frozen_home_paths(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Redirect import-time-frozen home paths (ClassVars / module globals) to *home*.

    These modules computed ``Path.home() / ...`` at import time, long before any
    function-scoped fixture runs, so env-var / ``Path.home`` patching alone does
    not reach them. Each redirect mirrors the module's real structure (dicts and
    lists are replaced wholesale; nested keys use ``setitem`` so sibling
    metadata survives — e.g. ``verify.PLATFORM_CONFIGS[*]["checks"]``). Modules
    that resolve home lazily at call time (e.g. ``core/routing/candidate_manager.py``)
    are covered by the ``Path.home`` patch and deliberately not listed here.
    """
    from vibesop.cli.commands import deploy, verify
    from vibesop.core import llm_config
    from vibesop.core.skills import (
        config_manager,
        external_loader,
        pack_lock,
        storage,
        trust,
    )
    from vibesop.installer import pack_installer
    from vibesop.integrations import detector
    from vibesop.security import skill_auditor

    # core/skills/storage.py — SkillStorage.CENTRAL_SKILLS_DIR / PLATFORM_SKILLS_DIRS
    monkeypatch.setattr(storage.SkillStorage, "CENTRAL_SKILLS_DIR", home / ".config" / "skills")
    monkeypatch.setattr(
        storage.SkillStorage,
        "PLATFORM_SKILLS_DIRS",
        {
            "claude-code": home / ".claude" / "skills",
            "kimi-cli": home / ".kimi-code" / "skills",
            "opencode": home / ".config" / "opencode" / "skills",
            "cursor": home / ".config" / "cursor" / "skills",
            "pi": home / ".pi" / "agent" / "skills",
        },
    )

    # installer/pack_installer.py — PackInstaller.CENTRAL_STORAGE / PLATFORM_PATHS
    monkeypatch.setattr(
        pack_installer.PackInstaller, "CENTRAL_STORAGE", home / ".config" / "skills"
    )
    monkeypatch.setattr(
        pack_installer.PackInstaller,
        "PLATFORM_PATHS",
        [
            home / ".claude" / "skills",
            home / ".config" / "opencode" / "skills",
            home / ".kimi" / "skills",
            home / ".config" / "cursor" / "skills",
        ],
    )

    # core/skills/pack_lock.py — PackLockStore.LOCKS_DIR
    monkeypatch.setattr(
        pack_lock.PackLockStore,
        "LOCKS_DIR",
        home / ".config" / "skills" / ".pack-locks",
    )

    # core/skills/trust.py — TrustStore.PATH
    monkeypatch.setattr(trust.TrustStore, "PATH", home / ".config" / "skills" / ".trusted.json")

    # core/skills/config_manager.py — SkillConfigManager.GLOBAL_CONFIG_HOME
    monkeypatch.setattr(
        config_manager.SkillConfigManager,
        "GLOBAL_CONFIG_HOME",
        home / ".vibe" / "config.toml",
    )

    # core/llm_config.py — VibeSOPConfigManager.CONFIG_PATHS (project-relative
    # entries kept as-is; only the home-based entries are redirected)
    monkeypatch.setattr(
        llm_config.VibeSOPConfigManager,
        "CONFIG_PATHS",
        [
            Path(".vibe/config.toml"),
            Path(".vibe/config.yaml"),
            Path(".vibe/llm.toml"),
            Path(".vibe/llm.yaml"),
            home / ".vibe" / "config.toml",
            home / ".vibe" / "config.yaml",
            home / ".vibe" / "llm.toml",
            home / ".vibe" / "llm.yaml",
        ],
    )

    # core/llm_config.py — AgentEnvironmentDetector.AGENT_CONFIGS (nested dict;
    # rebuild with home-frozen entries redirected, project-relative kept)
    monkeypatch.setattr(
        llm_config.AgentEnvironmentDetector,
        "AGENT_CONFIGS",
        {
            agent_id: {
                **cfg,
                "config_files": [
                    f if not f.is_absolute() else home / f.relative_to(f.anchor)
                    for f in cfg["config_files"]
                ],
            }
            for agent_id, cfg in llm_config.AgentEnvironmentDetector.AGENT_CONFIGS.items()
        },
    )

    # cli/commands/deploy.py — module-level PLATFORM_DIRS
    monkeypatch.setattr(
        deploy,
        "PLATFORM_DIRS",
        {
            "claude-code": home / ".claude",
            "kimi-cli": home / ".kimi",
            "opencode": home / ".config" / "opencode",
            "superpowers": home / ".superpowers",
            "cursor": home / ".cursor",
        },
    )

    # cli/commands/verify.py — module-level PLATFORM_CONFIGS; only the
    # home-frozen "config_dir" of each platform is redirected (the nested
    # "checks" metadata is platform semantics, not a path). "pi" uses the
    # project-relative Path(".pi") and stays untouched.
    for platform, config_dir in {
        "claude-code": home / ".claude",
        "kimi-cli": home / ".kimi-code",
        "opencode": home / ".config" / "opencode",
        "cursor": home / ".config" / "cursor",
    }.items():
        monkeypatch.setitem(verify.PLATFORM_CONFIGS[platform], "config_dir", config_dir)

    # core/skills/external_loader.py — ExternalSkillLoader.EXTERNAL_PATHS
    monkeypatch.setattr(
        external_loader.ExternalSkillLoader,
        "EXTERNAL_PATHS",
        [
            home / ".claude" / "skills",
            home / ".config" / "skills",
            home / ".vibe" / "skills",
        ],
    )

    # security/skill_auditor.py — SkillSecurityAuditor.ALLOWED_BASE_PATHS
    monkeypatch.setattr(
        skill_auditor.SkillSecurityAuditor,
        "ALLOWED_BASE_PATHS",
        [
            home / ".claude" / "skills",
            home / ".config" / "skills",
            home / ".vibe" / "skills",
        ],
    )

    # integrations/detector.py — IntegrationDetector.SKILLS_BASE_PATHS
    monkeypatch.setattr(
        detector.IntegrationDetector,
        "SKILLS_BASE_PATHS",
        [
            home / ".config" / "skills",
            home / ".claude" / "skills",
            home / ".config" / "claude" / "skills",
        ],
    )


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from the real user home directory (M4, three layers).

    1. Env vars: ``HOME``/``USERPROFILE`` → tmp; ``HOMEDRIVE``/``HOMEPATH``
       removed (ntpath.expanduser precedence: HOME > USERPROFILE > HOMEDRIVE/PATH).
    2. ``Path.home()`` patched to tmp for call-time consumers.
    3. Import-time-frozen ClassVar/module-level paths redirected to tmp
       (see ``_redirect_frozen_home_paths``).

    Tests may still override any of these with their own monkeypatch calls —
    those run after this fixture and win. Real-user-dir writes during the
    suite (e.g. ``~/.claude/skills/`` from test_skill_storage.py) are thereby
    eliminated.
    """
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    _redirect_frozen_home_paths(monkeypatch, home)


@pytest.fixture(scope="session")
def symlink_supported(tmp_path_factory: pytest.TempPathFactory) -> bool:
    """Probe once per session whether directory symlinks can be created.

    Windows without Developer Mode / SeCreateSymbolicLinkPrivilege cannot;
    symlink-dependent tests should guard with::

        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
    """
    from vibesop.utils.symlinks import can_create_dir_symlink

    probe_dir = tmp_path_factory.mktemp("symlink-probe")
    return can_create_dir_symlink(probe_dir)
