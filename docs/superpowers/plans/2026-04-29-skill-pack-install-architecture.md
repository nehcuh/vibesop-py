# Skill Pack Installation Architecture Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the external skill pack installation pipeline so that `vibe install`, `vibe build`, and the routing engine work together correctly for both trusted packs (gstack/superpowers/omx) and arbitrary third-party packs from Git URLs.

**Architecture:** Central storage (`~/.config/skills/<pack>/`) holds full pack clones for auditing and updates. Platform skill directories (`~/.kimi/skills/`) contain only per-skill symlinks pointing to individual skill directories in central storage. The routing engine discovers installed skills dynamically from central storage rather than relying solely on the static `registry.yaml`.

**Tech Stack:** Python 3.12+, dataclasses, pathlib, ruamel.yaml, Jinja2

---

## Current State — Issues

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| P1 | Pack-level symlink exposes non-skill files (bun toolchain, extension, tests) | `pack_installer.py:_create_symlinks()` | High |
| P1 | Build creates stubs for installed packs; `vibe install` has to clean them up | `adapters/_shared.py:_render_skill_content()` | High |
| P2 | External packs installed via URL not discoverable by routing engine | `routing/`, `registry.yaml` | High |
| P2 | No user-configurable security whitelist for untrusted packs | `security/`, `constants.py` | Medium |
| P3 | LLM-assisted layout detection for non-standard packs | `installer/analyzer.py` | Medium |
| P4 | superpowers naming mismatch: `registry.yaml:superpowers/tdd` vs directory `test-driven-development` | `registry.yaml`, `_shared.py` | Low |

---

## Phase 1: Fix Symlink Architecture (P1)

### Task 1.1: Remove pack-level symlinks from `_create_symlinks()`

**Files:**
- Modify: `src/vibesop/installer/pack_installer.py:201-300`
- Modify: `tests/installer/test_pack_installer.py`

- [ ] **Step 1: Refactor `_create_symlinks()` to only create skill-level symlinks**

In `src/vibesop/installer/pack_installer.py`, replace the pack-level symlink logic in `_create_symlinks()`:

```python
def _create_symlinks(
    self,
    pack_name: str,
    platforms: list[str] | None = None,
    _analysis: RepoAnalysis | None = None,
) -> list[tuple[str, str]]:
    """Create per-skill symlinks from platform directories to central storage.

    For each SKILL.md found in the pack, creates a symlink in each platform
    directory using flattened naming (e.g., gstack-review -> gstack/review/).

    Pack-level symlinks are intentionally NOT created — only individual
    skill symlinks so the platform directory stays clean.
    """
    results: list[tuple[str, str]] = []
    storage = SkillStorage()
    central_path = self.central_storage / pack_name

    if not central_path.exists():
        return results

    platforms_to_link = platforms or list(storage.PLATFORM_SKILLS_DIRS.keys())

    for platform in platforms_to_link:
        if platform not in storage.PLATFORM_SKILLS_DIRS:
            results.append((platform, "Unknown platform"))
            continue

        platform_dir = storage.PLATFORM_SKILLS_DIRS[platform]

        try:
            platform_dir.mkdir(parents=True, exist_ok=True)

            # Only create skill-level symlinks, not pack-level
            skill_count = self._create_skill_symlinks(
                central_path, platform_dir, pack_name, platform
            )

            results.append((platform, f"Linked to {platform} ({skill_count} skills)"))

        except OSError:
            try:
                skill_count = self._copy_skill_dirs(
                    central_path, platform_dir, pack_name
                )
                results.append((platform, f"Copied to {platform} ({skill_count} skills, symlinks not supported)"))
            except Exception as copy_err:
                results.append((platform, f"Failed: {copy_err}"))

    return results
```

- [ ] **Step 2: Remove the pack-level symlink creation block**

Delete the block in `_create_symlinks()` that handles pack-level symlink creation (the `platform_path = platform_dir / pack_name` block and fallback copy block). The method should only call `_create_skill_symlinks()`.

