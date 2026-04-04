# VibeSOP-Py Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical bugs, eliminate code duplication, correct false documentation claims, and establish a solid foundation for future development.

**Architecture:** Four-phase approach: Phase 1 fixes bugs that cause crashes or security issues; Phase 2 deduplicates installer code; Phase 3 cleans up documentation; Phase 4 fixes the semantic test suite. Each phase is independently verifiable.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest

---

## Phase 1: Critical Bug Fixes

### Task 1: Fix missing imports in installer/base.py

**Files:**
- Modify: `src/vibesop/installer/base.py:1-9`
- Test: `tests/test_transactional_installer.py`

- [ ] **Step 1: Add missing imports**

```python
# src/vibesop/installer/base.py — replace the import block (lines 1-9)
"""Base class for installers.

This module provides the BaseInstaller class that all
installers should inherit from.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
```

- [ ] **Step 2: Verify no other import errors**

Run: `uv run python -c "from vibesop.installer.base import BaseInstaller; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/installer/base.py
git commit -m "fix: add missing shutil/subprocess imports in BaseInstaller"
```

---

### Task 2: Replace eval() with safe condition parser

**Files:**
- Modify: `src/vibesop/builder/dynamic_renderer.py:194-218`
- Modify: `tests/test_dynamic_renderer.py`

The `_evaluate_condition` method uses `eval()` which is a security vulnerability. Replace with a safe parser that only supports simple equality comparisons.

- [ ] **Step 1: Write test for safe condition evaluation**

Add to `tests/test_dynamic_renderer.py`:

```python
class TestSafeConditionEvaluation:
    def test_equality_condition(self):
        from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer
        from unittest.mock import MagicMock

        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "2.1.0"

        assert renderer._evaluate_condition("platform == 'claude-code'", manifest) is True
        assert renderer._evaluate_condition("platform == 'opencode'", manifest) is False

    def test_empty_condition_returns_true(self):
        from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer
        from unittest.mock import MagicMock

        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()

        assert renderer._evaluate_condition("", manifest) is True
        assert renderer._evaluate_condition("   ", manifest) is True

    def test_invalid_condition_returns_false(self):
        from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer
        from unittest.mock import MagicMock

        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "2.1.0"

        assert renderer._evaluate_condition("import os", manifest) is False
        assert renderer._evaluate_condition("__import__('os').system('ls')", manifest) is False

    def test_version_condition(self):
        from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer
        from unittest.mock import MagicMock

        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "2.1.0"

        assert renderer._evaluate_condition("version == '2.1.0'", manifest) is True
        assert renderer._evaluate_condition("version == '1.0.0'", manifest) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_dynamic_renderer.py::TestSafeConditionEvaluation -v --no-header`
Expected: All tests should pass with current eval() implementation (baseline). Then we'll verify security.

- [ ] **Step 3: Replace eval() with safe parser**

Replace the `_evaluate_condition` method in `src/vibesop/builder/dynamic_renderer.py` (lines 194-218):

```python
    _SAFE_VARIABLES = {"platform", "version"}

    def _evaluate_condition(self, condition: str, manifest) -> bool:
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
            context = {
                "platform": manifest.metadata.platform,
                "version": manifest.metadata.version,
            }

            return self._parse_simple_equality(condition, context)
        except Exception:
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

        if not right.startswith("'") or not right.endswith("'"):
            if not right.startswith('"') or not right.endswith('"'):
                return False

        expected_value = right[1:-1]
        actual_value = str(context[left])

        return actual_value == expected_value
```

- [ ] **Step 4: Run all dynamic_renderer tests**

