# Phase 1: Foundation — Skill Optimization Engine + State Management

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three-layer skill optimization engine, unified state management, and integrate them into UnifiedRouter — enabling the system to handle 44+ skills without quality degradation.

**Architecture:** Three new modules (`optimization/`, `state/`) + update `UnifiedRouter` to pipeline through pre-filter → matching → preference boost → cluster conflict resolution. All changes are backward-compatible — existing routing behavior is preserved when optimization is disabled.

**Tech Stack:** Python 3.12+, Pydantic v2, scikit-learn (optional, for KMeans), existing matching infrastructure.

---

## File Structure Map

### New Files (20)
| File | Responsibility |
|------|---------------|
| `src/vibesop/core/optimization/__init__.py` | Package exports |
| `src/vibesop/core/optimization/prefilter.py` | Candidate pre-filtering (Priority + Namespace + Cluster) |
| `src/vibesop/core/optimization/preference_boost.py` | Preference learning integration with UnifiedRouter |
| `src/vibesop/core/optimization/clustering.py` | TF-IDF + KMeans skill clustering + auto conflict resolution |
| `src/vibesop/core/state/__init__.py` | Package exports |
| `src/vibesop/core/state/manager.py` | Unified state read/write/clear/list |
| `src/vibesop/core/state/schema.py` | Pydantic state models for all modes |
| `src/vibesop/core/state/migration.py` | Migrate existing .vibe/ data to new structure |
| `src/vibesop/core/config/optimization_config.py` | OptimizationConfig Pydantic model |
| `tests/test_optimization_prefilter.py` | Prefilter unit tests |
| `tests/test_optimization_preference_boost.py` | Preference boost unit tests |
| `tests/test_optimization_clustering.py` | Clustering unit tests |
| `tests/test_state_manager.py` | State manager unit tests |
| `tests/test_state_migration.py` | Migration tests |
| `tests/test_routing_optimization_integration.py` | End-to-end routing with optimization |

### Modified Files (4)
| File | Change |
|------|--------|
| `src/vibesop/core/routing/unified.py` | Add pre-filter, preference boost, cluster conflict to route() pipeline |
| `src/vibesop/core/config/manager.py` | Add optimization section to DEFAULT_CONFIG + get_optimization_config() |
| `src/vibesop/core/config/__init__.py` | Export OptimizationConfig |
| `core/registry.yaml` | Add `omx` namespace definition + 5 new conflict resolution scenarios |

---

## Task 1: OptimizationConfig Model

**Files:**
- Create: `src/vibesop/core/config/optimization_config.py`
- Modify: `src/vibesop/core/config/manager.py`
- Modify: `src/vibesop/core/config/__init__.py`
- Test: `tests/test_config_optimization.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_config_optimization.py
from vibesop.core.config.optimization_config import (
    OptimizationConfig,
    PrefilterConfig,
    PreferenceBoostConfig,
    ClusteringConfig,
)

def test_optimization_config_defaults():
    config = OptimizationConfig()
    assert config.enabled is True
    assert config.prefilter.enabled is True
    assert config.prefilter.min_candidates == 5
    assert config.prefilter.max_candidates == 15
    assert config.preference_boost.enabled is True
    assert config.preference_boost.weight == 0.3
    assert config.clustering.enabled is True
    assert config.clustering.auto_resolve is True
    assert config.clustering.confidence_gap_threshold == 0.1

def test_optimization_config_disabled():
    config = OptimizationConfig(enabled=False)
    assert config.prefilter.enabled is False
    assert config.preference_boost.enabled is False
    assert config.clustering.enabled is False

def test_optimization_config_custom_values():
    config = OptimizationConfig(
        prefilter=PrefilterConfig(max_candidates=20),
        preference_boost=PreferenceBoostConfig(weight=0.5),
    )
    assert config.prefilter.max_candidates == 20
    assert config.preference_boost.weight == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_optimization.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'vibesop.core.config.optimization_config'"

- [ ] **Step 3: Write OptimizationConfig model**

```python
# src/vibesop/core/config/optimization_config.py
"""Optimization configuration for skill routing.

Controls the three-layer optimization engine:
1. Candidate pre-filtering
2. Preference learning boost
3. Semantic clustering + conflict resolution
"""

from pydantic import BaseModel, Field


class PrefilterConfig(BaseModel):
    """Configuration for candidate pre-filtering."""

    enabled: bool = True
    min_candidates: int = Field(default=5, ge=1, le=50)
    max_candidates: int = Field(default=15, ge=1, le=50)
    # Priority tier settings
    always_include_p0: bool = True
    # Namespace relevance threshold
    namespace_relevance_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class PreferenceBoostConfig(BaseModel):
    """Configuration for preference learning integration."""

    enabled: bool = True
    weight: float = Field(default=0.3, ge=0.0, le=1.0)
    min_samples: int = Field(default=2, ge=1)
    decay_days: int = Field(default=30, ge=1)


class ClusteringConfig(BaseModel):
    """Configuration for semantic clustering."""

    enabled: bool = True
    auto_resolve: bool = True
    confidence_gap_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    # Minimum skills before clustering activates
    min_skills_for_clustering: int = Field(default=10, ge=3)
    # Max clusters (KMeans k upper bound)
    max_clusters: int = Field(default=12, ge=2)