- [ ] **Step 3: Remove the fallback `_copy_skill_dirs()` pack-level copy**

In the OSError fallback, remove the `shutil.copytree(central_path, platform_path)` line. Only call `_copy_skill_dirs()` for individual skills.

- [ ] **Step 4: Run existing tests**

```bash
.venv/bin/python -m pytest tests/installer/ -x -v
```

Expected: 47 tests pass, coverage threshold warning.

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/installer/pack_installer.py
git commit -m "refactor(pack_installer): remove pack-level symlinks, keep only per-skill symlinks"
```

### Task 1.2: Fix adapter `_render_skill_content()` to create symlinks for installed packs

**Files:**
- Modify: `src/vibesop/adapters/_shared.py`
- Modify: `src/vibesop/adapters/base.py`
- Modify: `src/vibesop/adapters/opencode.py:243-275`
- Modify: `src/vibesop/adapters/kimi_cli.py` (same pattern)
- Modify: `src/vibesop/adapters/claude_code.py` (same pattern)

- [ ] **Step 1: Add `_is_pack_installed()` helper to `_shared.py`**

```python
def is_pack_installed(skill_id: str) -> Path | None:
    """Check if the external pack for a skill is installed in central storage.

    For skill IDs like 'gstack/review' or 'superpowers/brainstorm',
    checks if ~/.config/skills/<namespace>/ exists.

    Returns:
        Path to the installed skill directory or None
    """
    if "/" not in skill_id:
        return None

    parts = skill_id.split("/", 1)
    namespace = parts[0]
    skill_name = parts[1]

    central_base = Path.home() / ".config" / "skills"

    # Try both layout patterns
    candidates = [
        central_base / namespace / skill_name,
        central_base / namespace / "skills" / skill_name,
    ]
    for candidate in candidates:
        if candidate.exists() and (candidate / "SKILL.md").exists():
            return candidate

    return None
```

- [ ] **Step 2: Add `_create_or_update_skill_symlink()` to `_shared.py`**

```python
def create_or_update_skill_symlink(
    skill_id: str,
    skill_dir_on_disk: Path,
    source_path: Path,
) -> bool:
    """Create or update a symlink from platform skill dir to central storage.

    Removes any existing stub directory or broken link before creating
    the new symlink. Handles the OSError fallback for Windows.

    Args:
        skill_id: Skill identifier (e.g., 'gstack/review')
        skill_dir_on_disk: Platform path (e.g., ~/.kimi/skills/gstack-review/)
        source_path: Central storage path (e.g., ~/.config/skills/gstack/review/)

    Returns:
        True if symlink created or already correct
    """
    try:
        if skill_dir_on_disk.is_symlink():
            current_target = skill_dir_on_disk.resolve()
            if current_target == source_path.resolve():
                return True  # Already correct
            skill_dir_on_disk.unlink()
        elif skill_dir_on_disk.exists():
            if skill_dir_on_disk.is_dir():
                shutil.rmtree(skill_dir_on_disk)
            else:
                skill_dir_on_disk.unlink()

        skill_dir_on_disk.symlink_to(source_path, target_is_directory=True)
        return True
    except OSError:
        # Windows fallback: copy instead of symlink
        try:
            if skill_dir_on_disk.exists():
                shutil.rmtree(skill_dir_on_disk)
            shutil.copytree(source_path, skill_dir_on_disk)
            return True
        except Exception:
            return False
```

Note: needs `import shutil` at the top of `_shared.py`.

- [ ] **Step 3: Update `PlatformAdapter._find_skill_content()` in `base.py`**

```python
def _find_skill_content(self, skill_id: str) -> str | None:
    """Try to find skill content, preferring central storage over project files."""
    from vibesop.adapters._shared import find_skill_content, is_pack_installed

    content = find_skill_content(skill_id, self._project_root)
    if content:
        return content

    # Check if installed in central storage with different layout
    if "/" in skill_id:
        installed_path = is_pack_installed(skill_id)
        if installed_path:
            skill_file = installed_path / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text(encoding="utf-8")
    return None
