---
id: omx/team
name: Team
description: Multi-agent parallel execution with Python asyncio runtime and file-based coordination.
intent: parallel execution
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to run multiple tasks in parallel with a team of agents
---

# Team — Multi-Agent Parallel Execution

Coordinate multiple agents working in parallel with file-based messaging.

## Pre-context Gate

1. Verify work is decomposable into independent tasks
2. If tasks are interdependent, use ralph instead
3. Load `.vibe/context/` snapshot

## Start Team

1. Parse arguments: team name, task list
2. Initialize state in `.vibe/state/team/{team-name}/`
3. Create mailbox directory: `.vibe/state/team/{team-name}/mailbox/`
4. Launch workers via Python asyncio (not tmux)

## Worker Protocol

Each worker:
1. Reads their task from the task queue
2. Works independently on their assignment
3. Writes results to `.vibe/state/team/{team-name}/workers/{worker-id}/result.json`
4. Signals completion by writing to their mailbox slot

## Monitor Loop

- Check worker status every 30 seconds
- Auto-nudge stalled workers (no progress for 5+ minutes)
- Report progress: completed/total/failed

## Shutdown

1. Wait for all workers to complete
2. Verify evidence: each worker's output is valid
3. Aggregate results into team report
4. Cleanup temporary files
5. Save final state

## State Structure

```
.vibe/state/team/{team-name}/
├── config.json          # Team configuration
├── mailbox/             # Worker communication
│   ├── worker-1.json
│   └── worker-2.json
└── workers/             # Worker results
    ├── worker-1/
    │   └── result.json
    └── worker-2/
        └── result.json
```
