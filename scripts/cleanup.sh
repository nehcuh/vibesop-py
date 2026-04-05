#!/bin/bash
# cleanup.sh - Clean up redundant files in VibeSOP project
# Run this from project root: ./scripts/cleanup.sh

set -e

echo "🔍 VibeSOP Project Cleanup"
echo "=========================="
echo ""

# Count files before cleanup
echo "📊 Before cleanup:"
echo "  Total files: $(find . -type f | wc -l | tr -d ' ')"
echo "  Python files: $(find . -name '*.py' -type f | wc -l | tr -d ' ')"
echo "  Markdown files: $(find . -name '*.md' -type f | wc -l | tr -d ' ')"
echo ""

# 1. Remove backup files
echo "🗑️  Step 1: Removing backup files..."
if [ -f "src/vibesop/core/checkpoint/manager.py.bak" ]; then
    rm -f src/vibesop/core/checkpoint/manager.py.bak
    echo "  ✓ Removed manager.py.bak"
else
    echo "  ℹ️  No backup files found"
fi

# 2. Remove nested .vibe directory
echo ""
echo "🗑️  Step 2: Removing nested .vibe directory..."
if [ -d ".vibe/.vibe" ]; then
    rm -rf .vibe/.vibe/
    echo "  ✓ Removed .vibe/.vibe/"
else
    echo "  ℹ️  No nested directory found"
fi

# 3. Remove redundant test file
echo ""
echo "🗑️  Step 3: Removing redundant test file..."
if [ -f "tests/hooks/test_installer.py" ]; then
    rm -f tests/hooks/test_installer.py
    echo "  ✓ Removed tests/hooks/test_installer.py"
else
    echo "  ℹ️  File already removed"
fi

# 4. Clean Python cache
echo ""
echo "🧹 Step 4: Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo "  ✓ Cleaned Python cache files"

# 5. Clean test cache
echo ""
echo "🧹 Step 5: Cleaning test cache..."
rm -rf .pytest_cache/ 2>/dev/null || true
echo "  ✓ Cleaned test cache"

# 6. Optional: Remove redundant documentation
echo ""
echo "🗑️  Step 6: Checking redundant documentation..."
if [ -f "docs/DEEP_REVIEW_REPORT.md" ]; then
    echo "  Found docs/DEEP_REVIEW_REPORT.md (superseded by V2)"
    read -p "  Delete it? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f docs/DEEP_REVIEW_REPORT.md
        echo "  ✓ Removed DEEP_REVIEW_REPORT.md"
    else
        echo "  ℹ️  Kept DEEP_REVIEW_REPORT.md"
    fi
else
    echo "  ℹ️  Already cleaned"
fi

# Count files after cleanup
echo ""
echo "📊 After cleanup:"
echo "  Total files: $(find . -type f | wc -l | tr -d ' ')"
echo "  Python files: $(find . -name '*.py' -type f | wc -l | tr -d ' ')"
echo "  Markdown files: $(find . -name '*.md' -type f | wc -l | tr -d ' ')"
echo ""

echo "✅ Cleanup complete!"
echo ""
echo "📋 Summary:"
echo "  - Backup files removed"
echo "  - Nested directories removed"
echo "  - Redundant tests removed"
echo "  - Cache files cleaned"
echo ""
echo "📝 Next steps:"
echo "  1. Review CLEANUP_REPORT.md for additional items"
echo "  2. Run tests: pytest tests/ -q"
echo "  3. Commit changes: git add -A && git commit -m 'chore: cleanup redundant files'"