```

- [ ] **Step 4: Update `_render_skill_content()` in `opencode.py`**

Replace the existing fallback logic. When a pack is installed, create a symlink instead of writing a stub:

```python
def _render_skill_content(self, skill, skill_dir, result, dir_name=None):
    skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
    skill_output_path = skill_dir / "SKILL.md"

    skill_content = self._find_skill_content(skill_id)

    if skill_content:
        skill_content = self._normalize_skill_type(skill_content)
        self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
        result.add_file(skill_output_path)
        return

    # Check if external pack is installed — if so, create symlink
    from vibesop.adapters._shared import is_pack_installed

    installed_path = is_pack_installed(skill_id)
    if installed_path:
        # Remove stub dir and create symlink
        if skill_dir.exists() and not skill_dir.is_symlink():
            import shutil
            if skill_dir.is_dir():
                shutil.rmtree(skill_dir)
        try:
            skill_dir.symlink_to(installed_path, target_is_directory=True)
            result.add_file(skill_dir / "SKILL.md")
            return
        except OSError:
            import shutil
            shutil.copytree(installed_path, skill_dir)
            result.add_file(skill_dir / "SKILL.md")
            return

    # Pack not installed — create informational stub
    fallback_content = self._generate_fallback_skill_content(skill, dir_name=dir_name)
    self.write_file_atomic(skill_output_path, fallback_content, validate_security=False)
    result.add_file(skill_output_path)
```

- [ ] **Step 5: Apply the same change to `kimi_cli.py`**

The `_render_skill_content()` in `src/vibesop/adapters/kimi_cli.py` follows the same pattern as opencode.py. Apply identical changes.

- [ ] **Step 6: Apply the same change to `claude_code.py`**

The `_render_skill_content()` in `src/vibesop/adapters/claude_code.py` at line ~350 follows a slightly different pattern (uses Jinja2 template fallback). Update accordingly.

- [ ] **Step 7: Run all tests**

```bash
.venv/bin/python -m pytest tests/installer/ tests/adapters/ -x -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/vibesop/adapters/_shared.py src/vibesop/adapters/base.py src/vibesop/adapters/opencode.py src/vibesop/adapters/kimi_cli.py src/vibesop/adapters/claude_code.py
git commit -m "fix(adapters): create symlinks instead of stubs for installed external packs"
```

### Task 1.3: Update Quickstart flow

**Files:**
- Modify: `src/vibesop/installer/quickstart_runner.py:281-348`

- [ ] **Step 1: After `_install_integration()`, trigger symlink creation**

In `_execute_installation()`, after the integration install loop, add a step that creates platform skill symlinks:

```python
# Step 3: Install integrations (if requested)
if config.install_integrations:
    for integration in self._available_integrations:
        self._install_integration(integration, config.platform)

    # Sync symlinks for newly installed packs to all configured platforms
    self._sync_platform_symlinks(config.platform)
```

- [ ] **Step 2: Add `_sync_platform_symlinks()` method**

```python
def _sync_platform_symlinks(self, platform: str) -> None:
    """Sync skill symlinks from central storage to platform directory."""
    from vibesop.core.skills.external_loader import ExternalSkillLoader
    from vibesop.core.skills.storage import SkillStorage
    from pathlib import Path
    import shutil

    storage = SkillStorage()
    platform_dir = storage.PLATFORM_SKILLS_DIRS.get(platform)
    if not platform_dir:
        return

    loader = ExternalSkillLoader()
    discovered = loader.discover_all()

    count = 0
    for skill_id, meta in discovered.items():
        if not skill_id or "/" not in skill_id:
            continue
        parts = skill_id.split("/", 1)
        namespace = parts[0]
        skill_name = parts[1]

        # Determine central source path
        central = Path.home() / ".config" / "skills"
        source = None
        for candidate in [
            central / namespace / skill_name,
            central / namespace / "skills" / skill_name,
        ]:
            if candidate.exists() and (candidate / "SKILL.md").exists():
                source = candidate
                break

        if not source:
            continue

        # Create flattened symlink
        flat_name = skill_id.replace("/", "-")
        target = platform_dir / flat_name

        try:
            if target.exists():
                if target.is_symlink():
                    if target.resolve() == source.resolve():
                        continue
                    target.unlink()
                elif target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.symlink_to(source, target_is_directory=True)
            count += 1
        except OSError:
            pass

    if count > 0:
        console.print(f"  ✓ Synced {count} skill symlinks to {platform}")
