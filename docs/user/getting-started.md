# Getting Started with VibeSOP

## Prerequisites

- Python 3.12 or higher
- `uv` package manager (recommended) or `pip`

## Installation

### Option 1: Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install dependencies
uv sync

# Verify installation
uv run vibe --help
```

### Option 2: Using pip

```bash
# Basic installation (no semantic matching)
pip install vibesop

# With semantic matching
pip install vibesop[semantic]

# With development dependencies
pip install -e "vibesop[dev]"
```

## Quick Start

```bash
# Check your environment
vibe doctor

# List available skills
vibe skills

# Route a query
vibe route "review my code"

# Auto-detect and execute
vibe auto "scan for security issues"
```

## Next Steps

- [CLI Reference](../user/cli-reference.md) — Complete command reference
- [Semantic Matching Guide](../semantic/guide.md) — Enable semantic recognition
- [Workflow Orchestration](workflows.md) — Multi-stage workflows
