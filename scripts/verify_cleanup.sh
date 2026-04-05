#!/bin/bash
# verify_cleanup.sh - Verify cleanup was successful

echo "🔍 Verifying Cleanup Results"
echo "============================="
echo ""

errors=0

# Check deleted files are gone
echo "1. Checking deleted files..."
if [ -f "src/vibesop/core/checkpoint/manager.py.bak" ]; then
    echo "   ❌ manager.py.bak still exists"
    errors=$((errors + 1))
else
    echo "   ✅ manager.py.bak removed"
fi

if [ -d ".vibe/.vibe" ]; then
    echo "   ❌ Nested .vibe directory still exists"
    errors=$((errors + 1))
else
    echo "   ✅ Nested .vibe directory removed"
fi

if [ -f "tests/hooks/test_installer.py" ]; then
    echo "   ❌ test_installer.py still exists"
    errors=$((errors + 1))
else
    echo "   ✅ test_installer.py removed"
fi

if [ -f "tests/cli/test_build.py" ]; then
    echo "   ❌ test_build.py still exists"
    errors=$((errors + 1))
else
    echo "   ✅ test_build.py removed"
fi

if [ -f "docs/DEEP_REVIEW_REPORT.md" ]; then
    echo "   ❌ DEEP_REVIEW_REPORT.md still exists"
    errors=$((errors + 1))
else
    echo "   ✅ DEEP_REVIEW_REPORT.md removed"
fi

if [ -f "run_external_tests.py" ]; then
    echo "   ❌ run_external_tests.py still exists"
    errors=$((errors + 1))
else
    echo "   ✅ run_external_tests.py removed"
fi

if [ -f "tests/workflow/test_models_unified.py" ]; then
    echo "   ❌ test_models_unified.py still exists"
    errors=$((errors + 1))
else
    echo "   ✅ test_models_unified.py removed"
fi

echo ""
echo "2. Checking test merge..."
if grep -q "TestStepResult" tests/workflow/test_models.py; then
    echo "   ✅ StepResult tests merged into test_models.py"
else
    echo "   ❌ StepResult tests not found in test_models.py"
    errors=$((errors + 1))
fi

if grep -q "TestClosureBugFix" tests/workflow/test_pipeline.py; then
    echo "   ✅ Closure bug tests moved to test_pipeline.py"
else
    echo "   ❌ Closure bug tests not found in test_pipeline.py"
    errors=$((errors + 1))
fi

echo ""
echo "============================="
if [ $errors -eq 0 ]; then
    echo "✅ All cleanup items verified!"
    exit 0
else
    echo "❌ $errors items need attention"
    exit 1
fi
