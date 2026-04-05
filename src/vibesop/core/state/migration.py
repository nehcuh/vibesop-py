"""Migration utilities for existing .vibe/ data."""

import json
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
    report: dict[str, Any] = {
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    if not vibe_root.exists():
        report["details"].append("No .vibe/ directory found, nothing to migrate")
        return report

    state_manager = StateManager(state_root=vibe_root / "state")

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

    memory_dir = vibe_root / "memory"
    if memory_dir.exists():
        for memory_file in memory_dir.glob("*.json"):
            try:
                with memory_file.open("r") as f:
                    data = json.load(f)
                scope = memory_file.stem
                if dry_run:
                    report["details"].append(
                        f"Would migrate: {memory_file} → state/sessions/{scope}"
                    )
                    report["migrated"] += 1
                else:
                    state_manager.write(
                        "sessions",
                        scope,
                        {
                            "source": "migrated_from_memory",
                            "original_file": str(memory_file),
                            **data,
                        },
                    )
                    report["migrated"] += 1
                    report["details"].append(f"Migrated: {memory_file} → state/sessions/{scope}")
            except Exception as e:
                report["errors"] += 1
                report["details"].append(f"Error migrating {memory_file}: {e}")
    else:
        report["details"].append("No memory/ directory found, skipping")
        report["skipped"] += 1

    return report
