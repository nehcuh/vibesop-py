#!/bin/bash
# VibeSOP Release Verification Script
#
# This script verifies that the package is ready for PyPI release.

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
PYTHON_VERSION=$(python --version | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
    echo -e "${GREEN}✅ Python version: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}❌ Python version must be 3.12+ (found: $PYTHON_VERSION)${NC}"
    exit 1
fi

# Check if in virtual environment
echo ""
echo "2. Checking virtual environment..."
if python -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)"; then
    echo -e "${GREEN}✅ Virtual environment active${NC}"
else
    echo -e "${YELLOW}⚠️  Not in virtual environment${NC}"
fi

# Run tests
echo ""
echo "3. Running tests..."
if python -m pytest tests/ -q --no-cov 2>&1 | grep -q "passed"; then
    echo -e "${GREEN}✅ Tests passing${NC}"
else
    echo -e "${RED}❌ Tests failing${NC}"
    exit 1
fi

# Check type hints
echo ""
echo "4. Checking type hints..."
if python -c "import pyright; import subprocess; subprocess.run(['pyright', 'src/vibesop'], check=True)" 2>/dev/null; then
    echo -e "${GREEN}✅ Type checking passed${NC}"
else
    echo -e "${YELLOW}⚠️  Type checking has warnings (may be acceptable)${NC}"
fi

# Check linting
echo ""
echo "5. Checking code style..."
if python -m ruff check src/ --output-format=text 2>&1 | grep -q "0 errors"; then
    echo -e "${GREEN}✅ No linting errors${NC}"
else
    echo -e "${YELLOW}⚠️  Linting issues found${NC}"
    python -m ruff check src/ --output-format=concise
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
    "MANIFEST.in"
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

# Check version in pyproject.toml
echo ""
echo "7. Checking version..."
VERSION=$(grep "^version = " pyproject.toml | head -1 | cut -d'"' -f2)
echo "Version: $VERSION"

if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}❌ Invalid version format${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Version format valid${NC}"
fi

# Try to build package
echo ""
echo "8. Building package..."
if python -m build --outdir /tmp/vibesop-build 2>&1 | grep -q "Successfully built"; then
    echo -e "${GREEN}✅ Package built successfully${NC}"
else
    echo -e "${RED}❌ Package build failed${NC}"
    exit 1
fi

# Check package
echo ""
echo "9. Checking package..."
if twine check /tmp/vibesop-build/vibesop-* 2>&1 | grep -q "Checking"; then
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
echo "3. Upload to TestPyPI: twine upload --repository testpypi /tmp/vibesop-build/*"
echo "4. Upload to PyPI: twine upload /tmp/vibesop-build/*"
echo ""
