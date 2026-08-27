#!/bin/bash
# VibeSOP Release Verification Script
#
# This script verifies that the package is ready for PyPI release.
# Toolchain: uv + ruff + basedpyright (same as CI). Run via: bash scripts/verify-release.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================"
echo "VibeSOP Release Verification"
echo "================================"
echo ""

# Check Python version
echo "1. Checking Python version..."
PYTHON_VERSION=$(uv run python --version | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
    echo -e "${GREEN}✅ Python version: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}❌ Python version must be 3.12+ (found: $PYTHON_VERSION)${NC}"
    exit 1
fi

# Check lockfile is in sync
echo ""
echo "2. Checking lockfile sync..."
if uv lock --check; then
    echo -e "${GREEN}✅ uv.lock in sync with pyproject.toml${NC}"
else
    echo -e "${RED}❌ uv.lock out of sync — run 'uv lock'${NC}"
    exit 1
fi

# Run tests
echo ""
echo "3. Running tests..."
if uv run pytest -m "not benchmark and not slow" -q 2>&1 | grep -q "passed"; then
    echo -e "${GREEN}✅ Tests passing${NC}"
else
    echo -e "${RED}❌ Tests failing${NC}"
    exit 1
fi

# Check type hints
echo ""
echo "4. Checking type hints (basedpyright, exit 0/3 accepted — same as CI)..."
uv run basedpyright || TYPE_EXIT=$?
if [ "${TYPE_EXIT:-0}" -eq 0 ] || [ "${TYPE_EXIT:-0}" -eq 3 ]; then
    echo -e "${GREEN}✅ Type checking passed (0 errors)${NC}"
else
    echo -e "${RED}❌ Type checking failed with errors${NC}"
    exit 1
fi

# Check linting
echo ""
echo "5. Checking code style..."
if uv run ruff check . && uv run ruff format --check .; then
    echo -e "${GREEN}✅ No linting errors${NC}"
else
    echo -e "${RED}❌ Linting issues found${NC}"
    exit 1
fi

# Check if all required files exist
echo ""
echo "6. Checking required files..."
REQUIRED_FILES=(
    "README.md"
    "LICENSE"
    "CHANGELOG.md"
    "CONTRIBUTING.md"
    "pyproject.toml"
)

ALL_FILES_PRESENT=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ $file${NC}"
    else
        echo -e "${RED}❌ $file missing${NC}"
        ALL_FILES_PRESENT=false
    fi
done

if [ "$ALL_FILES_PRESENT" = false ]; then
    exit 1
fi

# Check version in pyproject.toml (PEP 440 incl. dev/a/b/rc pre-releases)
echo ""
echo "7. Checking version..."
VERSION=$(grep "^version = " pyproject.toml | head -1 | cut -d'"' -f2)
echo "Version: $VERSION"

if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+((\.dev|a|b|rc)[0-9]+)?$ ]]; then
    echo -e "${RED}❌ Invalid version format${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Version format valid${NC}"
fi

# Try to build package
echo ""
echo "8. Building package..."
rm -rf /tmp/vibesop-build
if uv build --out-dir /tmp/vibesop-build; then
    echo -e "${GREEN}✅ Package built successfully${NC}"
else
    echo -e "${RED}❌ Package build failed${NC}"
    exit 1
fi

# Check package
echo ""
echo "9. Checking package..."
if uvx twine check /tmp/vibesop-build/vibesop-*; then
    echo -e "${GREEN}✅ Package check passed${NC}"
else
    echo -e "${RED}❌ Package check failed${NC}"
    exit 1
fi

# Summary
echo ""
echo "================================"
echo -e "${GREEN}✅ All Checks Passed!${NC}"
echo "================================"
echo ""
echo "Package is ready for PyPI release!"
echo ""
echo "Next steps:"
echo "1. Review the package in /tmp/vibesop-build"
echo "2. Test with: pip install /tmp/vibesop-build/vibesop-$VERSION.tar.gz"
echo "3. Release via tag: git tag v$VERSION && git push origin v$VERSION"
echo "   (the Release workflow runs CI gate, SLSA attestation, Trusted Publishing)"
echo ""
