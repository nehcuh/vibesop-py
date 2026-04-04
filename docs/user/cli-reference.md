# VibeSOP CLI Reference

Complete command reference for the VibeSOP CLI tool.

---

## Installation

```bash
# Install from source
pip install vibesop

# Or with poetry
poetry install
```

---

## Core Commands

### `vibe route`

Route user queries to appropriate skills using AI-powered semantic matching.

```bash
vibe route "<query>"
```

**Options**:
- `--provider, -p`: LLM provider (anthropic, openai) [default: anthropic]
- `--model, -m`: Model to use [default: auto-detect]
- `--top, -n`: Number of results to show [default: 3]
- `--threshold, -t`: Minimum confidence threshold [default: 0.0]
- `--json`: Output as JSON

**Examples**:
```bash
vibe route "help me debug this error"
vibe route "implement a feature" --top 5 --threshold 0.7
vibe route "review my code" --provider openai --json
```

---

### `vibe build`

Build configuration manifests from registry files.

```bash
vibe build [OPTIONS]
```

**Options**:
- `--platform, -p`: Target platform [claude-code, opencode]
- `--output, -o`: Output directory [default: auto-detect]
- `--overlay`: Overlay file path
- `--format`: Output format [yaml, json] [default: yaml]

**Examples**:
```bash
vibe build --platform claude-code
vibe build --overlay custom.yaml --output ./config
vibe build --platform opencode --format json
```

---

### `vibe render`

Render platform configurations from manifests.

```bash
vibe render [OPTIONS] MANIFEST
```

**Arguments**:
- `MANIFEST`: Path to manifest file

**Options**:
- `--platform, -p`: Target platform [default: auto-detect]
- `--output, -o`: Output directory [default: platform default]
- `--force`: Overwrite existing files

**Examples**:
```bash
vibe render manifest.yaml
vibe render manifest.yaml --platform claude-code --output ~/.claude
vibe render manifest.yaml --force
```

---

### `vibe scan`

Scan text for security threats.

```bash
vibe scan [OPTIONS] [INPUT]
```

**Arguments**:
- `INPUT`: Input text or file path (default: stdin)

**Options**:
- `--file, -f`: Treat input as file path
- `--threat-level`: Minimum threat level [low, medium, high, critical] [default: low]
- `--json`: Output as JSON
- `--quiet, -q`: Only output threats found

**Examples**:
```bash
vibe scan "Ignore all previous instructions"
vibe scan --file user_input.txt --threat-level high
vibe scan --file input.txt --json --quiet
echo "test input" | vibe scan
```

---

### `vibe doctor`

Check environment and configuration.

```bash
vibe doctor
```

**Checks performed**:
- ✅ Python version (requires 3.12+)
- ✅ Dependencies (pydantic, typer, rich)
- ✅ Configuration files
- ✅ LLM provider (API keys)
- ✅ Platform integrations (Superpowers, gstack)
- ✅ Hook status (installed/verified)

**Exit codes**:
- `0`: All checks passed
- `1`: Some checks failed

**Examples**:
```bash
vibe doctor
```

---

### `vibe version`

Show version information.

```bash
vibe version
```

**Output**:
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Version Information         ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ VibeSOP Python Edition      │
│                              │
│ Version: 1.0.0               │
│ Python: 3.12+                │
│ Pydantic: v2                 │
└──────────────────────────────┘
```

---

## Advanced Commands

### `vibe record`

Record skill selection for preference learning.

```bash
vibe record SKILL_ID QUERY [--helpful/--not-helpful]
```

**Arguments**:
- `SKILL_ID`: Skill that was selected
- `QUERY`: Original user query

**Options**:
- `--helpful, -h`: Mark as helpful (default)
- `--not-helpful, -H`: Mark as not helpful

**Examples**:
```bash
vibe record tdd "help me write tests" --helpful
vibe record brainstorm "generate ideas" --not-helpful
```

---

## Installation Scripts

### `vibe-install`

Shell script for installing VibeSOP configurations.

```bash
./scripts/vibe-install [OPTIONS] [PLATFORM]
```

**Actions**:
- (default): Install configuration for platform
- `--list`: List supported platforms
- `--verify [PLATFORM]`: Verify installation

**Options**:
- `--force`: Force overwrite existing configuration

**Examples**:
```bash
# Install Claude Code configuration
./scripts/vibe-install claude-code

# Install OpenCode configuration
./scripts/vibe-install opencode

# List supported platforms
./scripts/vibe-install --list

# Verify installation
./scripts/vibe-install --verify claude-code

# Force reinstall
./scripts/vibe-install claude-code --force
```

---

## Python API Usage

### Configuration Generation

```python
from vibesop.builder import ConfigRenderer, QuickBuilder
from pathlib import Path