```

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/installer/quickstart_runner.py
git commit -m "feat(quickstart): sync platform skill symlinks after pack installation"
```

---

## Phase 2: Dynamic Skill Discovery (P2)

### Task 2.1: Bridge `ExternalSkillLoader` into the routing engine

**Files:**
- Create: `src/vibesop/core/routing/dynamic_discovery.py`
- Modify: `src/vibesop/core/config/manager.py` (or the routing initialization)
- Test: `tests/core/routing/test_dynamic_discovery.py`

- [ ] **Step 1: Create `DynamicSkillDiscovery` class**

```python
"""Dynamic skill discovery from central storage.

Bridges ExternalSkillLoader (disk discovery) into the routing engine
so that externally installed packs are automatically available for routing
without manual registry.yaml updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DiscoveredSkill:
    id: str
    name: str
    description: str
    namespace: str
    source_path: Path
    triggers: list[str]


class DynamicSkillDiscovery:
    """Discovers installed skills from central storage for routing."""

    def discover(self) -> list[DiscoveredSkill]:
        """Scan ~/.config/skills/ for installed packs.

        Returns:
            List of DiscoveredSkill for all installed external packs
        """
        from vibesop.core.skills.external_loader import ExternalSkillLoader
        from vibesop.core.skills.parser import parse_skill_md

        loader = ExternalSkillLoader()
        raw = loader.discover_all()

        discovered = []
        for skill_id, meta in raw.items():
            if not skill_id or "/" not in skill_id:
                continue

            parts = skill_id.split("/", 1)
            namespace = parts[0]
            skill_name = parts[1]

            skill_file = meta.install_path / "SKILL.md" if meta.install_path else None
            triggers = []
            if skill_file:
                parsed = parse_skill_md(skill_file)
                if parsed and parsed.triggers:
                    triggers = parsed.triggers

            discovered.append(DiscoveredSkill(
                id=skill_id,
                name=meta.base_metadata.name,
                description=meta.base_metadata.description or "",
                namespace=namespace,
                source_path=meta.install_path or Path(),
                triggers=triggers,
            ))

        return discovered

    def merge_with_registry(
        self, registry_skills: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge dynamically discovered skills with static registry entries.

        Discovered skills supplement (not replace) registry entries.
        If a skill exists in both, the registry entry takes precedence
        for priority and metadata.

        Args:
            registry_skills: List of skill dicts from registry.yaml

        Returns:
            Merged list with discovered skills appended
        """
        registry_ids = {s["id"] for s in registry_skills}
        discovered = self.discover()

        merged = list(registry_skills)
        for skill in discovered:
            if skill.id not in registry_ids:
                merged.append({
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "namespace": skill.namespace,
                    "entrypoint": "external",
                    "priority": "P3",  # Discovered skills get default priority
                    "triggers": skill.triggers,
                })

        return merged
```

- [ ] **Step 2: Write tests**

