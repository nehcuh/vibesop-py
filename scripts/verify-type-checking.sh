#!/bin/bash
# Type checking verification script for VibeSOP-Py

set -e

echo "🔍 VibeSOP-Py Type Checking Verification"
echo "========================================"
echo

# Check if type checker is installed
if command -v pyright &> /dev/null; then
    TYPE_CHECKER="pyright"
elif command -v mypy &> /dev/null; then
    TYPE_CHECKER="mypy"
else
    echo "❌ No type checker found!"
    echo
    echo "Please install one of the following:"
    echo "  - Pyright: npm install -g pyright"
    echo "  - BasedPyright: pip install basedpyright"
    echo "  - MyPy: pip install mypy"
    echo
    echo "Or install all dev dependencies:"
    echo "  pip install -e '.[dev]'"
    exit 1
fi

echo "✅ Type checker found: $TYPE_CHECKER"
echo

# Run type checking
echo "🔬 Running type checks on src/vibesop..."
echo

if [ "$TYPE_CHECKER" = "pyright" ]; then
    pyright src/vibesop
    EXIT_CODE=$?
elif [ "$TYPE_CHECKER" = "mypy" ]; then
    mypy src/vibesop
    EXIT_CODE=$?
fi

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All type checks passed!"
    echo
    echo "Type checking verification complete."
    exit 0
else
    echo "❌ Type checking failed!"
    echo
    echo "Please fix the type errors above before committing."
    exit 1
fi
