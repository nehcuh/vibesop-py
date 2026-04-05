#!/usr/bin/env python3
"""Sync skill registry from Ruby version.

This script copies the core YAML configuration from the Ruby vibesop
to the Python vibesop-py, ensuring both versions stay in sync.
"""

import os
import shutil
from pathlib import Path


def sync_registry() -> None:
    """Sync skill registry from Ruby version."""
    # Define source and destination paths (configurable via environment variables)
    ruby_project = Path(os.environ.get("VIBESOP_RUBY_PATH", "../vibesop"))
    python_project = Path(os.environ.get("VIBESOP_PYTHON_PATH", "."))

    # Files to sync
    files_to_sync = [
        ("core/skills/registry.yaml", "core/registry.yaml"),
        ("core/policies/skill-selection.yaml", "core/policies/skill-selection.yaml"),
    ]

    for src_rel, dst_rel in files_to_sync:
        src_path = ruby_project / src_rel
        dst_path = python_project / dst_rel

        if not src_path.exists():
            print(f"⚠️  Source file not found: {src_path}")
            continue

        # Create destination directory
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src_path, dst_path)
        print(f"✅ Synced: {src_rel} → {dst_rel}")

    print("\n✨ Registry sync complete!")


if __name__ == "__main__":
    sync_registry()
