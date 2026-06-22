"""Project initialization support."""

from datetime import datetime
from pathlib import Path
from typing import Any


class InitSupport:
    """Creates .vibe directory structure and default configuration files."""

    def __init__(self) -> None:
        self._vibe_dir = Path(".vibe")
        self._config_file = self._vibe_dir / "config.toml"

    def init_project(
        self,
        project_path: Path,
        platform: str = "claude-code",
        force: bool = False,
        create_skills_dir: bool = True,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
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

            vibe_dir = project_path / self._vibe_dir
            if vibe_dir.exists() and not force:
                result["warnings"].append(f"Project already initialized at {vibe_dir}")
                result["success"] = True
                return result

            dirs_to_create = [
                self._vibe_dir,
                self._vibe_dir / "skills",
                self._vibe_dir / "core",
                self._vibe_dir / "memory",
            ]

            if create_skills_dir:
                dirs_to_create.append(project_path / ".skills")

            for dir_path in dirs_to_create:
                full_path = project_path / dir_path
                full_path.mkdir(parents=True, exist_ok=True)
                result["created_dirs"].append(str(full_path))

            config_content = self._generate_default_config(platform)
            config_file = project_path / self._config_file
            config_file.write_text(config_content)
            result["created_files"].append(str(config_file))

            _ensure_global_config(platform, result)

            from vibesop.core.routing.project_config import create_default_project_routing

            routing_file = create_default_project_routing(project_path)
            if routing_file:
                result["created_files"].append(str(routing_file))

            self._update_gitignore(project_path)

            readme_content = self._generate_readme(platform)
            readme_file = project_path / self._vibe_dir / "README.md"
            readme_file.write_text(readme_content)
            result["created_files"].append(str(readme_file))

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Initialization failed: {e}")

        return result

    def verify_init(self, project_path: Path) -> dict[str, Any]:
        project_path = project_path.expanduser().resolve()
        vibe_dir = project_path / self._vibe_dir

        vibe_dir_exists = vibe_dir.exists()
        config_exists = (vibe_dir / "config.toml").exists() or (vibe_dir / "config.yaml").exists()
        skills_dir_exists = (vibe_dir / "skills").exists()
        initialized = vibe_dir_exists and config_exists and skills_dir_exists

        return {
            "initialized": initialized,
            "vibe_dir_exists": vibe_dir_exists,
            "config_exists": config_exists,
            "skills_dir_exists": skills_dir_exists,
            "structure_valid": initialized,
        }

    def _generate_default_config(self, platform: str) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        return f"""# VibeSOP Project Configuration
# Generated for: {platform}
# Date: {date_str}

platform = "{platform}"

# ─────────────────────────────────────────────────────
# LLM Configuration (required for AI triage and orchestration)
# VibeSOP runs as a CLI subprocess and cannot reuse the host AI Agent's LLM.
# Choose one provider below.
# ─────────────────────────────────────────────────────
[llm]
# Provider: ollama | anthropic | openai | deepseek | kimi | zhipu
provider = "ollama"

# Model name (defaults shown below per provider)
# Ollama: Qwen3.6-35B-A3B-mlx-mxfp8
# Anthropic: claude-3-5-haiku-20241022
# OpenAI: gpt-4o-mini
# DeepSeek: deepseek-v4-flash
# Kimi: moonshot-v1-8k
# Zhipu: glm-4
model = "Qwen3.6-35B-A3B-mlx-mxfp8"

# API key (required for cloud providers, ignored for Ollama)
# For Ollama: leave empty (uses local dummy key)
# For Anthropic: sk-ant-...
# For OpenAI: sk-...
# For DeepSeek: sk-...
# Tip: set ANTHROPIC_API_KEY / OPENAI_API_KEY env var instead
api_key = ""

# Custom API base URL (for self-hosted or proxies)
# Ollama default: http://localhost:11434/v1
api_base = ""

temperature = 0.7
max_tokens = 4096

# Routing configuration
[routing]
confirmation_mode = "always"  # always | never | ambiguous_only
enable_ai_triage = true
enable_orchestration = true
enable_embedding = false
max_candidates = 3
use_cache = true
keyword_match_max_chars = 15
session_aware = true
default_strategy = "auto"  # auto | sequential | parallel | hybrid

# Degradation: confidence-gated layered fallback
degradation_enabled = true
degradation_auto_threshold = 0.6
degradation_suggest_threshold = 0.4
degradation_degrade_threshold = 0.2
degradation_fallback_always_ask = true

# Security configuration
[security]
scan_external = true

# Memory configuration
[memory]
enabled = true
autoload = true

# Preference learning
[preferences]
enabled = true
learning_rate = 0.1
"""

    def _generate_readme(self, platform: str) -> str:
        from vibesop._version import __version__

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

*Generated by VibeSOP {__version__}*
"""

    def _update_gitignore(self, project_path: Path) -> None:
        gitignore_path = project_path / ".gitignore"
        vibe_entries = ["# VibeSOP", ".vibe/", ".skills/"]

        if gitignore_path.exists():
            content = gitignore_path.read_text()
            if ".vibe/" not in content:
                with gitignore_path.open("a") as f:
                    f.write("\n" + "\n".join(vibe_entries) + "\n")
        else:
            gitignore_path.write_text("\n".join(vibe_entries) + "\n")


def _ensure_global_config(platform: str, result: dict[str, Any]) -> None:
    """Ensure global ~/.vibe/config.toml exists with full default template."""
    global_config_dir = Path.home() / ".vibe"
    global_config_file = global_config_dir / "config.toml"

    if (global_config_dir / "config.yaml").exists() or global_config_file.exists():
        return

    global_config_dir.mkdir(parents=True, exist_ok=True)
    global_config_file.write_text(_generate_global_config_template(platform))
    result["created_files"].append(str(global_config_file))


def _generate_global_config_template(platform: str) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"""# ───────────────────────────────────────────
# VibeSOP Global Configuration
# Location: ~/.vibe/config.toml
# Applies to all projects unless overridden in .vibe/config.toml
# Generated: {date_str}
# ───────────────────────────────────────────

# Default platform for CLI operations
default_platform = "{platform}"

# ─────────────────────────────────────────────────────
# LLM Configuration (REQUIRED for AI triage & orchestration)
#
# VibeSOP runs as a CLI subprocess and CANNOT reuse the host
# AI Agent's internal LLM (e.g., Claude Code's session model).
# You MUST configure a separate provider below.
#
# Priority order (auto-detect if provider is unset):
#   1. VIBE_LLM_PROVIDER env var  (explicit override)
#   2. Ollama (local, zero-cost)
#   3. DeepSeek
#   4. OpenAI
#   5. Anthropic
# ─────────────────────────────────────────────────────
[llm]
# Provider
# Options: ollama | anthropic | openai | deepseek | kimi | zhipu
# Default: ollama (local, no API key needed)
provider = "ollama"

# Model
# Ollama default:  Qwen3.6-35B-A3B-mlx-mxfp8
# Anthropic fast:  claude-3-5-haiku-20241022
# Anthropic smart: claude-sonnet-4-6-20250514
# OpenAI cheap:    gpt-4o-mini
# DeepSeek:        deepseek-v4-flash
model = "Qwen3.6-35B-A3B-mlx-mxfp8"

# API Key
# Ollama:        leave empty (uses local dummy key)
# Anthropic:     sk-ant-...
# OpenAI:        sk-...
# DeepSeek:      sk-...
# Tip: set ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY env var instead
api_key = ""

# API Base URL (for self-hosted, proxies, or non-standard ports)
# Ollama default:    http://localhost:11434/v1
# DeepSeek default:  https://api.deepseek.com
# Kimi default:      https://api.moonshot.cn/v1
# Zhipu default:     https://open.bigmodel.cn/api/paas/v4
api_base = ""

# Generation parameters
temperature = 0.7
max_tokens = 4096

# ─────────────────────────────────────────────────────
# Routing Configuration
# ─────────────────────────────────────────────────────
[routing]
# User confirmation before selecting a skill
#   "always"          - ask for confirmation every time (default)
#   "never"           - skip confirmation, auto-select
#   "ambiguous_only"  - ask only when multiple close candidates
confirmation_mode = "always"

# AI-powered semantic triage (Layer 2 of 10-layer pipeline)
# Disable if no LLM configured or you want keyword-only routing
enable_ai_triage = true

# Multi-intent detection and task decomposition
enable_orchestration = true

# Vector embedding-based semantic matching (Layer 5)
# Requires sentence-transformers (pip install vibesop[semantic])
enable_embedding = false

# Maximum candidate skills to return
max_candidates = 3

# Cache routing results for repeated queries
use_cache = true

# Maximum query length (chars) for keyword-only routing
# Queries shorter than this skip LLM triage
keyword_match_max_chars = 15

# Session-aware routing: remembers current skill context
# Disable for lower overhead or privacy concerns
session_aware = true

# Default orchestration strategy for multi-intent queries
#   "auto" | "sequential" | "parallel" | "hybrid"
default_strategy = "auto"

# ── Confidence-Gated Degradation (v5.2.0) ──
# Avoids binary match/no-match. Instead:
#   >= 0.6 → AUTO (auto-select)
#   >= 0.4 → SUGGEST (show with alternatives)
#   >= 0.2 → DEGRADE (use but warn)
#   < 0.2  → FALLBACK (raw LLM, no skill)
degradation_enabled = true
degradation_auto_threshold = 0.6
degradation_suggest_threshold = 0.4
degradation_degrade_threshold = 0.2
degradation_fallback_always_ask = true

# Routing transparency: show full decision tree
#   "full" | "compact"
transparency = "full"

# ─────────────────────────────────────────────────────
# Security Configuration
# ─────────────────────────────────────────────────────
[security]
# Scan external skills for threats before loading
scan_external = true

# ─────────────────────────────────────────────────────
# Preference Learning
# ─────────────────────────────────────────────────────
[preferences]
# Learn from your routing choices to improve accuracy
learning_enabled = true
"""