Run: `uv run python -m pytest tests/test_dynamic_renderer.py -v --no-header`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/builder/dynamic_renderer.py tests/test_dynamic_renderer.py
git commit -m "fix: replace eval() with safe equality parser in dynamic_renderer"
```

---

### Task 3: Remove MagicMock from production code (triggers/activator.py)

**Files:**
- Modify: `src/vibesop/triggers/activator.py:1-68`

- [ ] **Step 1: Replace MagicMock fallback with NullRouter**

Replace lines 1-68 of `src/vibesop/triggers/activator.py`:

```python
"""Skill activation for automatic trigger response.

This module provides automatic skill and workflow activation
based on detected user intent from keyword patterns.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from vibesop.triggers.models import TriggerPattern, PatternMatch
from vibesop.core.skills.manager import SkillManager
from vibesop.core.routing.engine import SkillRouter, RoutingRequest
from vibesop.workflow import WorkflowManager

logger = logging.getLogger(__name__)


class _NullRouter:
    """Fallback router that returns None for all requests."""

    def route(self, *args: Any, **kwargs: Any) -> None:
        return None


class SkillActivator:
    """Activate skills and workflows based on pattern matches.

    Bridges the gap between keyword detection and skill/workflow execution.
    Provides automatic activation with fallback and error handling.

    Attributes:
        skill_manager: SkillManager instance for skill execution
        router: SkillRouter for semantic skill routing
        workflow_manager: WorkflowManager for workflow execution
        project_root: Project root path
    """

    def __init__(
        self,
        project_root: Path = Path("."),
        skill_manager: Optional[SkillManager] = None,
        router: Optional[SkillRouter] = None,
        workflow_manager: Optional[WorkflowManager] = None,
    ):
        """Initialize skill activator.

        Args:
            project_root: Project root directory
            skill_manager: Optional SkillManager instance (created if None)
            router: Optional SkillRouter instance (created if None)
            workflow_manager: Optional WorkflowManager instance (created if None)
        """
        self.project_root = Path(project_root).resolve()

        self.skill_manager = skill_manager or SkillManager(self.project_root)

        try:
            self.router = router or SkillRouter(self.project_root)
        except Exception:
            logger.warning("Router initialization failed, using null router")
            self.router = _NullRouter()

        self.workflow_manager = workflow_manager or WorkflowManager(
            project_root=self.project_root
        )
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from vibesop.triggers.activator import SkillActivator; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/triggers/activator.py
git commit -m "fix: replace MagicMock fallback with NullRouter in activator"
```

---

### Task 4: Fix Pydantic v1 deprecated Config in workflow/models.py

**Files:**
- Modify: `src/vibesop/workflow/models.py:72-73`

- [ ] **Step 1: Replace `class Config` with `model_config`**

In `src/vibesop/workflow/models.py`, add import at top and replace `class Config`:

Add `ConfigDict` to the pydantic import on line 8:
```python
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
```

Replace lines 72-73 (`PipelineStage` class):
```python
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 2: Verify**

Run: `uv run python -c "from vibesop.workflow.models import PipelineStage; print('OK')"`
Expected: OK, no deprecation warning

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/workflow/models.py
git commit -m "fix: migrate PipelineStage from deprecated class Config to ConfigDict"
```

---

### Task 5: Fix Pydantic v1 deprecated Config in workflow/state.py

**Files:**
- Modify: `src/vibesop/workflow/state.py:97-101`

- [ ] **Step 1: Replace `class Config` with `model_config`**

In `src/vibesop/workflow/state.py`, update pydantic import on line 14:
```python
from pydantic import BaseModel, Field, ConfigDict
```

Replace lines 97-101 (`WorkflowState` class):
```python
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
```

- [ ] **Step 2: Verify**

Run: `uv run python -c "from vibesop.workflow.state import WorkflowState; print('OK')"`
Expected: OK, no deprecation warning

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/workflow/state.py
git commit -m "fix: migrate WorkflowState from deprecated class Config to ConfigDict"
```

---

### Task 6: Fix unreachable exception handler in utils/helpers.py

**Files:**
- Modify: `src/vibesop/utils/helpers.py:66-76`

- [ ] **Step 1: Fix the exception ordering**

Replace lines 66-76 in `src/vibesop/utils/helpers.py`:

```python
    try:
        yaml_parser = YAML()
        with open(path, "r", encoding=FileSystemSettings.DEFAULT_ENCODING) as f:
            data = yaml_parser.load(f)
            return data if isinstance(data, dict) else {}

    except (OSError, IOError) as e:
        raise OSError(f"Failed to read YAML file {path}: {e}") from e

    except Exception as e:
        raise ValueError(f"Failed to parse YAML file {path}: {e}") from e
```

Note: `(OSError, IOError)` is now first (more specific), `Exception` is last (catches YAML parsing errors).

- [ ] **Step 2: Verify**

Run: `uv run python -c "from vibesop.utils.helpers import load_yaml_safe; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/utils/helpers.py
git commit -m "fix: correct exception handler ordering in load_yaml_safe"
```

---

## Phase 2: Installer Deduplication

### Task 7: Extract shared GitBasedInstaller base class

**Files:**
- Modify: `src/vibesop/installer/base.py`
- Modify: `src/vibesop/installer/gstack_installer.py`
- Modify: `src/vibesop/installer/superpowers_installer.py`

The gstack and superpowers installers are 95%+ identical. Extract shared logic into a `GitBasedInstaller` base class.

- [ ] **Step 1: Add GitBasedInstaller to base.py**

Append to `src/vibesop/installer/base.py` (after the `BaseInstaller` class):

```python
import time


class GitBasedInstaller(BaseInstaller):
    """Base class for Git-based skill pack installers.

    Provides shared logic for cloning, symlink creation, verification,
    and version detection. Subclasses only need to define pack-specific
    configuration and marker detection.
    """

    repo_urls: list[str] = []
    repo_name: str = ""
    unified_path: Path = Path(".")
    platform_symlink_paths: dict[str, Path] = {}
    clone_timeout: int = 300
    max_retries: int = 3

    def __init__(self) -> None:
        super().__init__()

    def install(
        self,
        platform: Optional[str] = None,
        force: bool = False,
        progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        from vibesop.cli import ProgressTracker

        result: Dict[str, Any] = {
            "success": False,
            "installed_path": str(self.unified_path),
            "symlinks_created": [],
            "errors": [],
            "warnings": [],
        }

        if progress is None:
            progress = ProgressTracker(f"Installing {self.repo_name} Skill Pack")
            progress.start()
            manage_progress = True
        else:
            manage_progress = False

        try:
            progress.update(10, "Checking Git availability...")
            if not self._check_git_available():
                result["errors"].append("Git is not installed. Please install Git first.")
                progress.error("Git not found")
                return result

            progress.update(20, "Checking existing installation...")
            if not force and self._is_installed():
                result["warnings"].append(
                    f"{self.repo_name} already installed at {self.unified_path}"
                )
                result["success"] = True
                progress.warning("Already installed")
                if manage_progress:
                    progress.finish("Already installed")
                return result

            progress.update(30, f"Cloning {self.repo_name} repository...")
            clone_success = self._clone_repository(progress)

            if not clone_success:
                result["errors"].append(f"Failed to clone {self.repo_name} repository")
                progress.error("Failed to clone repository")
                return result

            progress.update(70, "Creating platform symlinks...")
            platforms = (
                [platform] if platform else list(self.platform_symlink_paths.keys())
            )
            for plat in platforms:
                symlink_result = self._create_platform_symlink(plat, progress)
                if symlink_result:
                    result["symlinks_created"].append(plat)

            progress.update(90, "Verifying installation...")
            if self._verify_installation():
                result["success"] = True
                progress.success(
                    f"{self.repo_name} installed successfully at {self.unified_path}"
                )
                if manage_progress:
                    progress.finish("Installation complete")
            else:
                result["errors"].append("Installation verification failed")
                progress.error("Verification failed")

        except Exception as e:
            result["errors"].append(f"Installation failed: {e}")
            progress.error(f"Installation failed: {e}")

        return result

    def uninstall(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": False,
            "removed_path": str(self.unified_path),
            "symlinks_removed": [],
            "errors": [],
        }

        try:
            for _platform, link_dir in self.platform_symlink_paths.items():
                symlink_dir = link_dir.expanduser()
                if not symlink_dir.exists():
                    continue

                removed_count = 0
                for entry in symlink_dir.iterdir():
                    if entry.is_symlink() and entry.name.startswith(
                        f"{self.repo_name}-"
                    ):
                        try:
                            entry.unlink()
                            removed_count += 1
                        except OSError as e:
                            result["errors"].append(
                                f"Failed to remove {entry.name}: {e}"
                            )

                if removed_count > 0:
                    result["symlinks_removed"].append(
                        f"{_platform} ({removed_count} links)"
                    )

            if self.unified_path.exists():
                shutil.rmtree(self.unified_path)
                result["success"] = True
            else:
                result["errors"].append(
                    f"{self.repo_name} not found at {self.unified_path}"
                )

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def verify(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "installed": False,
            "path": str(self.unified_path),
            "git_repo": False,
            "symlinks": {},
            "markers_present": False,
            "skills_count": 0,
        }

        if not self.unified_path.exists():
            return result

        result["installed"] = True
        result["git_repo"] = (self.unified_path / ".git").exists()
        result["markers_present"] = self._check_markers()

        if result["markers_present"]:
            skill_count = self._count_skills()
            result["skills_count"] = skill_count

        for platform, link_dir in self.platform_symlink_paths.items():
            symlink_dir = link_dir.expanduser()
            platform_links: Dict[str, Any] = {
                "directory_exists": symlink_dir.exists(),
                "links": [],
                "total_count": 0,
            }

            if symlink_dir.exists():
                for entry in symlink_dir.iterdir():
                    if entry.is_symlink() and entry.name.startswith(
                        f"{self.repo_name}-"
                    ):
                        platform_links["links"].append(entry.name)
                        platform_links["total_count"] += 1

            result["symlinks"][platform] = platform_links

        return result

    def _check_git_available(self) -> bool:
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _is_installed(self) -> bool:
        return self.unified_path.exists() and self._check_markers()

    def _check_markers(self) -> bool:
        raise NotImplementedError

    def _count_skills(self) -> int:
        return 0

    def _clone_repository(self, progress: Any) -> bool:
        self.unified_path.parent.mkdir(parents=True, exist_ok=True)

        for repo_url in self.repo_urls:
            for attempt in range(self.max_retries):
                try:
                    progress.update(
                        30 + (attempt * 10),
                        f"Cloning from {repo_url} (attempt {attempt + 1}/{self.max_retries})...",
                    )

                    if self.unified_path.exists():
                        shutil.rmtree(self.unified_path)

                    subprocess.run(
                        ["git", "clone", "--depth", "1", repo_url, str(self.unified_path)],
                        capture_output=True,
                        check=True,
                        timeout=self.clone_timeout,
                    )

                    progress.success(f"Successfully cloned from {repo_url}")
                    return True

                except subprocess.TimeoutExpired:
                    progress.error(f"Timeout cloning from {repo_url}")
                    break
                except subprocess.CalledProcessError as e:
                    progress.warning(f"Failed to clone from {repo_url}: {e}")
                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        progress.update(
                            30 + (attempt * 10),
                            f"Retrying in {wait_time} seconds...",
                        )
                        time.sleep(wait_time)
                    continue
                except Exception as e:
                    progress.error(f"Unexpected error: {e}")
                    break

        return False

    def _create_platform_symlink(self, platform: str, progress: Any) -> bool:
        if platform not in self.platform_symlink_paths:
            progress.warning(f"Unknown platform: {platform}")
            return False

        try:
            link_dir = self.platform_symlink_paths[platform].expanduser()
            skill_entries = self._find_skill_entries()

            if not skill_entries:
                progress.warning(f"No skills found in {self.repo_name} directory")
                return False

            link_dir.mkdir(parents=True, exist_ok=True)

            created = 0
            skipped = 0

            for skill_path in skill_entries:
                skill_name = skill_path.name
                link_name = f"{self.repo_name}-{skill_name}"
                link_path = link_dir / link_name

                if link_path.is_symlink():
                    try:
                        if link_path.resolve() == skill_path:
                            skipped += 1
                            continue
                    except OSError:
                        pass

                if link_path.exists() and not link_path.is_symlink():
                    progress.warning(f"Skipping {link_name}: already exists")
                    continue

                if link_path.is_symlink():
                    link_path.unlink()

                try:
                    link_path.symlink_to(skill_path)
                    created += 1
                except OSError as e:
                    progress.warning(f"Failed to create {link_name}: {e}")

            progress.success(f"{platform}: {created} created, {skipped} up to date")
            return created > 0

        except Exception as e:
            progress.error(f"Failed to create symlinks for {platform}: {e}")
            return False

    def _find_skill_entries(self) -> list[Path]:
        raise NotImplementedError

    def _verify_installation(self) -> bool:
        if not self.unified_path.exists():
            return False
        if not self._check_markers():
            return False
        return (self.unified_path / ".git").exists()

    def get_status(self) -> Dict[str, Any]:
        verify_result = self.verify()
        return {
            "installed": verify_result["installed"],
            "version": self._get_version(),
            "path": verify_result["path"],
            "git_repo": verify_result["git_repo"],
            "symlinks": verify_result["symlinks"],
            "marker_files": verify_result["markers_present"],
        }

    def _get_version(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=self.unified_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
```

- [ ] **Step 2: Rewrite GstackInstaller as thin subclass**

Replace entire `src/vibesop/installer/gstack_installer.py`:

```python
"""gstack skill pack installer.

