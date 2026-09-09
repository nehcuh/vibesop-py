#!/bin/bash
# Type checking verification script for VibeSOP-Py
# Uses basedpyright — the project's type checker (see pyproject.toml [tool.pyright]
# and .github/workflows/ci.yml). Mirrors the CI gate: basedpyright 1.39.9
# plain-text exit codes are 0 = success, 1 = type errors, 3 = configuration
# error (unrecognized setting, missing stubPath dir). ONLY exit 0 is a pass;
# `--level error` keeps rules configured as "warning" advisory/non-blocking
# while errors (1) and config errors (3) still fail.

set -e

echo "🔍 VibeSOP-Py Type Checking Verification"
echo "========================================"
echo

if ! uv run basedpyright --version &> /dev/null; then
    echo "❌ basedpyright not found in the project environment!"
    echo
    echo "Install dev dependencies:"
    echo "  uv sync --extra dev"
    exit 1
fi

echo "✅ Type checker found: basedpyright $(uv run basedpyright --version)"
echo

# Run type checking (same shape as the CI type-check job)
echo "🔬 Running type checks on src/..."
echo

uv run basedpyright --level error
EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All type checks passed!"
    exit 0
else
    echo "❌ Type checking failed (exit $EXIT_CODE — 1=type errors, 3=config error)."
    echo
    echo "Please fix the errors above before committing."
    exit 1
fi
