# External Tool Integration

> **Version**: 4.1.0
> **Last Updated**: 2026-04-18

## Overview

VibeSOP integrates with external AI tools and skill packages through a clean adapter pattern.

## Integration Model

```
┌─────────────────────────────────────────────────────────────┐
│                    VibeSOP Core                             │
│  (Routing, Discovery, Management)                           │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Adapter Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Claude Code  │  │  OpenCode    │  │ Future Tools │    │
│  │   Adapter    │  │   Adapter    │  │    Adapter   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌─────────┐     ┌──────────┐
│ Claude  │     │ Other    │
│  Code   │     │  Tools   │
└─────────┘     └──────────┘
```

## Platform Adapters

### Claude Code Adapter

**Location**: `src/vibesop/adapters/claude_code.py`

**Purpose**: Generate Claude Code compatible configuration

**Output**: `.claude/CLAUDE.md` with:
- Skill routing rules
- Behavior policies
- Documentation links

**Example**:
```python
from vibesop.adapters import ClaudeCodeAdapter

adapter = ClaudeCodeAdapter(
    project_root=".",
    config=config,
)
adapter.render(output_dir=".claude")
```

### OpenCode Adapter

**Location**: `src/vibesop/adapters/opencode.py`

**Purpose**: Generate OpenCode compatible configuration

**Output**: OpenCode-specific YAML configuration

## Skill Package Integration

### Supported Packages

| Package | Source | Skills Count | Status |
|---------|--------|--------------|--------|
| superpowers | github.com/obra/superpowers | 7 | ✅ Supported |
| gstack | github.com/gstack-skills/gstack | 19 | ✅ Supported |
| omx | Custom | 7 | ✅ Supported |

### Installation Flow

```
vibe install <package>
    │
    ▼
┌─────────────────────────────────────────────────┐
│ 1. SmartInstaller.detect()                      │
│    - Clone to temp                              │
│    - Analyze structure                          │
│    - Find SKILL.md files                        │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 2. SecurityScanner.audit()                      │
│    - Scan for threats                           │
│    - Validate paths                             │
│    - Check permissions                          │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 3. SkillStorage.install()                       │
│    - Copy to ~/.config/skills/<package>/        │
│    - Create symlinks                            │
│    - Update registry                            │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 4. AdapterFactory.render()                      │
│    - Generate platform config                  │
│    - Create CLAUDE.md                           │
│    - Setup aliases                              │
└─────────────────────────────────────────────────┘
```

### Custom Skill Packages

Any Git repository or local directory containing `SKILL.md` files can be installed:

```bash
# From Git
vibe install https://github.com/user/my-skills

# From local
vibe install ./path/to/skills

# Single file
vibe install https://example.com/skill.md
```

## Skill Package Format

### Directory Structure

```
my-skills/
├── README.md              # Package description
├── skills/
│   ├── my-skill/
│   │   └── SKILL.md       # Skill definition
│   └── another-skill/
│       └── SKILL.md
└── setup/                 # Optional setup scripts
    ├── install.sh
    └── package.json
```

### SKILL.md Format

```markdown
# My Skill

id: my-skill
name: My Skill
description: Does something useful
intent:
  - user says "do something"
  - user asks for help
version: 1.0.0

## Steps

1. Read the file
2. Analyze the content
3. Provide suggestions
```

## Health Monitoring

**Location**: `src/vibesop/integrations/health_monitor.py`

**Purpose**: Monitor installed skill packages

**Checks**:
- SKILL.md files present
- Required fields complete
- File integrity (encoding, size)
- Version consistency

**Usage**:
```bash
# 🚧 v4.2.0 计划实现
# vibe skills health
# Output:
# superpowers ✅ v1.2.0 (7 skills)
# gstack ✅ v2.0.1 (19 skills)
# omx ⚠️ v0.3.0 (2 skills missing)
```

## Platform-Specific Features

### Claude Code

**Exclusive Features**:
- `/` commands (e.g., `/review`)
- Rich panel output
- Tool integration

**Configuration**:
```yaml
# .claude/settings.json
{
  "skills": ["~/.claude/skills"],
  "rules": ["~/.claude/rules"]
}
```

### OpenCode

**Exclusive Features**:
- YAML-based config
- Plugin system
- Custom tool definitions

## Future Integrations

### Potential Platforms

| Platform | Status | Priority |
|----------|--------|----------|
| Cursor | Planned | P2 |
| Windsurf | Planned | P2 |
| Continue | Planned | P3 |

### Adding a New Platform

1. Create adapter in `src/vibesop/adapters/<platform>.py`
2. Implement `BaseAdapter` protocol
3. Add to `AdapterFactory`
4. Document platform-specific features

## Integration Best Practices

1. **Don't Execute, Only Route**: VibeSOP finds skills, doesn't run them
2. **Platform Agnostic**: Core logic independent of target platform
3. **Fail Gracefully**: Missing skills shouldn't break routing
4. **Security First**: Always audit external skills before installation

---

*For system overview, see [overview.md](overview.md)*