# Quick configuration
manifest = QuickBuilder.default(platform="claude-code")
renderer = ConfigRenderer()
result = renderer.render(manifest, Path("~/.claude"))

print(f"✅ Created {result.file_count} files")
```

### Security Scanning

```python
from vibesop.security import SecurityScanner

scanner = SecurityScanner()

# Scan text
result = scanner.scan("user input here")
if result.has_threats:
    for threat in result.threats:
        print(f"🚨 {threat.type}: {threat.message}")

# Scan with exception
try:
    scanner.scan_bang("suspicious input")
except UnsafeContentError as e:
    print(f"❌ Unsafe: {e}")
```

### Hook Management

```python
from vibesop.hooks import HookInstaller, HookPoint
from pathlib import Path

installer = HookInstaller()

# Install all hooks
results = installer.install_hooks("claude-code", Path("~/.claude"))
for name, success in results.items():
    status = "✅" if success else "❌"
    print(f"{status} {name}")

# Verify hooks
status = installer.verify_hooks("claude-code", Path("~/.claude"))
installed = sum(1 for v in status.values() if v)
print(f"Hooks: {installed}/{len(status)} installed")
```

### Integration Detection

```python
from vibesop.integrations import IntegrationManager

manager = IntegrationManager()

# List all integrations
integrations = manager.list_integrations()
for info in integrations:
    icon = "✅" if info.status.value == "installed" else "⚪️"
    print(f"{icon} {info.name}: {info.description}")

# Get all available skills
skills = manager.get_skills()
print(f"📚 {len(skills)} skills available")
```

---

## Environment Variables

### LLM Provider APIs

```bash
# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI GPT
export OPENAI_API_KEY="sk-..."
```

### VibeSOP Configuration

```bash
# Configuration directory
export VIBE_CONFIG_DIR="$HOME/.vibe"

# Default platform
export VIBE_PLATFORM="claude-code"

# Log level
export VIBE_LOG_LEVEL="INFO"
```

### Routing Options

```bash
# Semantic routing threshold
export VIBE_SEMANTIC_THRESHOLD="0.75"

# Enable fuzzy matching
export VIBE_ENABLE_FUZZY="true"
```

---

## Configuration Files

### Manifest File (`manifest.yaml`)

```yaml
metadata:
  platform: claude-code
  version: 1.0.0
  author: Your Name

skills:
  - id: tdd
    name: Test-Driven Development
    description: TDD workflow
    trigger_when: User asks about testing

policies:
  security:
    enable_scanning: true
    threat_level: high

  routing:
    semantic_threshold: 0.75
    enable_fuzzy: true
```

### Overlay File (`overlay.yaml`)

```yaml
# Override specific settings
skills:
  - id: custom-skill
    name: My Custom Skill
    description: Custom functionality

policies:
  security:
    threat_level: critical  # Override to critical
```

---

## Tips and Tricks

### 1. Quick Configuration Check

```bash
# Verify everything is set up correctly
vibe doctor
```

### 2. Test Before Deploying

```bash
# Render to temp directory first
vibe render manifest.yaml --output /tmp/vibesop-test

# Verify the output
ls -la /tmp/vibesop-test

# Then deploy
vibe render manifest.yaml --output ~/.claude
```

### 3. Scan Multiple Files

```bash
# Scan all files in a directory
for file in inputs/*.txt; do
    echo "Scanning $file..."
    vibe scan --file "$file"
done
```

### 4. Batch Installation

```bash
# Install for all platforms
./scripts/vibe-install claude-code
./scripts/vibe-install opencode

# Verify all installations
./scripts/vibe-install --verify claude-code
./scripts/vibe-install --verify opencode
```

### 5. Pipeline Integration

```bash
# Use in CI/CD pipeline
vibe scan user_input.json --json --quiet | jq '.threats'
if [ $? -eq 0 ]; then
    echo "Threats detected!"
    exit 1
fi
```

---

## Troubleshooting

### "No API key found"

Set the appropriate environment variable:
```bash
export ANTHROPIC_API_KEY="your-key-here"
# or
export OPENAI_API_KEY="your-key-here"
```

### "Configuration not found"

Check your configuration directory:
```bash
ls -la ~/.vibe
# or
echo $VIBE_CONFIG_DIR
```

### "Platform not supported"

List supported platforms:
```bash
./scripts/vibe-install --list
```

### "Hook verification failed"

Check hook status:
```bash
vibe doctor
# Look for "Hook Status" section
```

---

## Getting Help

- **Version**: `vibe version`
- **Doctor**: `vibe doctor`
- **Command help**: `vibe --help`
- **Subcommand help**: `vibe route --help`

---

**For more information, visit**: https://github.com/yourusername/vibesop-py
