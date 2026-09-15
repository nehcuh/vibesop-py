# VibeSOP

> **Engineering tools and empirical research for reliable AI-assisted development.**
>
> [中文](README.zh-CN.md) · [Documentation](docs/INDEX.md) · [Project status](docs/PROJECT_STATUS.md) · [Research](docs/research/README.md)

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/Version-8.4.1-blue.svg)](https://github.com/nehcuh/vibesop-py/releases/tag/v8.4.1)
[![PyPI](https://img.shields.io/pypi/v/vibesop.svg)](https://pypi.org/project/vibesop/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

VibeSOP is a **multi-agent AI engineering workflow** system. It routes requests
to the right skill or agent, verifies delivery against explicit criteria, and
records observable execution evidence. Around that core it provides skill
selection, governance over what may gate a release, and experience/knowledge
accumulation across AI coding agents. The repository also contains experiments on
when skills, specifications, orchestration, review, and memory improve the
work—and when they add overhead.

**SkillOS is the skill-management subsystem**, not the whole project. VibeSOP
also covers routing, verification, observability, governance, and
experience/knowledge accumulation. Reliability is the objective; the presence of
these tools does not establish an automatic or proven end-to-end software
factory. See the [project positioning](docs/POSITIONING.md).

## Version and availability

| Surface | State |
|---|---|
| Current source and package metadata | **8.4.1** |
| Previous public release | **8.4.0**, published 2026-09-14 |
| Commit / changelog references to 8.3.1 | Internal repair-batch labels; no 8.3.1 release exists |
| Skill format | SKILL.md v3.0; independent of the package version |
| Fixed-role committee v2 | Unfinished research; separate from the installed package |

The capabilities below describe this release. Local experiment data is not part
of the installed package. Details and release evidence: [project status](docs/PROJECT_STATUS.md).

## What you can do

| Need | Tools in the source tree | Boundary |
|---|---|---|
| Select and maintain skills | `vibe route`, skill installation, scopes, lifecycle management | No-match is a valid result; a skill need not be injected into every task |
| Plan work and check delivery | Execution plans, dependency tracking, verifier selection, blocked-plan handling | A generated plan or a model's approval is not proof of completion |
| Inspect what happened | Traces, replay, observability, machine acceptance records | Evidence must come from the execution being evaluated |
| Retrieve prior work | `vibe recall`, feedback, clustering and cross-project pools | Retrieval is implemented; continual improvement is not guaranteed |
| Run recurring work | `vibe loop` and scheduler integration | Behavior depends on the configured executor, schedule and environment |
| Evaluate an engineering method | Research reports, protocols, controlled runs and evidence manifests | Experimental branches and results are not automatically shipping features |

The hook path hands skill context to the host coding agent. Runtime, loop and
validation tools have their own execution paths. Platform configuration support,
hook support and end-to-end verification should be checked separately in the
[integration guide](docs/agent-integration.md).

## Quick start

Python **3.12+** is required. Install the public package with uv:

```sh
uv tool install vibesop
vibe --version
vibe quickstart
```

The routing demo uses a local lightweight path; LLM-enhanced routing requires a
configured provider. Review the selected skill and plan before relying on it.

To work from source:

```sh
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py
uv sync --extra dev
uv run vibe --version
uv run vibe quickstart
```

Inside a source checkout, use `uv run vibe` in place of `vibe` to avoid accidentally
invoking an older globally installed package.

## Integrations

Generate configuration for the agent you use, then restart that agent:

| Agent | Command |
|---|---|
| Claude Code | `vibe build claude-code --output ~/.claude` |
| Grok Build | `vibe build grok-build --output ~/.grok` |
| Kimi CLI | `vibe build kimi-cli --output ~/.kimi-code` |
| Pi | `vibe build pi --output .pi` |
| OpenCode | `vibe build opencode --output ~/.config/opencode` |
| Cursor | `vibe build cursor --output ~/.cursor` |

These are configuration-generation targets, not a claim of identical runtime
behavior across agents. Use `vibe doctor` and the platform-specific documentation
to check your environment.

## LLM configuration

For a CLI subprocess, configure a supported provider, for example:

```sh
export ANTHROPIC_API_KEY="your-key"
vibe route "help me debug this code"
```

An in-process integration can supply its host LLM through `AgentRouter.set_llm()`.
Provider options and platform-specific setup are in the
[configuration guide](docs/SKILL_LLM_CONFIG_GUIDE.md) and
[agent integration guide](docs/agent-integration.md).

## Workflow examples

```sh
vibe route "help me debug this code"
vibe plan list
vibe recall "configuration merge lost user hooks"
vibe loop list
vibe doctor
```

`recall` needs recorded traces and its embedding dependencies. Cross-project
retrieval is explicit (`--cross-project`) and requires a populated pool.
A blocked plan needs its reported problem resolved; it must not be treated as a
completed or ready-to-run task. See the
[verification contract](docs/architecture/verification-contract.md).

### Routing evidence (source candidate 8.5.0)

`vibe observe routing` reports no-match, near-miss, and decision-source
evidence from local route spans. It is report-only: it never edits the eval
dataset, thresholds, or routing policy. Generate a hermetic eval payload, then
observe spans against it:

```sh
# 1. Produce a fresh hermetic eval payload (near-miss over-injection evidence).
uv run python scripts/eval_routing.py --hermetic --json --json-out /tmp/eval-routing.json

# 2. Observe local route spans against it (reads .vibe/observability/spans.jsonl
#    by default; exit 4 means not enough scorable spans yet).
uv run vibe observe routing --eval-json /tmp/eval-routing.json --json
```

Spans come from real `vibe route` runs. See the
[operator runbook](docs/observe-routing.md) for metric definitions, thresholds,
exit codes, and cron/CI wrappers.

For commands and realistic scenarios, see the [CLI reference](docs/user/CLI_REFERENCE.md),
[command handbook](docs/user/COMMAND_HANDBOOK.md), and [use cases](docs/USE_CASES.en.md).

## Research and engineering principles

Our experiments ask how specifications, skills, models and execution environments
interact; whether more reviewers or fixed expert roles justify their cost; and
whether stored experience produces useful future behavior.

- [Research overview](docs/research/README.md): findings, source material and limitations.
- [Experiment registry](docs/experiments/README.md): settled cohorts and unfinished v2 research.
- [Research survey](docs/research/research-survey.md): the broader evidence record.
- [Engineering methodology](docs/enterprise-agent-methodology.md): proposed practices, with tested components distinguished from untested end-to-end hypotheses.
- [Article collection](docs/essays/README.md): explanations for a broader audience.

We select skills when useful, define acceptance criteria, retain failures and
interruptions, and separate model review from execution evidence. We do not infer
universal gains from more skills, more agents, or more stored traces. Dataset,
model, budget and measurement conditions belong beside each reported result.

Some raw runs live in a checksummed local archive and are **not included in a Git
clone or the wheel**. Experiment evidence manifests describe their locations and
restoration requirements. Research protocols and package releases have separate
version histories.

## Development

```sh
uv sync --extra dev
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run basedpyright --level error
uv run pytest
```

A documented test command is not a claim that the current checkout passed it.
Verification scope and dated evidence belong in the relevant change or report.

Start with the [architecture guide](docs/dev/architecture-overview.md),
[contribution guide](CONTRIBUTING.md), and [current roadmap](docs/ROADMAP.md).
The next release should reconcile source changes, migration notes and release
checks; a positioning update alone does not justify a new version.

## Documentation and project history

[All documentation](docs/INDEX.md) · [Project status](docs/PROJECT_STATUS.md) ·
[Design principles](docs/PHILOSOPHY.md) · [Changelog](CHANGELOG.md) ·
[Historical reviews](docs/archive/reviews/README.md) ·
[Workspace recovery](docs/maintenance/README.md)

## License and acknowledgments

[MIT](LICENSE). VibeSOP integrates with community skill ecosystems including
[superpowers](https://github.com/obra/superpowers),
[oh-my-codex](https://github.com/Yeachan-Heo/oh-my-codex), and other installable
packs. Skills and host agents retain their own authorship, licenses and runtime
requirements.

Report issues and discuss the project on [GitHub](https://github.com/nehcuh/vibesop-py).