```python
# tests/core/routing/test_dynamic_discovery.py

import pytest
from pathlib import Path
from vibesop.core.routing.dynamic_discovery import DynamicSkillDiscovery, DiscoveredSkill


class TestDynamicSkillDiscovery:
    def test_discover_installed_packs(self):
        discovery = DynamicSkillDiscovery()
        skills = discovery.discover()

        # Should find gstack, superpowers, omx if installed
        ids = [s.id for s in skills]
        assert len(skills) > 0, "Expected at least one installed pack"

    def test_merge_with_registry_no_duplicates(self):
        discovery = DynamicSkillDiscovery()
        registry = [
            {"id": "gstack/review", "name": "Review", "namespace": "gstack"},
        ]
        merged = discovery.merge_with_registry(registry)

        # Registry entry should not be duplicated
        gstack_entries = [s for s in merged if s["id"] == "gstack/review"]
        assert len(gstack_entries) == 1

    def test_merge_with_registry_adds_new(self):
        discovery = DynamicSkillDiscovery()
        registry = []
        merged = discovery.merge_with_registry(registry)

        # Should include discovered skills
        ids = [s["id"] for s in merged]
        # At minimum, some gstack skills if installed
        gstack_skills = [i for i in ids if i.startswith("gstack/")]
        assert len(gstack_skills) > 0 or len(merged) > 0
```

- [ ] **Step 3: Integrate into `ManifestBuilder._load_skills()`**

In `src/vibesop/builder/manifest.py`, modify `_load_skills()` to call `DynamicSkillDiscovery.merge_with_registry()` after loading the static registry:

```python
def _load_skills(self) -> list:
    manager = ConfigManager()
    registry_skills = manager.get_all_skills()

    # Augment with dynamically discovered skills
    from vibesop.core.routing.dynamic_discovery import DynamicSkillDiscovery
    discovery = DynamicSkillDiscovery()
    merged_skills = discovery.merge_with_registry(registry_skills)

    skills = []
    for skill_data in merged_skills:
        skill = self._build_skill_definition(skill_data)
        if skill:
            skills.append(skill)
    return skills
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/core/routing/ -x -v
```

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/routing/dynamic_discovery.py tests/core/routing/test_dynamic_discovery.py src/vibesop/builder/manifest.py
git commit -m "feat(routing): dynamic skill discovery from installed packs in central storage"
```

---

## Phase 3: Security Whitelist (P2)

### Task 3.1: User-configurable trust list

**Files:**
- Create: `src/vibesop/core/skills/trust.py`
- Modify: `src/vibesop/security/skill_auditor.py`
- Modify: `src/vibesop/cli/commands/install.py`
- Create: `src/vibesop/cli/commands/trust.py`
- Test: `tests/core/skills/test_trust.py`

- [ ] **Step 1: Create `TrustStore` in `src/vibesop/core/skills/trust.py`**

```python
"""Trust store for user-approved skill pack sources."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class TrustStore:
    """Persistent store for user-approved skill pack sources.

    Stored at ~/.config/skills/.trusted.json
    """

    PATH: Path = Path.home() / ".config" / "skills" / ".trusted.json"

    def __init__(self) -> None:
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.PATH.exists():
            return {"packs": {}, "sources": {}}
        try:
            return json.loads(self.PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {"packs": {}, "sources": {}}

    def _save(self) -> None:
        self.PATH.parent.mkdir(parents=True, exist_ok=True)
        self.PATH.write_text(json.dumps(self._data, indent=2))

    def is_trusted_pack(self, pack_name: str) -> bool:
        return pack_name in self._data.get("packs", {})

    def is_trusted_source(self, source_url: str) -> bool:
        return source_url in self._data.get("sources", {})

    def trust_pack(self, pack_name: str, source_url: str = "") -> None:
        self._data.setdefault("packs", {})[pack_name] = {
            "trusted_at": datetime.now().isoformat(),
            "source": source_url,
        }
        self._save()

    def trust_source(self, source_url: str, reason: str = "") -> None:
        self._data.setdefault("sources", {})[source_url] = {
            "trusted_at": datetime.now().isoformat(),
            "reason": reason,
        }
        self._save()

    def revoke(self, key: str) -> bool:
        removed = (
            self._data.get("packs", {}).pop(key, None)
            or self._data.get("sources", {}).pop(key, None)
        )
        if removed:
            self._save()
        return removed is not None

    def get_trusted_packs(self) -> dict[str, Any]:
        return dict(self._data.get("packs", {}))

    def get_trusted_sources(self) -> dict[str, Any]:
        return dict(self._data.get("sources", {}))
```

- [ ] **Step 2: Integrate `TrustStore` into `SkillSecurityAuditor`**

Modify `src/vibesop/security/skill_auditor.py` to consult the trust store before rejecting a skill:

In the `audit_skill_file()` method, add:

```python
# Check user trust store before blocking
from vibesop.core.skills.trust import TrustStore
trust_store = TrustStore()

# If the pack is in the user's trust list, downgrade HIGH threats
if self._pack_name and trust_store.is_trusted_pack(self._pack_name):
    for threat in audit_result.threats:
        if threat.level.value == "high":
            threat.level = RiskLevel.MEDIUM
    audit_result._recalculate()
```

- [ ] **Step 3: Write tests**

```python
# tests/core/skills/test_trust.py

import pytest
from vibesop.core.skills.trust import TrustStore


class TestTrustStore:
    def test_trust_and_check_pack(self, tmp_path):
        store = TrustStore()
        store.trust_pack("my-custom-pack", "https://github.com/user/skills")

        assert store.is_trusted_pack("my-custom-pack")
        assert not store.is_trusted_pack("unknown-pack")

    def test_trust_and_revoke(self, tmp_path):
        store = TrustStore()
        store.trust_pack("test-pack")
        assert store.is_trusted_pack("test-pack")

        store.revoke("test-pack")
        assert not store.is_trusted_pack("test-pack")

    def test_trust_source(self, tmp_path):
        store = TrustStore()
        store.trust_source("https://github.com/user/tools", "needed for CI")

        assert store.is_trusted_source("https://github.com/user/tools")
```

- [ ] **Step 4: Add `vibe trust` CLI command**

Create `src/vibesop/cli/commands/trust.py`:

```python
"""vibe trust - Manage user trust list for skill packs."""

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.skills.trust import TrustStore

console = Console()

def trust(
    pack: str = typer.Argument(..., help="Pack name or source URL to trust"),
    source_url: str = typer.Option("", "--source", "-s", help="Source URL"),
    revoke: bool = typer.Option(False, "--revoke", "-r", help="Revoke trust"),
    list_trusted: bool = typer.Option(False, "--list", "-l", help="List trusted packs"),
) -> None:
    """Manage the skill pack trust list."""
    store = TrustStore()

    if list_trusted:
        _list_trusted(store)
        return

    if revoke:
        if store.revoke(pack):
            console.print(f"[green]✓ Revoked trust for {pack}[/green]")
        else:
            console.print(f"[yellow]⊘ {pack} was not trusted[/yellow]")
        return

    # Determine if pack name or URL
    if pack.startswith(("http://", "https://")):
        store.trust_source(pack)
        console.print(f"[green]✓ Trusted source: {pack}[/green]")
        console.print("[dim]Skills from this source will skip HIGH-level threat blocks[/dim]")
    else:
        store.trust_pack(pack, source_url)
        console.print(f"[green]✓ Trusted pack: {pack}[/green]")
        console.print("[dim]Subsequent installs of this pack skip security audit blocks[/dim]")


def _list_trusted(store: TrustStore) -> None:
    t = Table(title="Trusted Skill Packs & Sources")
    t.add_column("Name/Source")
    t.add_column("Type")
    t.add_column("Trusted At")

    for name, info in store.get_trusted_packs().items():
        t.add_row(name, "pack", info.get("trusted_at", ""))
    for url, info in store.get_trusted_sources().items():
        t.add_row(url, "source", info.get("trusted_at", ""))

    console.print(t)
```

Register the command in `src/vibesop/cli/main.py`:
```python
app.command(name="trust")(trust_command.trust)
```

- [ ] **Step 5: Update `vibe install` to prompt for trust on untrusted packs**

In `src/vibesop/cli/commands/install.py` `_install_pack()`, after a failed security audit, show a prompt:

```python
if not audit_result.get("is_safe"):
    console.print(
        "[yellow]⚠ Security audit flagged issues with this pack[/yellow]\n"
        f"[dim]Issues: {audit_result.get('summary')}[/dim]\n\n"
        "You can:\n"
        "  1. Review the source code manually\n"
        f"  2. Trust this source: [cyan]vibe trust {pack_url or pack_name}[/cyan]\n"
        "  3. Cancel installation\n"
    )
```

- [ ] **Step 6: Commit**

```bash
git add src/vibesop/core/skills/trust.py src/vibesop/security/skill_auditor.py src/vibesop/cli/commands/trust.py src/vibesop/cli/commands/install.py tests/core/skills/test_trust.py
git commit -m "feat(security): user-configurable trust list for skill pack sources"
```

---

## Phase 4: LLM-Assisted Pack Installation (P3)

### Task 4.1: AI analyzer for non-standard pack layouts

**Files:**
- Create: `src/vibesop/installer/ai_analyzer.py`
- Modify: `src/vibesop/installer/analyzer.py`
- Test: `tests/installer/test_ai_analyzer.py`

- [ ] **Step 1: Create `AIAnalyzer` class**

```python
"""AI-assisted repository analyzer for non-standard skill packs.

