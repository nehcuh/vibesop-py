#!/bin/bash
# Type checking verification script for VibeSOP-Py
# Uses basedpyright — the project's type checker (see pyproject.toml [tool.pyright]
# and .github/workflows/ci.yml). Accepts exit 0 (clean) or 3 (warnings only),
# same as CI; fails on 1 (errors).

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

# Run type checking
echo "🔬 Running type checks on src/..."
echo

EXIT_CODE=0
uv run basedpyright || EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All type checks passed!"
    exit 0
elif [ $EXIT_CODE -eq 3 ]; then
    echo "✅ No type errors (warnings only — advisory, non-blocking)."
    exit 0
else
    echo "❌ Type checking failed!"
    echo
    echo "Please fix the type errors above before committing."
    exit 1
fi
