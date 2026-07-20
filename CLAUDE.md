# Project Context

> **Project-level CLAUDE.md** — loaded by Grok Build (Claude compatibility)

System-wide routing, tool environment, and session lifecycle are defined in `~/.claude/CLAUDE.md` and the project `AGENTS.md`.

---

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (always use `uv` instead of `pip`)
- **Build System**: hatchling
- **CLI Framework**: Typer + Rich
- **Data Validation**: Pydantic v2
- **Config Parsing**: ruamel.yaml, PyYAML
- **Templating**: Jinja2
- **HTTP Client**: httpx
- **LLM Integration**: anthropic (Claude), openai (GPT/Kimi)
- **Testing**: pytest 9.x, pytest-cov, pytest-asyncio, pytest-mock, pytest-xdist
- **Linting**: ruff, basedpyright
- **Security**: bandit

---

## Architecture

VibeSOP is an **AI SkillOS** — a skill routing, orchestration, and lifecycle management system
for AI coding agents (Claude Code, Grok Build, Kimi Code, Pi, OpenCode, Cursor, etc.).

### Three-Layer Architecture

1. **Skill Discovery** — `core/skills/` contains builtin skills; external skills installed via `vibe install`
2. **Routing Engine** — semantic matching (`src/vibesop/core/`), hook-based interception (`src/vibesop/hooks/`)
3. **Platform Adapters** — generates agent-specific config (`src/vibesop/adapters/`): CLAUDE.md, AGENTS.md, JSON hooks, shell scripts

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/vibesop/core/` | Routing, classification, skill registry |
| `src/vibesop/cli/` | Typer CLI commands |
| `src/vibesop/adapters/` | Platform adapters (claude-code, grok-build, kimi-cli, pi, cursor, etc.) |
| `src/vibesop/installer/` | Skill installation and lifecycle |
| `src/vibesop/builder/` | Config generation and rendering |
| `src/vibesop/agent/` | In-process agent integration API |
| `src/vibesop/utils/` | Encoding, symlinks, Jinja safety |
| `core/skills/` | Builtin skills (shipped with wheel) |
| `core/policies/` | Policy definitions (YAML) |
| `tests/` | Test suite (mirrors src structure) |
| `docs/` | Architecture, ADRs, user/dev guides |
| `memory/` | Project knowledge, instincts, session state |
| `scripts/` | Bootstrap, verification, CI helpers |

---

## Coding Standards

- **Python 3.12+**: Use modern syntax (match/case, `X | None` unions, PEP 695 type params where appropriate)
- **Type annotations**: Strict mode; all public functions must have parameter and return types
- **Line length**: 100 characters (ruff)
- **Quotes**: Double quotes (ruff format)
- **Imports**: isort ordering, first-party = `vibesop`
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants
- **Public API**: All modules use `__all__` for explicit exports
- **Docstrings**: Google-style for public functions; internal helpers can be brief
- **Error handling**: Use custom exception hierarchy from `vibesop.core.exceptions`

## Testing

- **Run tests**: `uv run pytest`
- **Run with coverage**: `uv run pytest --cov=src/vibesop --cov-report=term`
- **Run specific file**: `uv run pytest tests/path/to/test_file.py`
- **Run with markers**: `uv run pytest -m "not benchmark and not slow"`
- **Lint**: `uv run ruff check src/ tests/`
- **Type check**: `uv run basedpyright src/`
- **Security audit**: `uv run bandit -c pyproject.toml -r src/`
- **CI**: GitHub Actions (`.github/workflows/ci.yml`) — Ubuntu + Windows, Python 3.12/3.13

Coverage gate: ≥ 73% (branch coverage).

## Build & Deploy

- **Install dev env**: `uv sync --extra dev`
- **Build wheel**: `uv build`
- **Install CLI**: `uv tool install .` (or `pipx install .`)
- **VibeSOP config**: `vibe build --platform grok-build` to deploy routing hooks

---

## Key Conventions

- **Never use `pip`** — always `uv`
- **Verify before claiming completion** — run tests, check output
- **Atomic changes** — small, reversible, single-purpose commits
- **Roadmap**: See `ROADMAP.md` and `docs/ROADMAP.md` for planned features
- **ADRs**: Architecture decisions in `docs/adr/`

---

*Project-level context — loaded after system-wide rules*