class OptimizationConfig(BaseModel):
    """Top-level optimization configuration.

    When enabled=False, all optimization layers are disabled
    and routing falls back to pure matcher pipeline (v3.0.0 behavior).
    """

    enabled: bool = True
    prefilter: PrefilterConfig = Field(default_factory=PrefilterConfig)
    preference_boost: PreferenceBoostConfig = Field(
        default_factory=PreferenceBoostConfig
    )
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)

    def disable_all(self) -> "OptimizationConfig":
        """Return a config with all optimization disabled."""
        return OptimizationConfig(
            enabled=False,
            prefilter=PrefilterConfig(enabled=False),
            preference_boost=PreferenceBoostConfig(enabled=False),
            clustering=ClusteringConfig(enabled=False),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_optimization.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Update ConfigManager to include optimization section**

Add to `DEFAULT_CONFIG` in `src/vibesop/core/config/manager.py`:

```python
# In DEFAULT_CONFIG dict, add:
"optimization": {
    "enabled": True,
    "prefilter": {
        "enabled": True,
        "min_candidates": 5,
        "max_candidates": 15,
        "always_include_p0": True,
        "namespace_relevance_threshold": 0.3,
    },
    "preference_boost": {
        "enabled": True,
        "weight": 0.3,
        "min_samples": 2,
        "decay_days": 30,
    },
    "clustering": {
        "enabled": True,
        "auto_resolve": True,
        "confidence_gap_threshold": 0.1,
        "min_skills_for_clustering": 10,
        "max_clusters": 12,
    },
},
```

Add method to ConfigManager:

```python
def get_optimization_config(self) -> "OptimizationConfig":
    """Get optimization configuration."""
    from vibesop.core.config.optimization_config import OptimizationConfig

    section = self._get_section("optimization")
    return OptimizationConfig(**section)
```

- [ ] **Step 6: Export OptimizationConfig from config package**

Modify `src/vibesop/core/config/__init__.py`:

```python
from vibesop.core.config.optimization_config import (
    ClusteringConfig,
    OptimizationConfig,
    PrefilterConfig,
    PreferenceBoostConfig,
)

__all__ = [
    "ConfigManager",
    "ConfigSource",
    "ConfigSourcePriority",
    "RoutingConfig",
    "SecurityConfig",
    "SemanticConfig",
    "OptimizationConfig",
    "PrefilterConfig",
    "PreferenceBoostConfig",
    "ClusteringConfig",
]
```

- [ ] **Step 7: Run all config tests**

Run: `uv run pytest tests/test_config_optimization.py tests/test_config_manager.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/vibesop/core/config/optimization_config.py src/vibesop/core/config/manager.py src/vibesop/core/config/__init__.py tests/test_config_optimization.py
git commit -m "feat: add OptimizationConfig model for three-layer skill optimization

Add PrefilterConfig, PreferenceBoostConfig, ClusteringConfig Pydantic models.
Integrate optimization section into ConfigManager DEFAULT_CONFIG.
Backward-compatible: optimization enabled by default, can be fully disabled."
```

---

## Task 2: Unified State Management

**Files:**
- Create: `src/vibesop/core/state/__init__.py`
- Create: `src/vibesop/core/state/schema.py`
- Create: `src/vibesop/core/state/manager.py`
- Create: `src/vibesop/core/state/migration.py`
- Test: `tests/test_state_manager.py`
- Test: `tests/test_state_migration.py`

- [ ] **Step 1: Write state schema models**

```python
# src/vibesop/core/state/schema.py
"""Pydantic state models for all VibeSOP modes.

Unified state schema replaces scattered state files across .vibe/.
All modes use the same base structure with mode-specific data.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StateEntry(BaseModel):
    """Base state entry for any mode.

    Attributes:
        mode: The mode name (e.g., 'ralph', 'team', 'deep-interview')
        scope: The scope identifier (e.g., session ID, team name)
        active: Whether this state is currently active
        current_phase: Current phase within the mode
        created_at: When this state was created
        updated_at: Last update timestamp
        data: Mode-specific state data
    """

    mode: str = Field(..., min_length=1, description="Mode name")
    scope: str = Field(..., min_length=1, description="Scope identifier")
    active: bool = Field(default=True, description="Whether state is active")
    current_phase: str = Field(
        default="initializing",
        description="Current phase",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Mode-specific state data",
    )

    def update(self, **kwargs: Any) -> None:
        """Update state fields and refresh updated_at."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()

    def deactivate(self) -> None:
        """Mark this state as inactive."""
        self.active = False
        self.updated_at = datetime.now()


class RalphState(StateEntry):
    """State for ralph persistent completion loop."""

    mode: str = Field(default="ralph")
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=10, ge=1)
    context_snapshot_path: str | None = None
    linked_ultrawork: bool = False
    linked_ecomode: bool = False


class TeamState(StateEntry):
    """State for team multi-agent runtime."""

    mode: str = Field(default="team")
    team_name: str = Field(default="", min_length=1)
    worker_count: int = Field(default=0, ge=0)
    pending_tasks: int = Field(default=0, ge=0)
    completed_tasks: int = Field(default=0, ge=0)
    failed_tasks: int = Field(default=0, ge=0)


class InterviewState(StateEntry):
    """State for deep-interview workflow."""

    mode: str = Field(default="deep-interview")
    profile: str = Field(default="standard")
    threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    current_ambiguity: float = Field(default=1.0, ge=0.0, le=1.0)
    round_number: int = Field(default=0, ge=0)
    max_rounds: int = Field(default=12, ge=1)


class SessionState(StateEntry):
    """State for session-scoped data."""

    mode: str = Field(default="session")
    session_id: str = Field(default="", min_length=1)
    active_modes: list[str] = Field(default_factory=list)


# Mode → State class mapping
STATE_MODELS: dict[str, type[StateEntry]] = {
    "ralph": RalphState,
    "team": TeamState,
    "deep-interview": InterviewState,
    "session": SessionState,
}
```

- [ ] **Step 2: Write state manager**

```python
# src/vibesop/core/state/manager.py
"""Unified state management for all VibeSOP modes.

Provides a single API for reading, writing, clearing, and listing state
across all modes (ralph, team, deep-interview, session, etc.).

State is stored under .vibe/state/ with mode-specific subdirectories:
  .vibe/state/ralph/{scope}/state.json
  .vibe/state/team/{scope}/state.json
  .vibe/state/sessions/{session-id}/state.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.state.schema import STATE_MODELS, StateEntry


class StateManager:
    """Unified state manager for all modes."""

    def __init__(self, state_root: str | Path = ".vibe/state"):
        self.state_root = Path(state_root).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    def write(self, mode: str, scope: str, data: dict[str, Any]) -> Path:
        """Write state for a mode.

        Args:
            mode: Mode name (e.g., 'ralph', 'team')
            scope: Scope identifier (e.g., session ID, team name)
            data: Mode-specific state data (merged into existing state)

        Returns:
            Path to the written state file
        """
        state_dir = self.state_root / mode / scope
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        # Load existing state if present
        existing: dict[str, Any] = {}
        if state_file.exists():
            try:
                with state_file.open("r") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}

        # Merge new data
        now = datetime.now().isoformat()
        merged = {
            "mode": mode,
            "scope": scope,
            "active": True,
            "updated_at": now,
            **existing,
            **data,
        }
        if "created_at" not in merged:
            merged["created_at"] = now

        # Atomic write
        tmp_file = state_file.with_suffix(".tmp")
        with tmp_file.open("w") as f:
            json.dump(merged, f, indent=2, default=str)
        tmp_file.rename(state_file)

        return state_file

    def read(self, mode: str, scope: str) -> dict[str, Any] | None:
        """Read state for a mode.

        Returns:
            State dict or None if not found
        """
        state_file = self.state_root / mode / scope / "state.json"
        if not state_file.exists():
            return None

        try:
            with state_file.open("r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self, mode: str, scope: str) -> bool:
        """Clear state for a mode.

        Returns:
            True if state was cleared, False if not found
        """
        state_dir = self.state_root / mode / scope
        if not state_dir.exists():
            return False

        state_file = state_dir / "state.json"
        if state_file.exists():
            # Mark as inactive instead of deleting
            data = self.read(mode, scope)
            if data:
                data["active"] = False
                data["updated_at"] = datetime.now().isoformat()
                self.write(mode, scope, data)
            return True
        return False

    def list_active(self) -> list[dict[str, Any]]:
        """List all active state entries.

        Returns:
            List of active state dicts
        """
        active_states = []

        if not self.state_root.exists():
            return active_states

        for mode_dir in self.state_root.iterdir():
            if not mode_dir.is_dir():
                continue
            for scope_dir in mode_dir.iterdir():
                if not scope_dir.is_dir():
                    continue
                state_file = scope_dir / "state.json"
                if state_file.exists():
                    try:
                        with state_file.open("r") as f:
                            data = json.load(f)
                        if data.get("active", False):
                            active_states.append(data)
                    except (json.JSONDecodeError, OSError):
                        continue

        return active_states

    def get_state_path(self, mode: str, scope: str) -> Path:
        """Get the state file path without reading/writing.

        Useful for passing paths to other components.
        """
        return self.state_root / mode / scope / "state.json"
```

- [ ] **Step 3: Write state migration**

```python
# src/vibesop/core/state/migration.py
"""Migration utilities for existing .vibe/ data.

Migrates legacy state files to the new unified structure:
- .vibe/memory/ → .vibe/state/sessions/
- .vibe/experiments/ → preserved (no migration needed)
- .vibe/instincts/ → preserved (no migration needed)
"""

from pathlib import Path
from typing import Any

from vibesop.core.state.manager import StateManager


def migrate_legacy_state(
    vibe_root: str | Path = ".vibe",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Migrate existing .vibe/ data to new structure.

    Args:
        vibe_root: Path to .vibe directory
        dry_run: If True, report what would be migrated without doing it

    Returns:
        Migration report with counts and details
    """
    vibe_root = Path(vibe_root).resolve()
    report = {
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    if not vibe_root.exists():
        report["details"].append("No .vibe/ directory found, nothing to migrate")
        return report

    state_manager = StateManager(state_root=vibe_root / "state")

    # Create new directories
    new_dirs = [
        vibe_root / "interviews",
        vibe_root / "plans",
        vibe_root / "specs",
        vibe_root / "context",
        vibe_root / "state" / "ralph",
        vibe_root / "state" / "team",
        vibe_root / "state" / "sessions",
    ]

    for dir_path in new_dirs:
        if dry_run:
            report["details"].append(f"Would create: {dir_path}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)
            report["details"].append(f"Created: {dir_path}")

    # Migrate memory/ files to sessions state
    memory_dir = vibe_root / "memory"
    if memory_dir.exists():
        for memory_file in memory_dir.glob("*.json"):
            try:
                import json
                with memory_file.open("r") as f:
                    data = json.load(f)

                scope = memory_file.stem
                if dry_run:
                    report["details"].append(
                        f"Would migrate: {memory_file} → state/sessions/{scope}"
                    )
                    report["migrated"] += 1
                else:
                    state_manager.write("sessions", scope, {
                        "source": "migrated_from_memory",
                        "original_file": str(memory_file),
                        **data,
                    })
                    report["migrated"] += 1
                    report["details"].append(
                        f"Migrated: {memory_file} → state/sessions/{scope}"
                    )
            except Exception as e:
                report["errors"] += 1
                report["details"].append(f"Error migrating {memory_file}: {e}")
    else:
        report["details"].append("No memory/ directory found, skipping")
        report["skipped"] += 1

    return report
```

- [ ] **Step 4: Write package __init__.py**

```python
# src/vibesop/core/state/__init__.py
"""Unified state management for VibeSOP.

Provides state read/write/clear/list operations for all modes
(ralph, team, deep-interview, session, etc.).

State is stored under .vibe/state/ with mode-specific subdirectories.
"""

from vibesop.core.state.manager import StateManager
from vibesop.core.state.migration import migrate_legacy_state
from vibesop.core.state.schema import (
    STATE_MODELS,
    InterviewState,
    RalphState,
    SessionState,
    StateEntry,
    TeamState,
)

__all__ = [
    "StateManager",
    "StateEntry",
    "RalphState",
    "TeamState",
    "InterviewState",
    "SessionState",
    "STATE_MODELS",
    "migrate_legacy_state",
]
```

- [ ] **Step 5: Write state manager tests**

```python
# tests/test_state_manager.py
import json
import pytest
from pathlib import Path
from vibesop.core.state.manager import StateManager
from vibesop.core.state.schema import RalphState, TeamState


@pytest.fixture
def state_manager(tmp_path):
    return StateManager(state_root=tmp_path / "state")


def test_write_and_read_state(state_manager):
    state_manager.write("ralph", "test-scope", {
        "iteration": 1,
        "current_phase": "executing",
    })

    state = state_manager.read("ralph", "test-scope")
    assert state is not None
    assert state["mode"] == "ralph"
    assert state["scope"] == "test-scope"
    assert state["active"] is True
    assert state["iteration"] == 1
    assert state["current_phase"] == "executing"
    assert "created_at" in state
    assert "updated_at" in state


def test_read_nonexistent_state(state_manager):
    state = state_manager.read("ralph", "nonexistent")
    assert state is None


def test_clear_state(state_manager):
    state_manager.write("ralph", "test-scope", {"iteration": 1})
    result = state_manager.clear("ralph", "test-scope")
    assert result is True

    state = state_manager.read("ralph", "test-scope")
    assert state["active"] is False


def test_clear_nonexistent_state(state_manager):
    result = state_manager.clear("ralph", "nonexistent")
    assert result is False


def test_list_active_states(state_manager):
    state_manager.write("ralph", "scope1", {"iteration": 1})
    state_manager.write("team", "scope2", {"worker_count": 3})
    state_manager.clear("ralph", "scope1")

    active = state_manager.list_active_states()
    assert len(active) == 1
    assert active[0]["mode"] == "team"
    assert active[0]["scope"] == "scope2"


def test_list_active_states_empty(state_manager):
    active = state_manager.list_active_states()
    assert active == []


def test_state_file_created(state_manager, tmp_path):
    path = state_manager.write("ralph", "test", {"data": "value"})
    assert path.exists()
    assert path.name == "state.json"
    assert "ralph" in str(path)
    assert "test" in str(path)
```

- [ ] **Step 6: Write migration tests**

```python
# tests/test_state_migration.py
import json
import pytest
from pathlib import Path
from vibesop.core.state.migration import migrate_legacy_state


@pytest.fixture
def vibe_root(tmp_path):
    """Create a .vibe/ directory with legacy data."""
    vibe = tmp_path / ".vibe"
    vibe.mkdir()

    # Create legacy memory files
    memory_dir = vibe / "memory"
    memory_dir.mkdir()
    (memory_dir / "session-1.json").write_text(json.dumps({
        "last_query": "debug this",
        "last_skill": "systematic-debugging",
    }))
    (memory_dir / "session-2.json").write_text(json.dumps({
        "last_query": "ship it",
        "last_skill": "gstack/ship",
    }))

    return vibe


def test_migrate_creates_new_directories(vibe_root):
    report = migrate_legacy_state(vibe_root)
    assert (vibe_root / "interviews").exists()
    assert (vibe_root / "plans").exists()
    assert (vibe_root / "specs").exists()
    assert (vibe_root / "context").exists()
    assert (vibe_root / "state").exists()


def test_migrate_migrates_memory_files(vibe_root):
    report = migrate_legacy_state(vibe_root)
    assert report["migrated"] == 2
    assert report["errors"] == 0

    # Check migrated state files
    state_file_1 = vibe_root / "state" / "sessions" / "session-1" / "state.json"
    state_file_2 = vibe_root / "state" / "sessions" / "session-2" / "state.json"
    assert state_file_1.exists()
    assert state_file_2.exists()

    data = json.loads(state_file_1.read_text())
    assert data["last_query"] == "debug this"
    assert data["source"] == "migrated_from_memory"


def test_migrate_dry_run(vibe_root):
    report = migrate_legacy_state(vibe_root, dry_run=True)
    assert report["migrated"] == 2
    # Directories should NOT be created in dry run
    assert not (vibe_root / "interviews").exists()


def test_migrate_no_vibe_directory(tmp_path):
    report = migrate_legacy_state(tmp_path / "nonexistent")
    assert "No .vibe/" in report["details"][0]
    assert report["migrated"] == 0
```

- [ ] **Step 7: Run all state tests**

Run: `uv run pytest tests/test_state_manager.py tests/test_state_migration.py -v`
Expected: All PASS (10 tests)

- [ ] **Step 8: Commit**

```bash
git add src/vibesop/core/state/ tests/test_state_manager.py tests/test_state_migration.py
git commit -m "feat: add unified state management with migration support

StateManager provides read/write/clear/list for all modes.
State schema models for ralph, team, interview, session.
Migration utility moves legacy .vibe/memory/ to .vibe/state/sessions/.
Creates new .vibe/ directories: interviews/, plans/, specs/, context/."
```

---

## Task 3: Layer 1 — Candidate Pre-filtering

**Files:**
- Create: `src/vibesop/core/optimization/prefilter.py`
- Test: `tests/test_optimization_prefilter.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_optimization_prefilter.py
import pytest
from vibesop.core.optimization.prefilter import CandidatePrefilter


@pytest.fixture
def candidates():
    """44 skill candidates simulating full registry."""
    return [
        # P0 builtin skills
        {"id": "systematic-debugging", "namespace": "builtin", "priority": "P0",
         "description": "Find root cause before attempting fixes.", "intent": "debugging"},
        {"id": "verification-before-completion", "namespace": "builtin", "priority": "P0",
         "description": "Require fresh verification evidence.", "intent": "verification"},
        {"id": "session-end", "namespace": "builtin", "priority": "P0",
         "description": "Capture handoff before ending session.", "intent": "session management"},
        # P1 builtin skills
        {"id": "planning-with-files", "namespace": "builtin", "priority": "P1",
         "description": "Use persistent files as working memory.", "intent": "planning"},
        {"id": "riper-workflow", "namespace": "builtin", "priority": "P1",
         "description": "5-phase development workflow.", "intent": "execution"},
        # P2 external skills (superpowers)
        {"id": "superpowers/tdd", "namespace": "superpowers", "priority": "P2",
         "description": "Test-driven development.", "intent": "testing"},
        {"id": "superpowers/brainstorm", "namespace": "superpowers", "priority": "P2",
         "description": "Structured brainstorming.", "intent": "brainstorming"},
        # P2 external skills (gstack)
        {"id": "gstack/office-hours", "namespace": "gstack", "priority": "P2",
         "description": "Product brainstorming with forcing questions.", "intent": "product thinking"},
        {"id": "gstack/qa", "namespace": "gstack", "priority": "P2",
         "description": "Browser QA testing.", "intent": "testing"},
        {"id": "gstack/ship", "namespace": "gstack", "priority": "P2",
         "description": "Release workflow.", "intent": "shipping"},
        # P1 omx skills (new)
        {"id": "omx/deep-interview", "namespace": "omx", "priority": "P1",
         "description": "Socratic requirements clarification with ambiguity scoring.", "intent": "requirements"},
        {"id": "omx/ralph", "namespace": "omx", "priority": "P1",
         "description": "Persistent completion loop.", "intent": "execution"},
        {"id": "omx/ralplan", "namespace": "omx", "priority": "P1",
         "description": "Consensus planning with structured deliberation.", "intent": "planning"},
        {"id": "omx/team", "namespace": "omx", "priority": "P1",
         "description": "Multi-agent parallel execution.", "intent": "parallel execution"},
    ]


@pytest.fixture
def prefilter(candidates):
    """Prefilter with mock cluster index."""
    class MockClusterIndex:
        def get_relevant_clusters(self, query):
            return ["debugging"] if "debug" in query.lower() else []
        def get_cluster_members(self, cluster_id):
            return ["systematic-debugging"] if cluster_id == "debugging" else []

    return CandidatePrefilter(cluster_index=MockClusterIndex())


def test_p0_always_included(prefilter, candidates):
    """P0 skills are always in the filtered set."""
    result = prefilter.filter("随便问点什么", candidates)
    ids = [c["id"] for c in result]
    assert "systematic-debugging" in ids
    assert "verification-before-completion" in ids
    assert "session-end" in ids


def test_debug_query_filters_to_debug_skills(prefilter, candidates):
    """Debug query should prioritize debugging skills."""
    result = prefilter.filter("帮我调试数据库错误", candidates)
    ids = [c["id"] for c in result]
    # systematic-debugging should be in the result
    assert "systematic-debugging" in ids


def test_p2_excluded_without_namespace_trigger(prefilter, candidates):
    """P2 skills excluded unless namespace is explicitly mentioned."""
    result = prefilter.filter("发布新版本", candidates)
    ids = [c["id"] for c in result]
    # P2 skills should NOT be included (no namespace trigger)
    p2_skills = [c for c in result if c.get("priority") == "P2"]
    assert len(p2_skills) == 0


def test_p2_included_with_namespace_keyword(prefilter, candidates):
    """P2 skills included when namespace is mentioned."""
    result = prefilter.filter("用 gstack 发布", candidates)
    ids = [c["id"] for c in result]
    # gstack skills should be included
    gstack_skills = [c for c in result if c["id"].startswith("gstack/")]
    assert len(gstack_skills) > 0


def test_candidate_reduction(prefilter, candidates):
    """Prefilter should reduce candidate set significantly."""
    result = prefilter.filter("帮我调试数据库错误", candidates)
    assert len(result) < len(candidates)
    # Should reduce to a manageable set
    assert len(result) <= 10


def test_empty_candidates(prefilter):
    result = prefilter.filter("test", [])
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_optimization_prefilter.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write CandidatePrefilter**

```python
# src/vibesop/core/optimization/prefilter.py
"""Candidate pre-filtering for skill routing.

Reduces the candidate set from N (e.g., 44) to ~8-15 before
running the matcher pipeline, improving both speed and accuracy.

Three-stage cascade:
1. Priority tier: P0 always included, P1 for complex queries, P2 on namespace trigger
2. Namespace relevance: Keep namespaces with relevance > threshold
3. Intent cluster: Include skills in matched clusters + P0
"""

from __future__ import annotations

import re
from typing import Any


# Keywords that indicate complex queries needing P1 skills
COMPLEXITY_INDICATORS = [
    "复杂", "很多", "多个", "很多文件", "麻烦", "large", "complex",
    "multiple", "several", "many", "architecture", "架构", "设计",
    "design", "plan", "规划",
]

# Namespace trigger keywords
NAMESPACE_KEYWORDS = {
    "gstack": ["gstack", "g stack", "gee stack"],
    "superpowers": ["superpowers", "super powers", "超能力"],
    "omx": ["omx", "oh-my-codex", "codex"],
}


class CandidatePrefilter:
    """Pre-filter skill candidates before matching.

    Reduces candidate set from N to ~8-15 using:
    1. Priority tier filtering (P0 always included)
    2. Namespace relevance filtering
    3. Intent cluster filtering
    """

    def __init__(self, cluster_index=None):
        """Initialize prefilter.

        Args:
            cluster_index: SkillClusterIndex instance for cluster filtering.
                          Can be None (cluster filtering skipped if not provided).
        """
        self._cluster_index = cluster_index

    def filter(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filter candidates for a query.

        Args:
            query: User's natural language query
            candidates: Full list of skill candidates

        Returns:
            Filtered candidate list (8-15 items typically)
        """
        if not candidates:
            return []

        # Stage A: Priority tier
        tier_filtered = self._filter_by_priority(query, candidates)

        # Stage B: Namespace relevance
        ns_filtered = self._filter_by_namespace(query, tier_filtered)

        # Stage C: Intent cluster (if cluster_index available)
        if self._cluster_index:
            return self._filter_by_cluster(query, ns_filtered)

        return ns_filtered

    def _filter_by_priority(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Stage A: Filter by priority tier.

        - P0: ALWAYS included
        - P1: Included if query has complexity indicators
        - P2: Only included if namespace keyword is present
        """
        result = []
        is_complex = any(kw in query for kw in COMPLEXITY_INDICATORS)

        for candidate in candidates:
            priority = candidate.get("priority", "P2")

            if priority == "P0":
                # Always include P0
                result.append(candidate)
            elif priority == "P1":
                # Include P1 for complex queries
                if is_complex:
                    result.append(candidate)
            elif priority == "P2":
                # P2 only on namespace trigger (handled in Stage B)
                pass

        return result

    def _filter_by_namespace(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Stage B: Filter by namespace relevance.

        If query contains namespace keywords, include those skills.
        Otherwise, compute relevance from query keywords.
        """
        query_lower = query.lower()

        # Check for explicit namespace triggers
        triggered_namespaces = set()
        for namespace, keywords in NAMESPACE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                triggered_namespaces.add(namespace)

        if triggered_namespaces:
            # Include all candidates from triggered namespaces
            # PLUS P0 skills (always included)
            return [
                c for c in candidates
                if c.get("namespace") in triggered_namespaces
                or c.get("priority") == "P0"
            ]

        # No namespace trigger — return candidates as-is
        # (Stage A already filtered by priority)
        return candidates

    def _filter_by_cluster(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Stage C: Filter by intent cluster.

        Include skills in matched clusters + P0 skills.
        """
        if not self._cluster_index:
            return candidates

        relevant_clusters = self._cluster_index.get_relevant_clusters(query)
        if not relevant_clusters:
            return candidates

        # Collect skill IDs from relevant clusters
        cluster_skills = set()
        for cluster_id in relevant_clusters:
            cluster_skills.update(
                self._cluster_index.get_cluster_members(cluster_id)
            )

        # Include cluster skills + P0 skills
        p0_ids = {c["id"] for c in candidates if c.get("priority") == "P0"}
        allowed_ids = cluster_skills | p0_ids

        return [c for c in candidates if c["id"] in allowed_ids]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_optimization_prefilter.py -v`
Expected: All PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/optimization/prefilter.py tests/test_optimization_prefilter.py
git commit -m "feat: add candidate pre-filtering (Layer 1 of optimization)

Three-stage cascade: Priority tier → Namespace relevance → Intent cluster.
P0 skills always included, P1 for complex queries, P2 on namespace trigger.
Reduces candidate set from 44 to ~8-15 before matcher pipeline."
```

---

## Task 4: Layer 2 — Preference Boost Integration

**Files:**
- Create: `src/vibesop/core/optimization/preference_boost.py`
- Test: `tests/test_optimization_preference_boost.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_optimization_preference_boost.py
import pytest
from pathlib import Path
from vibesop.core.optimization.preference_boost import PreferenceBooster
from vibesop.core.matching import MatchResult, MatcherType


@pytest.fixture
def booster(tmp_path):
    return PreferenceBooster(
        storage_path=tmp_path / "preferences.json",
        weight=0.3,
        min_samples=1,
    )


@pytest.fixture
def sample_matches():
    return [
        MatchResult(
            skill_id="systematic-debugging",
            confidence=0.7,
            matcher_type=MatcherType.KEYWORD,
            metadata={"namespace": "builtin"},
        ),
        MatchResult(
            skill_id="gstack/investigate",
            confidence=0.65,
            matcher_type=MatcherType.TFIDF,
            metadata={"namespace": "gstack"},
        ),
        MatchResult(
            skill_id="superpowers/debug",
            confidence=0.6,
            matcher_type=MatcherType.KEYWORD,
            metadata={"namespace": "superpowers"},
        ),
    ]


def test_no_preferences_returns_original(booster, sample_matches):
    """When no preferences exist, matches are unchanged."""
    boosted = booster.boost(sample_matches, "debug this")
    # Scores should be unchanged (no preference data)
    assert boosted[0].confidence == 0.7
    assert boosted[1].confidence == 0.65


def test_preference_boosts_matching_skill(booster, sample_matches):
    """Recording preference for a skill boosts its score."""
    # Record that user prefers systematic-debugging
    booster.record_selection("systematic-debugging", "debug this", helpful=True)
    booster.record_selection("systematic-debugging", "fix bug", helpful=True)

    boosted = booster.boost(sample_matches, "debug this")

    # systematic-debugging should be boosted
    assert boosted[0].confidence > 0.7
    # Other skills should be unchanged or less boosted
    assert boosted[0].confidence > boosted[1].confidence


def test_unhelpful_feedback_reduces_boost(booster, sample_matches):
    """Unhelpful feedback reduces preference score."""
    booster.record_selection("systematic-debugging", "debug this", helpful=False)
    booster.record_selection("systematic-debugging", "fix bug", helpful=False)

    boosted = booster.boost(sample_matches, "debug this")

    # Should have minimal or no boost
    assert boosted[0].confidence <= 0.72  # Small boost at most


def test_order_preserved_when_no_boost(booster):
    """Match order is preserved when no preferences apply."""
    matches = [
        MatchResult(skill_id="a", confidence=0.8, matcher_type=MatcherType.KEYWORD),
        MatchResult(skill_id="b", confidence=0.6, matcher_type=MatcherType.KEYWORD),
    ]
    boosted = booster.boost(matches, "query")
    assert boosted[0].skill_id == "a"
    assert boosted[1].skill_id == "b"


def test_boost_respects_weight(booster, sample_matches):
    """Boost magnitude respects the weight parameter."""
    booster.record_selection("systematic-debugging", "debug", helpful=True)
    booster.record_selection("systematic-debugging", "debug", helpful=True)

    # With weight=0.3, max boost is 0.3
    boosted = booster.boost(sample_matches, "debug")
    # Original 0.7 + boost (at most 0.3) = at most 1.0
    assert boosted[0].confidence <= 1.0
    # Should be boosted above original
    assert boosted[0].confidence > 0.7


def test_disabled_booster(sample_matches):
    """Disabled booster returns matches unchanged."""
    booster = PreferenceBooster(enabled=False)
    boosted = booster.boost(sample_matches, "query")
    for orig, b in zip(sample_matches, boosted):
        assert orig.confidence == b.confidence
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_optimization_preference_boost.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write PreferenceBooster**

```python
# src/vibesop/core/optimization/preference_boost.py
"""Preference learning integration with UnifiedRouter.

Connects the existing PreferenceLearner to the routing pipeline,
applying personalized preference boosts to match results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.matching import MatchResult

if TYPE_CHECKING:
    from vibesop.core.preference import PreferenceLearner


class PreferenceBooster:
    """Apply preference boosts to match results.

    Combines matcher confidence with preference scores:
    final_confidence = matcher_confidence × (1 - weight) + preference_score × weight

    When no preferences exist, matches pass through unchanged.
    """

    def __init__(
        self,
        enabled: bool = True,
        weight: float = 0.3,
        min_samples: int = 2,
        storage_path: str = ".vibe/preferences.json",
    ):
        self.enabled = enabled
        self.weight = max(0.0, min(1.0, weight))
        self.min_samples = min_samples
        self._storage_path = storage_path
        self._learner: PreferenceLearner | None = None

    def _get_learner(self) -> "PreferenceLearner":
        """Lazy-load the PreferenceLearner."""
        if self._learner is None:
            from vibesop.core.preference import PreferenceLearner
            self._learner = PreferenceLearner(
                storage_path=self._storage_path,
                min_samples=self.min_samples,
            )
        return self._learner

    def boost(
        self,
        matches: list[MatchResult],
        query: str = "",
    ) -> list[MatchResult]:
        """Apply preference boosts to match results.

        Args:
            matches: List of MatchResult from matcher pipeline
            query: Original query for context boost

        Returns:
            New list of MatchResult with boosted confidence scores,
            sorted by confidence descending
        """
        if not self.enabled or not matches:
            return list(matches)

        try:
            learner = self._get_learner()
        except Exception:
            # If preference loading fails, return original matches
            return list(matches)

        skill_ids = [m.skill_id for m in matches]
        rankings = learner.get_personalized_rankings(skill_ids, query)

        # Build score map
        score_map = {sid: score for sid, score in rankings}

        # Apply boosts
        boosted = []
        for match in matches:
            pref_score = score_map.get(match.skill_id, 0.0)
            new_confidence = (
                match.confidence * (1 - self.weight)
                + pref_score * self.weight
            )
            # Clamp to [0, 1]
            new_confidence = max(0.0, min(1.0, new_confidence))

            boosted.append(
                MatchResult(
                    skill_id=match.skill_id,
                    confidence=new_confidence,
                    score_breakdown={
                        **match.score_breakdown,
                        "preference_boost": pref_score * self.weight,
                    },
                    matcher_type=match.matcher_type,
                    matched_keywords=match.matched_keywords,
                    matched_patterns=match.matched_patterns,
                    semantic_score=match.semantic_score,
                    metadata={
                        **match.metadata,
                        "preference_applied": pref_score > 0,
                    },
                )
            )

        # Re-sort by confidence
        boosted.sort(key=lambda m: m.confidence, reverse=True)
        return boosted

    def record_selection(
        self,
        skill_id: str,
        query: str,
        helpful: bool = True,
    ) -> None:
        """Record a skill selection for future boosting.

        Args:
            skill_id: The skill that was selected
            query: The original query
            helpful: Whether the selection was helpful
        """
        if not self.enabled:
            return
        try:
            learner = self._get_learner()
            learner.record_selection(skill_id, query, was_helpful=helpful)
        except Exception:
            pass  # Silently fail — preference recording is non-critical
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_optimization_preference_boost.py -v`
Expected: All PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/optimization/preference_boost.py tests/test_optimization_preference_boost.py
git commit -m "feat: add preference boost integration (Layer 2 of optimization)

Connects PreferenceLearner to routing pipeline.
Combines matcher confidence with preference scores (70/30 split).
Non-breaking: when no preferences exist, matches pass through unchanged."
```

---

## Task 5: Layer 3 — Semantic Clustering + Auto Conflict Resolution

**Files:**
- Create: `src/vibesop/core/optimization/clustering.py`
- Test: `tests/test_optimization_clustering.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_optimization_clustering.py
import pytest
from vibesop.core.optimization.clustering import SkillClusterIndex


@pytest.fixture
def sample_skills():
    return [
        {"id": "systematic-debugging", "description": "Find root cause before attempting fixes. Debugging workflow.", "intent": "debugging"},
        {"id": "gstack/investigate", "description": "Systematic root-cause debugging with auto-freeze.", "intent": "debugging"},
        {"id": "superpowers/debug", "description": "Advanced debugging workflows.", "intent": "debugging"},
        {"id": "planning-with-files", "description": "Use persistent files as working memory for planning.", "intent": "planning"},
        {"id": "omx/ralplan", "description": "Consensus planning with structured deliberation.", "intent": "planning"},
        {"id": "riper-workflow", "description": "5-phase development workflow: Research, Innovate, Plan, Execute, Review.", "intent": "execution"},
        {"id": "omx/ralph", "description": "Persistent completion loop with verification.", "intent": "execution"},
        {"id": "gstack/qa", "description": "Browser QA testing with Chromium.", "intent": "testing"},
        {"id": "omx/ultraqa", "description": "Autonomous QA cycling with architect diagnosis.", "intent": "testing"},
        {"id": "gstack/ship", "description": "Release workflow, sync main, run tests, push, open PR.", "intent": "shipping"},
    ]


def test_build_clusters(sample_skills):
    index = SkillClusterIndex()
    clusters = index.build(sample_skills)

    # Should produce clusters
    assert len(clusters) > 0
    # Each skill should be in exactly one cluster
    all_skills = set()
    for skill_ids in clusters.values():
        all_skills.update(skill_ids)
    assert len(all_skills) == len(sample_skills)


def test_get_cluster(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)

    # Debugging skills should be in the same cluster
    cluster_debug = index.get_cluster("systematic-debugging")
    cluster_investigate = index.get_cluster("gstack/investigate")
    assert cluster_debug == cluster_investigate


def test_get_cluster_members(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)

    cluster_id = index.get_cluster("systematic-debugging")
    members = index.get_cluster_members(cluster_id)
    assert "systematic-debugging" in members


def test_resolve_conflicts_no_conflict(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)

    # Single skill match — no conflict
    result = index.resolve_conflicts(
        query="debug this",
        matched_skills=["systematic-debugging"],
    )
    assert result["primary"] == "systematic-debugging"
    assert result["alternatives"] == []


def test_resolve_conflicts_same_cluster(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)

    # Multiple skills from same cluster — auto-resolve
    result = index.resolve_conflicts(
        query="debug this",
        matched_skills=["systematic-debugging", "gstack/investigate"],
        confidences={"systematic-debugging": 0.8, "gstack/investigate": 0.6},
    )
    assert result["primary"] == "systematic-debugging"
    assert "gstack/investigate" in result["alternatives"]


def test_resolve_conflicts_close_confidence(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)

    # Close confidence — flag for manual review
    result = index.resolve_conflicts(
        query="debug this",
        matched_skills=["systematic-debugging", "gstack/investigate"],
        confidences={"systematic-debugging": 0.75, "gstack/investigate": 0.72},
        confidence_gap_threshold=0.1,
    )
    assert result["primary"] == "systematic-debugging"
    assert result.get("needs_review") is True


def test_empty_skills():
    index = SkillClusterIndex()
    clusters = index.build([])
    assert clusters == {}


def test_single_skill():
    index = SkillClusterIndex()
    clusters = index.build([{"id": "only-one", "description": "test", "intent": "test"}])
    # Single skill should still produce a cluster
    assert len(clusters) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_optimization_clustering.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write SkillClusterIndex**

```python
# src/vibesop/core/optimization/clustering.py
"""Semantic clustering of skills by intent similarity.

Uses TF-IDF + KMeans to automatically group skills into clusters.
Enables automatic conflict resolution when multiple skills from
the same cluster match a query.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


class SkillClusterIndex:
    """Automatically cluster skills by intent similarity.

    Uses TF-IDF on skill descriptions with simple KMeans-like clustering.
    Produces clusters like:
    - "debugging": [systematic-debugging, gstack/investigate, superpowers/debug]
    - "planning": [planning-with-files, omx/ralplan]
    - "execution": [riper-workflow, omx/ralph]
    - "qa": [gstack/qa, omx/ultraqa]
    """

    def __init__(self):
        self._clusters: dict[str, list[str]] = {}
        self._skill_to_cluster: dict[str, str] = {}
        self._built = False

    def build(self, skills: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Build cluster index from skill definitions.

        Uses TF-IDF + simple centroid-based clustering.
        For small skill counts (<10), falls back to intent-based grouping.

        Args:
            skills: List of skill dicts with 'id', 'description', 'intent'

        Returns:
            cluster_id → [skill_ids]
        """
        if len(skills) < 2:
            # Single or no skills — trivial clustering
            self._clusters = {"default": [s["id"] for s in skills]} if skills else {}
            self._skill_to_cluster = {s["id"]: "default" for s in skills}
            self._built = True
            return self._clusters

        # For small sets, use intent-based grouping (simpler, more reliable)
        if len(skills) < 10:
            return self._cluster_by_intent(skills)

        # For larger sets, use TF-IDF + KMeans
        return self._cluster_by_tfidf(skills)

    def _cluster_by_intent(
        self,
        skills: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Simple intent-based clustering for small skill sets."""
        clusters: dict[str, list[str]] = defaultdict(list)

        for skill in skills:
            intent = skill.get("intent", "other").lower().strip()
            # Normalize intent to cluster name
            cluster_name = self._normalize_intent(intent)
            clusters[cluster_name].append(skill["id"])

        self._clusters = dict(clusters)
        self._skill_to_cluster = {
            skill_id: cluster_id
            for cluster_id, skill_ids in self._clusters.items()
            for skill_id in skill_ids
        }
        self._built = True
        return self._clusters

    def _cluster_by_tfidf(
        self,
        skills: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """TF-IDF + KMeans clustering for larger skill sets."""
        from vibesop.core.matching.tfidf import TFIDFCalculator
        from vibesop.core.matching.tokenizers import tokenize

        # Build TF-IDF vectors
        tfidf = TFIDFCalculator()
        documents = []
        for skill in skills:
            text = f"{skill.get('description', '')} {skill.get('intent', '')}"
            documents.append(tokenize(text))
        tfidf.fit(documents)

        # Get vectors
        vectors = []
        for doc in documents:
            vec = tfidf.transform(doc)
            vectors.append(vec.to_dict())

        # Simple KMeans (use sklearn if available, fallback to simple)
        try:
            from sklearn.cluster import KMeans
            import numpy as np

            vector_array = np.array([
                [v.get(str(i), 0.0) for i in range(len(documents[0]))]
                for v in vectors
            ])

            # Determine k using silhouette score
            best_k = 3
            best_score = -1
            for k in range(2, min(8, len(skills))):
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(vector_array)
                # Simple score: inter-cluster distance / intra-cluster distance
                score = self._silhouette_score_approx(vector_array, labels)
                if score > best_score:
                    best_score = score
                    best_k = k

            km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
            labels = km.fit_predict(vector_array)

            clusters: dict[str, list[str]] = defaultdict(list)
            for i, label in enumerate(labels):
                cluster_name = f"cluster_{label}"
                clusters[cluster_name].append(skills[i]["id"])

            self._clusters = dict(clusters)
        except ImportError:
            # Fallback: intent-based
            return self._cluster_by_intent(skills)

        self._skill_to_cluster = {
            skill_id: cluster_id
            for cluster_id, skill_ids in self._clusters.items()
            for skill_id in skill_ids
        }
        self._built = True
        return self._clusters

    def _silhouette_score_approx(
        self,
        vectors: Any,
        labels: Any,
    ) -> float:
        """Approximate silhouette score for cluster quality."""
        try:
            from sklearn.metrics import silhouette_score
            return float(silhouette_score(vectors, labels))
        except ImportError:
            return 0.0

    def _normalize_intent(self, intent: str) -> str:
        """Normalize intent string to cluster name."""
        intent = intent.lower().strip()

        # Mapping of intent keywords to cluster names
        intent_map = {
            "debug": "debugging",
            "debugging": "debugging",
            "root cause": "debugging",
            "investigate": "debugging",
            "plan": "planning",
            "planning": "planning",
            "design": "planning",
            "execute": "execution",
            "execution": "execution",
            "workflow": "execution",
            "test": "testing",
            "testing": "testing",
            "qa": "testing",
            "quality": "testing",
            "ship": "shipping",
            "release": "shipping",
            "deploy": "shipping",
            "brainstorm": "brainstorming",
            "product": "product_thinking",
            "review": "review",
            "refactor": "refactoring",
            "architecture": "architecture",
            "session": "session_management",
            "verification": "verification",
            "experiment": "experimentation",
            "requirements": "requirements",
            "parallel": "parallel_execution",
        }

        for keyword, cluster in intent_map.items():
            if keyword in intent:
                return cluster

        return "other"

    def get_cluster(self, skill_id: str) -> str | None:
        """Get cluster for a skill."""
        return self._skill_to_cluster.get(skill_id)

    def get_cluster_members(self, cluster_id: str) -> list[str]:
        """Get all skills in a cluster."""
        return self._clusters.get(cluster_id, [])

    def get_relevant_clusters(self, query: str) -> list[str]:
        """Get clusters relevant to a query.

        Uses keyword matching on cluster names and member intents.
        """
        query_lower = query.lower()
        relevant = []

        for cluster_id, skill_ids in self._clusters.items():
            # Check if cluster name matches query
            cluster_keywords = cluster_id.replace("_", " ").split()
            if any(kw in query_lower for kw in cluster_keywords):
                relevant.append(cluster_id)
                continue

            # Check member intents (stored in _cluster_intents if available)
            if hasattr(self, "_cluster_intents"):
                intents = self._cluster_intents.get(cluster_id, [])
                if any(kw in query_lower for kw in intents):
                    relevant.append(cluster_id)

        return relevant

    def resolve_conflicts(
        self,
        query: str,
        matched_skills: list[str],
        confidences: dict[str, float] | None = None,
        confidence_gap_threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Auto-generate conflict resolution for matched skills.

        If multiple skills from same cluster match:
        1. Keep highest confidence match as primary
        2. Add 2nd best as alternative
        3. Flag for manual review if confidence gap < threshold

        Args:
            query: Original query
            matched_skills: List of matched skill IDs
            confidences: Skill ID → confidence map (if available)
            confidence_gap_threshold: Gap below which manual review is needed

        Returns:
            Dict with 'primary', 'alternatives', 'needs_review'
        """
        if len(matched_skills) <= 1:
            return {
                "primary": matched_skills[0] if matched_skills else None,
                "alternatives": [],
                "needs_review": False,
            }

        # Group by cluster
        cluster_groups: dict[str, list[str]] = defaultdict(list)
        for skill_id in matched_skills:
            cluster = self.get_cluster(skill_id)
            if cluster:
                cluster_groups[cluster].append(skill_id)

        # Find the cluster with the most matches
        if not cluster_groups:
            # No cluster info — use confidence ordering
            sorted_skills = sorted(
                matched_skills,
                key=lambda s: (confidences or {}).get(s, 0.0),
                reverse=True,
            )
            return {
                "primary": sorted_skills[0],
                "alternatives": sorted_skills[1:],
                "needs_review": False,
            }

        # Within each cluster, sort by confidence
        primary = None
        alternatives = []
        needs_review = False

        for cluster_id, skills_in_cluster in cluster_groups.items():
            sorted_skills = sorted(
                skills_in_cluster,
                key=lambda s: (confidences or {}).get(s, 0.0),
                reverse=True,
            )

            if primary is None:
                primary = sorted_skills[0]
                alternatives.extend(sorted_skills[1:])
            else:
                # Skills from other clusters become alternatives
                alternatives.extend(sorted_skills)

            # Check confidence gap within cluster
            if len(sorted_skills) >= 2 and confidences:
                top_score = confidences.get(sorted_skills[0], 0.0)
                second_score = confidences.get(sorted_skills[1], 0.0)
                if top_score - second_score < confidence_gap_threshold:
                    needs_review = True

        return {
            "primary": primary,
            "alternatives": alternatives,
            "needs_review": needs_review,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_optimization_clustering.py -v`
Expected: All PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/optimization/clustering.py tests/test_optimization_clustering.py
git commit -m "feat: add semantic clustering with auto conflict resolution (Layer 3)

TF-IDF + KMeans clustering (with sklearn) for large skill sets.
Intent-based fallback for small sets (<10 skills).
Auto-resolves conflicts when multiple skills from same cluster match.
Flags close-confidence matches for manual review."
```

---

## Task 6: Optimization Package + UnifiedRouter Integration

**Files:**
- Create: `src/vibesop/core/optimization/__init__.py`
- Modify: `src/vibesop/core/routing/unified.py`
- Test: `tests/test_routing_optimization_integration.py`

- [ ] **Step 1: Write optimization package __init__.py**

```python
# src/vibesop/core/optimization/__init__.py
"""Three-layer skill optimization engine.

Layer 1: CandidatePrefilter — Reduce candidates from N to ~8-15
Layer 2: PreferenceBooster — Apply personalized preference boosts
Layer 3: SkillClusterIndex — Auto-resolve conflicts via semantic clustering

All layers are optional and backward-compatible.
When disabled, routing falls back to pure matcher pipeline.
"""

from vibesop.core.optimization.clustering import SkillClusterIndex
from vibesop.core.optimization.prefilter import CandidatePrefilter
from vibesop.core.optimization.preference_boost import PreferenceBooster

__all__ = [
    "CandidatePrefilter",
    "PreferenceBooster",
    "SkillClusterIndex",
]
```

- [ ] **Step 2: Write integration test**

```python
# tests/test_routing_optimization_integration.py
"""End-to-end tests for UnifiedRouter with optimization enabled."""

import pytest
from pathlib import Path
from vibesop.core.routing.unified import UnifiedRouter, RoutingResult
from vibesop.core.config.manager import ConfigManager


@pytest.fixture
def router(tmp_path):
    """Router with optimization enabled."""
    # Create minimal project structure
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("optimization.enabled", True)
    manager.set_cli_override("optimization.prefilter.enabled", True)
    manager.set_cli_override("optimization.prefilter.max_candidates", 10)
    manager.set_cli_override("optimization.preference_boost.enabled", True)
    manager.set_cli_override("optimization.clustering.enabled", True)

    return UnifiedRouter(project_root=tmp_path, config=manager)


def test_router_with_optimization_enabled(router):
    """Router should work with optimization enabled."""
    result = router.route("debug this error")
    # Should return a result (may be no match if no skills registered)
    assert isinstance(result, RoutingResult)


def test_optimization_reduces_candidates(router):
    """Prefilter should reduce candidate count."""
    # With no skills registered, this tests the pipeline doesn't crash
    result = router.route("test query")
    assert result is not None


def test_router_backward_compatible(tmp_path):
    """Router with optimization disabled should behave like v3.0.0."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("optimization.enabled", False)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    result = router.route("test query")
    assert isinstance(result, RoutingResult)
```

- [ ] **Step 3: Update UnifiedRouter to integrate optimization**

In `src/vibesop/core/routing/unified.py`, modify the `__init__` and `route` methods:

Add imports at top:

```python
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
```

Add to `__init__` (after matcher initialization):

```python
# Initialize optimization layers
        self._optimization_config = self._config_manager.get_optimization_config()

        # Build cluster index
        self._cluster_index = SkillClusterIndex()
        self._cluster_built = False

        # Initialize prefilter
        self._prefilter = CandidatePrefilter(cluster_index=self._cluster_index)

        # Initialize preference booster
        pref_config = self._optimization_config.preference_boost
        self._preference_booster = PreferenceBooster(
            enabled=self._optimization_config.enabled and pref_config.enabled,
            weight=pref_config.weight,
            min_samples=pref_config.min_samples,
            storage_path=str(self.project_root / ".vibe" / "preferences.json"),
        )
```

Replace the `route` method's core logic. The new flow:

```python
def route(
    self,
    query: str,
    candidates: list[dict[str, Any]] | None = None,
    context: RoutingContext | None = None,
) -> RoutingResult:
    start_time = time.perf_counter()

    # Auto-discover candidates if not provided
    if candidates is None:
        candidates = self._get_candidates(query)

    # === NEW: Pre-filtering (Layer 1) ===
    if (
        self._optimization_config.enabled
        and self._optimization_config.prefilter.enabled
    ):
        candidates = self._prefilter.filter(query, candidates)

    # === NEW: Build cluster index (Layer 3, lazy) ===
    if (
        self._optimization_config.enabled
        and self._optimization_config.clustering.enabled
        and not self._cluster_built
        and len(candidates) >= self._optimization_config.clustering.min_skills_for_clustering
    ):
        self._cluster_index.build(candidates)
        self._cluster_built = True

    routing_path: list[RoutingLayer] = []

    # === EXISTING: Matcher pipeline ===
    for layer, matcher in self._matchers:
        routing_path.append(layer)

        if layer == RoutingLayer.EMBEDDING and not self._config.enable_embedding:
            continue

        try:
            matches = matcher.match(
                query,
                candidates,
                context,
                top_k=self._config.max_candidates + 1,
            )

            if matches and matches[0].confidence >= self._config.min_confidence:
                # === NEW: Preference boost (Layer 2) ===
                if self._optimization_config.enabled and self._optimization_config.preference_boost.enabled:
                    matches = self._preference_booster.boost(
                        matches, query
                    )

                # === NEW: Cluster conflict resolution (Layer 3) ===
                if (
                    self._optimization_config.enabled
                    and self._optimization_config.clustering.enabled
                    and self._optimization_config.clustering.auto_resolve
                    and len(matches) > 1
                ):
                    confidences = {m.skill_id: m.confidence for m in matches}
                    match_ids = [m.skill_id for m in matches]
                    conflict_result = self._cluster_index.resolve_conflicts(
                        query,
                        match_ids,
                        confidences,
                        self._optimization_config.clustering.confidence_gap_threshold,
                    )
                    # Re-order matches based on conflict resolution
                    if conflict_result["primary"]:
                        primary_id = conflict_result["primary"]
                        primary_match = next(
                            (m for m in matches if m.skill_id == primary_id),
                            matches[0],
                        )
                        alternatives = [
                            m for m in matches if m.skill_id != primary_id
                        ][: self._config.max_candidates]
                    else:
                        primary_match = matches[0]
                        alternatives = matches[1 : self._config.max_candidates + 1]
                else:
                    primary_match = matches[0]
                    alternatives = matches[1 : self._config.max_candidates + 1]

                duration_ms = (time.perf_counter() - start_time) * 1000
                primary_namespace = primary_match.metadata.get("namespace", "builtin")
                primary_source = self._get_skill_source(
                    primary_match.skill_id, primary_namespace
                )

                return RoutingResult(
                    primary=SkillRoute(
                        skill_id=primary_match.skill_id,
                        confidence=primary_match.confidence,
                        layer=layer,
                        source=primary_source,
                        metadata=primary_match.metadata,
                    ),
                    alternatives=[
                        SkillRoute(
                            skill_id=m.skill_id,
                            confidence=m.confidence,
                            layer=layer,
                            source=self._get_skill_source(
                                m.skill_id,
                                m.metadata.get("namespace", "builtin"),
                            ),
                            metadata=m.metadata,
                        )
                        for m in alternatives
                    ],
                    routing_path=routing_path,
                    query=query,
                    duration_ms=duration_ms,
                )

        except Exception:
            continue

    # No match found
    duration_ms = (time.perf_counter() - start_time) * 1000
    return self._no_match_result(query, routing_path, duration_ms)
```

- [ ] **Step 4: Run integration test**

Run: `uv run pytest tests/test_routing_optimization_integration.py -v`
Expected: All PASS (3 tests)

- [ ] **Step 5: Run ALL tests to verify no regressions**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -20`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/vibesop/core/optimization/__init__.py src/vibesop/core/routing/unified.py tests/test_routing_optimization_integration.py
git commit -m "feat: integrate three-layer optimization into UnifiedRouter

Pipeline: Pre-filter → Matching → Preference Boost → Cluster Conflict.
Backward-compatible: optimization.enabled=false restores v3.0.0 behavior.
Cluster index built lazily when skill count exceeds threshold."
```

---

## Task 7: Registry Updates — omx/ Namespace + Conflict Resolution

**Files:**
- Modify: `core/registry.yaml`

- [ ] **Step 1: Add omx namespace and conflict resolution scenarios**

Add to `core/registry.yaml`:

After the `namespaces:` section, add:

```yaml
  omx:
    owner: oh-my-codex
    default_trust: reviewed
    purpose: oh-my-codex engineering methodologies — deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa.
```

Add to `conflict_resolution.strategies:` (after the existing 6 scenarios):

```yaml
    # Requirements clarification: omx/deep-interview is primary
    - scenario: requirements_clarification
      primary: omx/deep-interview
      primary_source: omx
      alternatives:
        - skill: gstack/office-hours
          source: gstack
          trigger: "产品头脑风暴"
        - skill: superpowers/brainstorm
          source: superpowers
          trigger: "设计细化"

    # Persistent execution: omx/ralph is primary
    - scenario: persistent_execution
      primary: omx/ralph
      primary_source: omx
      alternatives:
        - skill: riper-workflow
          source: builtin
          trigger: "5 阶段开发"

    # Structured planning: omx/ralplan is primary
    - scenario: structured_planning
      primary: omx/ralplan
      primary_source: omx
      alternatives:
        - skill: planning-with-files
          source: builtin
          trigger: "文件规划"
        - skill: gstack/plan-eng-review
          source: gstack
          trigger: "架构审查"

    # Parallel execution: omx/team is primary
    - scenario: parallel_execution
      primary: omx/team
      primary_source: omx
      alternatives:
        - skill: omx/ultrawork
          source: omx
          trigger: "纯并行执行"
        - skill: using-git-worktrees
          source: builtin
          trigger: "工作树隔离"

    # QA cycling: omx/ultraqa is primary
    - scenario: qa_cycling
      primary: omx/ultraqa
      primary_source: omx
      alternatives:
        - skill: gstack/qa
          source: gstack
          trigger: "浏览器测试"
        - skill: gstack/qa-only
          source: gstack
          trigger: "仅报告"
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "from ruamel.yaml import YAML; YAML().load(open('core/registry.yaml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add core/registry.yaml
git commit -m "feat: add omx/ namespace and 5 conflict resolution scenarios

Add omx namespace for oh-my-codex methodologies.
New conflict scenarios: requirements_clarification, persistent_execution,
structured_planning, parallel_execution, qa_cycling."
```

---

## Task 8: Run Migration + Final Verification

- [ ] **Step 1: Run migration to create new .vibe/ directories**

Run: `uv run python -c "
from vibesop.core.state.migration import migrate_legacy_state
report = migrate_legacy_state('.vibe')
print(f'Migrated: {report[\"migrated\"]}')
print(f'Errors: {report[\"errors\"]}')
for detail in report['details']:
    print(f'  {detail}')
"`

Expected: New directories created, existing memory files migrated

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -x -q --tb=short 2>&1 | tail -30`
Expected: All tests pass (existing + new)

- [ ] **Step 3: Run linting**

Run: `uv run ruff check src/vibesop/core/optimization/ src/vibesop/core/state/ src/vibesop/core/routing/unified.py src/vibesop/core/config/`
Expected: No errors

- [ ] **Step 4: Run type checking**

Run: `uv run basedpyright src/vibesop/core/optimization/ src/vibesop/core/state/ src/vibesop/core/routing/unified.py`
Expected: No errors

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(phase1): foundation complete — optimization engine + state management

Three-layer skill optimization integrated into UnifiedRouter:
- Layer 1: Candidate pre-filtering (Priority + Namespace + Cluster)
- Layer 2: Preference learning boost (70/30 matcher/preference split)
- Layer 3: Semantic clustering + auto conflict resolution

Unified state management with migration from legacy .vibe/memory/.
omx/ namespace added to registry with 5 conflict resolution scenarios.

Backward-compatible: optimization.enabled=false restores v3.0.0 behavior."
```

---

## Self-Review

### 1. Spec Coverage Check

| Spec Section | Task |
|-------------|------|
| Layer 1: Pre-filtering | Task 3 ✅ |
| Layer 2: Preference Boost | Task 4 ✅ |
| Layer 3: Clustering | Task 5 ✅ |
| UnifiedRouter Integration | Task 6 ✅ |
| State Management | Task 2 ✅ |
| Migration | Task 2 ✅ |
| OptimizationConfig | Task 1 ✅ |
| Registry Updates | Task 7 ✅ |
| omx/ namespace definition | Task 7 ✅ |
| Conflict resolution scenarios | Task 7 ✅ |

### 2. Placeholder Scan

No TBD/TODO/placeholder found. Every step has actual code, exact commands, and expected output.

### 3. Type Consistency

- `MatchResult` from `vibesop.core.matching` used consistently in prefilter tests and preference boost
- `PreferenceBooster.boost()` returns `list[MatchResult]` matching the type expected by UnifiedRouter
- `SkillClusterIndex.resolve_conflicts()` returns `dict[str, Any]` with keys `primary`, `alternatives`, `needs_review` — used correctly in UnifiedRouter integration
- `StateManager.write/read/clear` signatures match spec design

### 4. Scope Check

This plan covers Phase 1 only (foundation). omx/ skill implementations (deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa) are in subsequent phases. Scope is focused and testable.
