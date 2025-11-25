#!/bin/bash

# Script to cleanly restart the Legal Portal application
# This ensures Python code changes are picked up

echo "========================================="
echo "Restarting Legal Portal Application"
echo "========================================="
echo ""

# Navigate to project root
cd "$(dirname "$0")"

echo "📦 Clearing Python cache files..."
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true
echo "✅ Cache cleared"
echo ""

echo "🔍 Verifying code changes are present..."

# Check fix #1 (preventive)
if grep -q 'Remove code fences with language specifiers' src/legal_portal/services/json_processing_service.py; then
    echo "✅ Code fix is present in json_processing_service.py"
else
    echo "❌ WARNING: Fix missing in json_processing_service.py"
fi

# Check fix #2 (primary fix)
if grep -q '_clean_code_fences' src/legal_portal/services/letter_review_service.py; then
    echo "✅ PRIMARY FIX is present in letter_review_service.py"
else
    echo "❌ WARNING: PRIMARY FIX missing in letter_review_service.py"
fi

# Check CSS improvements
if grep -q 'text-align: justify' src/legal_portal/services/document_formatter.py; then
    echo "✅ CSS improvements are present in document_formatter.py"
else
    echo "❌ WARNING: CSS improvements may be missing"
fi

echo ""

echo "🔧 Checking virtual environment..."
if [ -d "venv" ]; then
    echo "✅ Virtual environment found"
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "⚠️  No venv directory found - using system Python"
fi
echo ""

echo "🚀 Starting application..."
echo "----------------------------------------"
echo ""

# Check which start method is available
if [ -f "start_app.sh" ]; then
    echo "Using start_app.sh..."
    ./start_app.sh
elif [ -f "run_app.py" ]; then
    echo "Using run_app.py..."
    python3 run_app.py
elif [ -f "src/legal_portal/ui/main.py" ]; then
    echo "Using streamlit directly..."
    streamlit run src/legal_portal/ui/main.py
else
    echo "❌ Could not find application entry point"
    echo "Please start the app manually"
    exit 1
fi

