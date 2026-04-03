"""Project initialization support.

This module provides functionality for initializing new projects
with VibeSOP configuration.
"""

import shutil
from pathlib import Path
from typing import Dict, List, Optional


class InitSupport:
    """Support for project initialization.

    Creates .vibe directory structure and default
    configuration files for new projects.

    Example:
        >>> init_support = InitSupport()
        >>> result = init_support.init_project(
        ...     project_path=Path("."),
        ...     platform="claude-code"
        ... )
    """

    def __init__(self) -> None:
        """Initialize init support."""
        self._vibe_dir = Path(".vibe")
        self._config_file = self._vibe_dir / "config.yaml"

    def init_project(
        self,
        project_path: Path,
        platform: str = "claude-code",
        force: bool = False,
        create_skills_dir: bool = True,
    ) -> Dict[str, any]:
        """Initialize a project with VibeSOP configuration.

        Args:
            project_path: Path to project root
            platform: Target platform
            force: Force overwrite if already initialized
            create_skills_dir: Whether to create skills directory

        Returns:
            Dictionary with initialization results
        """
        result = {
            "success": False,
            "project_path": str(project_path),
            "platform": platform,
            "created_dirs": [],
            "created_files": [],
            "errors": [],
            "warnings": [],
        }

        try:
            project_path = project_path.expanduser().resolve()

            # Check if already initialized
            vibe_dir = project_path / self._vibe_dir
            if vibe_dir.exists() and not force:
                result["warnings"].append(f"Project already initialized at {vibe_dir}")
                result["success"] = True
                return result

            # Create .vibe directory structure
            dirs_to_create = [
                self._vibe_dir,
                self._vibe_dir / "skills",
                self._vibe_dir / "core",
                self._vibe_dir / "memory",
            ]

            if create_skills_dir:
                dirs_to_create.append(
                    project_path / ".skills"
                )

            for dir_path in dirs_to_create:
                full_path = project_path / dir_path
                full_path.mkdir(parents=True, exist_ok=True)
                result["created_dirs"].append(str(full_path))

            # Create default config file
            config_content = self._generate_default_config(platform)
            config_file = project_path / self._config_file
            config_file.write_text(config_content)
            result["created_files"].append(str(config_file))

            # Create .gitignore entries
            self._update_gitignore(project_path)

            # Create README
            readme_content = self._generate_readme(platform)
            readme_file = project_path / self._vibe_dir / "README.md"
            readme_file.write_text(readme_content)
            result["created_files"].append(str(readme_file))

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Initialization failed: {e}")

        return result

    def verify_init(self, project_path: Path) -> Dict[str, any]:
        """Verify project initialization.

        Args:
            project_path: Path to project root

        Returns:
            Dictionary with verification results
        """
        result = {
            "initialized": False,
            "vibe_dir_exists": False,
            "config_exists": False,
            "skills_dir_exists": False,
            "structure_valid": False,
        }

        project_path = project_path.expanduser().resolve()
        vibe_dir = project_path / self._vibe_dir

        result["vibe_dir_exists"] = vibe_dir.exists()
        result["config_exists"] = (vibe_dir / "config.yaml").exists()
        result["skills_dir_exists"] = (vibe_dir / "skills").exists()

        result["initialized"] = (
            result["vibe_dir_exists"]
            and result["config_exists"]
            and result["skills_dir_exists"]
        )

        result["structure_valid"] = result["initialized"]

        return result

    def _generate_default_config(self, platform: str) -> str:
        """Generate default configuration content.

        Args:
            platform: Target platform

        Returns:
            Configuration YAML content
        """
        return f"""# VibeSOP Project Configuration
# Generated for: {platform}
# Date: {self._get_current_date()}

platform: {platform}

# Routing configuration
routing:
  semantic_threshold: 0.75
  enable_fuzzy: true
  cache_enabled: true

# Security configuration
security:
  enable_scanning: true
  threat_level: high

# Memory configuration
memory:
  enabled: true
  autoload: true

# Preference learning
preferences:
  enabled: true
  learning_rate: 0.1
"""

    def _generate_readme(self, platform: str) -> str:
        """Generate README content.

        Args:
            platform: Target platform

        Returns:
            README markdown content
        """
        return f"""# VibeSOP Configuration

This directory contains VibeSOP configuration for the **{platform}** platform.

## Directory Structure

- `config.yaml` - Main configuration file
- `skills/` - Project-specific skills
- `core/` - Core configuration from registry
- `memory/` - Session memory storage

## Quick Start

1. Install VibeSOP: `pip install vibesop`
2. Initialize platform: `vibe init {platform}`
3. Generate configuration: `vibe build`

## Documentation

For more information, see:
- [VibeSOP Documentation](https://github.com/nehcuh/vibesop-py)
- [CLI Reference](docs/CLI_REFERENCE.md)

---

*Generated by VibeSOP v1.0.0*
"""

    def _update_gitignore(self, project_path: Path) -> None:
        """Update .gitignore with VibeSOP entries.

        Args:
            project_path: Path to project root
        """
        gitignore_path = project_path / ".gitignore"

        # Entries to add
        vibe_entries = [
            "# VibeSOP",
            ".vibe/",
            ".skills/",
        ]

        if gitignore_path.exists():
            content = gitignore_path.read_text()
            # Check if entries already exist
            if ".vibe/" not in content:
                with open(gitignore_path, "a") as f:
                    f.write("\n" + "\n".join(vibe_entries) + "\n")
        else:
            # Create new .gitignore
            gitignore_path.write_text("\n".join(vibe_entries) + "\n")

    def _get_current_date(self) -> str:
        """Get current date as ISO string.

        Returns:
            ISO format date string
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")