When the rule-based RepoAnalyzer can't determine the layout or
dependency structure, this module uses an LLM to read the README
and infer how to install the pack.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

AI_ANALYSIS_PROMPT = """You are analyzing a skill pack repository to determine how to install it.

Repository: {repo_path}
README content:
{readme_content}

Directory structure (top-level):
{dir_structure}

SKILL.md files found:
{skill_files}

Answer in JSON:
{{
  "layout_type": "flat|nested|simple|mixed",
  "skill_root": "subdirectory where skills live, or empty for flat",
  "dependencies": ["bun", "npm", "pip", ...],
  "setup_commands": ["command1", "command2"],
  "confidence": 0.0-1.0,
  "notes": "any observations"
}}

If the layout is unclear, set confidence low. Do not guess dependencies —
only list what the README or toolchain files (package.json, etc.) explicitly
mention. If the README has no setup instructions, setup_commands should be empty.
"""


@dataclass
class AIAnalysis:
    layout_type: str
    skill_root: str
    dependencies: list[str]
    setup_commands: list[str]
    confidence: float
    notes: str

    @classmethod
    def from_llm_response(cls, text: str) -> AIAnalysis:
        data = json.loads(text)
        return cls(
            layout_type=data.get("layout_type", "simple"),
            skill_root=data.get("skill_root", ""),
            dependencies=data.get("dependencies", []),
            setup_commands=data.get("setup_commands", []),
            confidence=data.get("confidence", 0.0),
            notes=data.get("notes", ""),
        )


