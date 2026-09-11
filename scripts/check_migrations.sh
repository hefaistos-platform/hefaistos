#!/bin/bash
# Migration troubleshooting and cleanup script for HEFAISTOS

set -e

BACKEND_DIR="backend"
APP_NAME="${1:-pain_points}"

echo "=== HEFAISTOS Migration Management Tool ==="
echo "App: $APP_NAME"
echo ""

# Check if migrations directory exists
if [ ! -d "$BACKEND_DIR/$APP_NAME/migrations" ]; then
    echo "ERROR: $BACKEND_DIR/$APP_NAME/migrations not found"
    exit 1
fi

# Function to show current migration status
show_status() {
    echo "📋 Current Migration Files:"
    ls -1 "$BACKEND_DIR/$APP_NAME/migrations/" | grep -E "^[0-9]" || echo "No migrations found"
    echo ""
}

# Function to check for conflicts
check_conflicts() {
    echo "🔍 Checking for migration conflicts..."
    
    # Count files starting with 0002
    count=$(ls -1 "$BACKEND_DIR/$APP_NAME/migrations/" 2>/dev/null | grep -E "^0002_" | wc -l)
    
    if [ "$count" -gt 1 ]; then
        echo "⚠️  CONFLICT DETECTED: Multiple 0002_* files found:"
        ls -1 "$BACKEND_DIR/$APP_NAME/migrations/" | grep "^0002_"
        return 1
    else
        echo "✅ No migration number conflicts detected"
        return 0
    fi
}

# Function to validate migration chain
validate_chain() {
    echo "🔗 Validating migration dependency chain..."
    
    # This would require parsing Python, so we'll just show the dependencies
    echo "Dependencies:"
    grep -h "dependencies = \[" "$BACKEND_DIR/$APP_NAME/migrations/"*.py 2>/dev/null || echo "No dependencies found"
    echo ""
}

# Function to show what to do
show_recommendations() {
    echo "💡 Recommendations:"
    echo ""
    echo "For a clean migration setup:"
    echo "1. Keep 0001_initial.py"
    echo "2. Use 0002_add_threaded_comments_consolidated.py (if it exists)"
    echo "3. Delete old conflicting files"
    echo ""
    echo "To apply migrations:"
    echo "  python manage.py migrate $APP_NAME"
    echo ""
    echo "To fake a migration (if DB already has the schema):"
    echo "  python manage.py migrate $APP_NAME 0002_add_threaded_comments_consolidated --fake"
    echo ""
    echo "To check migration status:"
    echo "  python manage.py showmigrations $APP_NAME"
    echo ""
}

# Main
show_status
if ! check_conflicts; then
    echo ""
    show_recommendations
    exit 1
fi

validate_chain
show_recommendations

echo "✨ Migration check complete!"
