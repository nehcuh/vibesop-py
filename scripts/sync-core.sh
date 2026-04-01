#!/bin/bash
# Sync core YAML schemas from Ruby version

set -e

RUBY_PROJECT="../vibesop"
PYTHON_PROJECT="."

echo "🔄 Syncing core YAML schemas from Ruby version..."

# Copy core YAML files
if [ -d "$RUBY_PROJECT/core" ]; then
    cp -r "$RUBY_PROJECT/core"/*.yaml "$PYTHON_PROJECT/src/vibesop/core/synced/" 2>/dev/null || true
    echo "✅ Synced core YAML files"
else
    echo "⚠️  Ruby project not found at $RUBY_PROJECT"
fi

# Copy documentation
if [ -d "$RUBY_PROJECT/docs" ]; then
    cp -r "$RUBY_PROJECT/docs" "$PYTHON_PROJECT/" 2>/dev/null || true
    echo "✅ Synced documentation"
fi

echo "✨ Sync complete!"
