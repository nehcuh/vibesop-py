# Workflow Orchestration

VibeSOP v2.0+ supports multi-stage workflow execution with dependency management.

## Running a Workflow

```bash
# Run a workflow from YAML file
vibe workflow run my-workflow.yaml

# List available workflows
vibe workflow list

# Resume an interrupted workflow
vibe workflow resume <workflow-id>

# Validate a workflow definition
vibe workflow validate my-workflow.yaml
```

## Workflow Definition

Workflows are defined in YAML format:

```yaml
name: my-workflow
strategy: sequential  # sequential, parallel, or pipeline

stages:
  - id: validate
    name: Validate Input
    handler: validate_handler
    depends_on: []

  - id: process
    name: Process Data
    handler: process_handler
    depends_on: [validate]

  - id: report
    name: Generate Report
    handler: report_handler
    depends_on: [process]
```

## Execution Strategies

- **Sequential**: Stage-by-stage execution (default)
- **Parallel**: Concurrent stage execution where dependencies allow
- **Pipeline**: Adaptive streaming with progress callbacks

## State Management

Workflow state is persisted to `.vibe/state/workflows/` and can be resumed after interruption.