class AIAnalyzer:
    """Uses LLM to analyze non-standard skill pack repositories."""

    def __init__(self, llm_provider: str = "auto"):
        self._llm_provider = llm_provider

    def analyze(self, repo_path: Path) -> AIAnalysis | None:
        """Analyze a repository using LLM.

        Only called when the rule-based RepoAnalyzer produces
        layout_type="mixed" or dependencies=[] with an unusual structure.

        Args:
            repo_path: Path to cloned repository

        Returns:
            AIAnalysis or None if LLM unavailable
        """
        readme_path = None
        for name in ("README.md", "README.rst", "README.txt"):
            candidate = repo_path / name
            if candidate.exists():
                readme_path = candidate
                break

        readme_content = ""
        if readme_path:
            try:
                readme_content = readme_path.read_text()[:4000]
            except Exception:
                pass

        skill_files = [
            str(p.relative_to(repo_path))
            for p in sorted(repo_path.rglob("SKILL.md"))
        ]

        dir_structure = "\n".join(
            f"  {'  ' * (len(p.relative_to(repo_path).parts) - 1)}{p.name}"
            for p in sorted(repo_path.iterdir())
            if not p.name.startswith(".")
        )

        prompt = AI_ANALYSIS_PROMPT.format(
            repo_path=str(repo_path),
            readme_content=readme_content,
            dir_structure=dir_structure,
            skill_files="\n".join(f"  - {s}" for s in skill_files[:30]),
        )

        response = self._call_llm(prompt)
        if not response:
            return None

        try:
            return AIAnalysis.from_llm_response(response)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Failed to parse LLM response: {e}")
            return None

    def _call_llm(self, prompt: str) -> str | None:
        """Call the configured LLM with a prompt.

        Uses the same LLM configuration as the routing engine (vibe config).
        Returns the text response or None if unavailable.
        """
        try:
            from vibesop.llm.factory import LLMFactory
            llm = LLMFactory.create(provider=self._llm_provider)
            return llm.complete(prompt)
        except Exception as e:
            logger.debug(f"LLM call failed: {e}")
            return None
```

- [ ] **Step 2: Integrate into `RepoAnalyzer.analyze()`**

In `src/vibesop/installer/analyzer.py`, after `_detect_layout()`:

```python
# If layout detection is uncertain (mixed), try AI analysis
if result.layout_type == "mixed":
    try:
        ai = AIAnalyzer()
        ai_result = ai.analyze(tmpdir_path)
        if ai_result and ai_result.confidence > 0.5:
            result.layout_type = ai_result.layout_type
            if ai_result.dependencies and not result.dependencies:
                result.dependencies = ai_result.dependencies
            result.post_install_hints.append(
                f"AI-inferred layout: {ai_result.layout_type} "
                f"(confidence: {ai_result.confidence:.0%})"
            )
    except Exception:
        pass  # AI analysis is best-effort
```

- [ ] **Step 3: Write tests**

```python
# tests/installer/test_ai_analyzer.py

import json
import pytest
from pathlib import Path
from vibesop.installer.ai_analyzer import AIAnalyzer, AIAnalysis


class TestAIAnalysis:
    def test_from_llm_response_valid(self):
        response = json.dumps({
            "layout_type": "nested",
            "skill_root": "skills",
            "dependencies": ["npm"],
            "setup_commands": ["npm install"],
            "confidence": 0.85,
            "notes": "Standard layout"
        })
        result = AIAnalysis.from_llm_response(response)
        assert result.layout_type == "nested"
        assert result.dependencies == ["npm"]
        assert result.confidence == 0.85

    def test_from_llm_response_malformed(self):
        with pytest.raises((json.JSONDecodeError, KeyError)):
            AIAnalysis.from_llm_response("not json")
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/installer/ai_analyzer.py src/vibesop/installer/analyzer.py tests/installer/test_ai_analyzer.py
git commit -m "feat(installer): AI-assisted layout detection for non-standard skill packs"
```

---

## Phase Summary

| Phase | Description | Files Changed | Priority |
|-------|-------------|---------------|----------|
| P1 | Fix symlink architecture (remove pack-level, build creates symlinks) | 7 files | **Must-do** |
| P2 | Dynamic skill discovery from central storage into routing | 3 files | **Must-do** |
| P3 | User-configurable security whitelist | 5 files | **Should-do** |
| P4 | LLM-assisted layout detection | 3 files | **Nice-to-have** |

**Total: ~18 files changed/created across 4 phases**

## Execution Order

1. **Phase 1 first** — Without this, the other phases build on a broken foundation
2. **Phase 2 second** — Enables `vibe install <arbitrary-url>` skills to be routed
3. **Phase 3 third** — Makes arbitrary URL installs safe by default
4. **Phase 4 last** — Quality of life for non-standard packs