This module handles installation of the gstack skill pack
from GitHub, including repository cloning and symlink setup.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from vibesop.installer.base import GitBasedInstaller


class GstackInstaller(GitBasedInstaller):
    """Installer for gstack skill pack.

    Clones the gstack repository and sets up symlinks
    for different platforms.
    """

    repo_urls = [
        "https://github.com/garrytan/gstack.git",
        "https://gitee.com/mirrors/gstack.git",
    ]
    repo_name = "gstack"
    unified_path = Path("~/.config/skills/gstack").expanduser()
    platform_symlink_paths = {
        "claude-code": Path("~/.config/claude/skills"),
        "opencode": Path("~/.config/opencode/skills"),
    }
    clone_timeout = 300
    max_retries = 3

    def _check_markers(self) -> bool:
        markers = [
            self.unified_path / "SKILL.md",
            self.unified_path / "VERSION",
            self.unified_path / "setup",
        ]
        return all(marker.exists() for marker in markers)

    def _find_skill_entries(self) -> list[Path]:
        entries = []
        for entry in self.unified_path.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                entries.append(entry)
        return entries

    def _count_skills(self) -> int:
        return len(self._find_skill_entries())
```

- [ ] **Step 3: Rewrite SuperpowersInstaller as thin subclass**

Replace entire `src/vibesop/installer/superpowers_installer.py`:

```python
"""Superpowers skill pack installer.

This module handles installation of the Superpowers skill pack
from GitHub, including repository cloning and symlink setup.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from vibesop.installer.base import GitBasedInstaller


class SuperpowersInstaller(GitBasedInstaller):
    """Installer for Superpowers skill pack.

    Clones the Superpowers repository and sets up symlinks
    for different platforms.
    """

    repo_urls = [
        "https://github.com/obra/superpowers.git",
        "https://gitee.com/mirrors/superpowers.git",
    ]
    repo_name = "superpowers"
    unified_path = Path("~/.config/skills/superpowers").expanduser()
    platform_symlink_paths = {
        "claude-code": Path("~/.config/claude/skills"),
        "opencode": Path("~/.config/opencode/skills"),
    }
    clone_timeout = 300
    max_retries = 3

    def _check_markers(self) -> bool:
        skills_dir = self.unified_path / "skills"
        return (
            self.unified_path.exists()
            and skills_dir.exists()
            and any(skills_dir.iterdir())
        )

    def _find_skill_entries(self) -> list[Path]:
        skills_dir = self.unified_path / "skills"
        if not skills_dir.exists():
            return []
        return [e for e in skills_dir.iterdir() if e.is_dir()]

    def _count_skills(self) -> int:
        return len(self._find_skill_entries())
```

- [ ] **Step 4: Verify both installers load correctly**

Run: `uv run python -c "from vibesop.installer.gstack_installer import GstackInstaller; from vibesop.installer.superpowers_installer import SuperpowersInstaller; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/installer/base.py src/vibesop/installer/gstack_installer.py src/vibesop/installer/superpowers_installer.py
git commit -m "refactor: extract GitBasedInstaller base class, deduplicate gstack/superpowers installers"
```

---

## Phase 3: Documentation Cleanup

### Task 8: Merge root-level status documents

**Files:**
- Create: `REFACTORING.md`
- Delete: `COMPLETE.md`, `COMPLETION_SUMMARY.md`, `DEPLOYMENT_COMPLETE.md`, `DESIGN_RETROSPECTIVE.md`, `DEVELOPMENT_LOG.md`, `FINAL_SESSION_REPORT.md`, `MIGRATION_PLAN.md`, `PHASE1_COMPLETE.md`, `PHASE1_RETROSPECTIVE.md`, `PHASE2_PLAN.md`, `PROGRESS.md`, `PROJECT_CONTEXT.md`, `SESSION_SUMMARY.md`, `V2_RELEASE_COMPLETE.md`

- [ ] **Step 1: Create consolidated REFACTORING.md**

```markdown
# VibeSOP-Py Refactoring Notes

> Consolidated from multiple session documents on 2026-04-04.

## Project Status

- **Version**: 2.1.0
- **Status**: Active development, pre-production
- **Known Issues**: See GitHub Issues

## Development History

- v1.0: Core models, routing engine, CLI, LLM clients, skill management
- v2.0: Workflow orchestration, intelligent trigger system
- v2.1: Semantic recognition (Sentence Transformers), AI-powered skill enhancement

## Honest Metrics (2026-04-04 Audit)

| Metric | Value |
|--------|-------|
| Source files | 127 |
| Test files | 86 |
| Tests collected | 1,279 |
| Test collection errors | 6 (semantic module) |
| Line coverage (excluding semantic) | ~24% |
| Known bugs | See Phase 1 fixes above |

## Previous Session Summaries

Historical session documents have been consolidated into this file.
Detailed per-phase information is available in git history.
```

- [ ] **Step 2: Remove outdated status documents**

```bash
rm COMPLETE.md COMPLETION_SUMMARY.md DEPLOYMENT_COMPLETE.md DESIGN_RETROSPECTIVE.md DEVELOPMENT_LOG.md FINAL_SESSION_REPORT.md MIGRATION_PLAN.md PHASE1_COMPLETE.md PHASE1_RETROSPECTIVE.md PHASE2_PLAN.md PROGRESS.md PROJECT_CONTEXT.md SESSION_SUMMARY.md V2_RELEASE_COMPLETE.md
```

- [ ] **Step 3: Update docs/FINAL_HONEST_CHECK.md and docs/FINAL_ASSESSMENT.md**

Prepend a notice to both files:

```markdown
> **WARNING**: This document contains inaccurate claims about test coverage and feature completeness.
> See `REFACTORING.md` for corrected metrics as of 2026-04-04.
```

- [ ] **Step 4: Update docs/PROJECT_STATUS.md**

Replace inaccurate claims. Change any instance of "263+ Tests Passing" to "1,279 tests collected (6 collection errors)" and "100% Feature Complete" to "Core features implemented, semantic module tests require optional dependency".

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: consolidate status documents, correct inaccurate claims"
```

---

## Phase 4: Fix Semantic Module Tests

### Task 9: Add pytest skipif for semantic tests requiring optional dependency

**Files:**
- Modify: `tests/semantic/test_encoder.py`
- Modify: `tests/semantic/test_similarity.py`
- Modify: `tests/semantic/test_cache.py`
- Modify: `tests/semantic/test_strategies.py`
- Modify: `tests/semantic/test_e2e.py`
- Modify: `tests/triggers/test_semantic_integration.py`

- [ ] **Step 1: Verify each test file has the skipif guard**

The encoder test already has `pytest.importorskip("sentence_transformers", ...)` on line 12. Check the other 5 files. If they import numpy or sentence_transformers at module level, wrap with try/except and add `pytest.importorskip`.

For each file that doesn't have it, add at the top (after imports):

```python
import pytest

pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
```

Also ensure `numpy` is guarded:

```python
np = pytest.importorskip("numpy", reason="numpy not installed")
```

Instead of bare `import numpy as np`.

- [ ] **Step 2: Verify test collection succeeds**

Run: `uv run python -m pytest --co tests/semantic/ -q 2>&1 | tail -5`
Expected: Tests should be collected (not error). They will be SKIPPED at runtime if dependency is missing, not error during collection.

- [ ] **Step 3: Run full test collection**

Run: `uv run python -m pytest --co -q 2>&1 | tail -5`
Expected: 0 collection errors

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/ tests/triggers/test_semantic_integration.py
git commit -m "fix: add pytest.importorskip guards for semantic module tests"
```

---

### Task 10: Replace MD5 with SHA-256 in semantic/cache.py

**Files:**
- Modify: `src/vibesop/semantic/cache.py:474-487`

- [ ] **Step 1: Replace md5 with sha256**

Replace the `_hash_examples` method in `src/vibesop/semantic/cache.py` (lines 474-487):

```python
    def _hash_examples(self, examples: list[str]) -> str:
        """Compute hash of examples for cache validation.

        Args:
            examples: List of example texts.

        Returns:
            SHA-256 hash string.
        """
        import hashlib

        text = "|||".join(examples)
        return hashlib.sha256(text.encode()).hexdigest()
```

- [ ] **Step 2: Commit**

```bash
git add src/vibesop/semantic/cache.py
git commit -m "fix: replace MD5 with SHA-256 in semantic vector cache"
```

---

### Task 11: Fix duplicate TYPE_CHECKING import in semantic/cache.py

**Files:**
- Modify: `src/vibesop/semantic/cache.py:16,25-26`

- [ ] **Step 1: Fix the imports**

Line 16 has `from typing import TYPE_CHECKING, TYPE_CHECKING` (duplicate).
Lines 25-26 have an empty `if TYPE_CHECKING: pass` block.

Replace lines 16 and 25-26:

Line 16:
```python
from typing import TYPE_CHECKING
```

Remove lines 25-26 (the empty `if TYPE_CHECKING: pass` block).

- [ ] **Step 2: Commit**

```bash
git add src/vibesop/semantic/cache.py
git commit -m "fix: remove duplicate TYPE_CHECKING import and empty block in cache.py"
```

---

## Verification

### Task 12: Final verification

- [ ] **Step 1: Run full test collection**

Run: `uv run python -m pytest --co -q 2>&1 | tail -5`
Expected: 0 errors, all tests collected

- [ ] **Step 2: Run quick unit tests**

Run: `uv run python -m pytest tests/test_models.py tests/test_config.py tests/test_memory.py tests/test_cli.py --tb=no -q 2>&1 | tail -5`
Expected: All pass

- [ ] **Step 3: Check no deprecation warnings**

Run: `uv run python -W error::DeprecationWarning -c "from vibesop.workflow.models import PipelineStage; from vibesop.workflow.state import WorkflowState; print('OK')" 2>&1`
Expected: OK (no Pydantic deprecation warnings)

- [ ] **Step 4: Check no import errors**

Run: `uv run python -c "from vibesop.installer.base import BaseInstaller, GitBasedInstaller; from vibesop.installer.gstack_installer import GstackInstaller; from vibesop.installer.superpowers_installer import SuperpowersInstaller; from vibesop.triggers.activator import SkillActivator; from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer; print('All imports OK')"`
Expected: All imports OK

- [ ] **Step 5: Verify eval() is gone from dynamic_renderer**

Run: `grep -n 'eval(' src/vibesop/builder/dynamic_renderer.py`
Expected: No results

- [ ] **Step 6: Verify MagicMock is gone from activator**

Run: `grep -n 'MagicMock\|unittest.mock' src/vibesop/triggers/activator.py`
Expected: No results

- [ ] **Step 7: Final commit with refactoring summary**

If any additional fixes were needed during verification:

```bash
git add -A
git commit -m "chore: final refactoring verification and cleanup"
```
