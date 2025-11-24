#!/bin/bash
# Quick script to check AI improvement loop progress

echo "======================================================================"
echo "AI IMPROVEMENT LOOP - PROGRESS CHECK"
echo "======================================================================"
echo ""

# Check if process is running
PID=$(ps aux | grep "ai_letter_improvement_loop.py" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "❌ AI loop is NOT running"
    echo ""
    echo "To start it, run:"
    echo "  cd /Users/BRFlorida/Projects/Work/Finding_Emails"
    echo "  OPENAI_API_KEY='your-key' nohup python3 scripts/ai_letter_improvement_loop.py > ai_improvement.log 2>&1 &"
else
    echo "✅ AI loop is RUNNING (PID: $PID)"
fi

echo ""
echo "======================================================================"
echo "LATEST ITERATIONS"
echo "======================================================================"
echo ""

cd "$(dirname "$0")/.."
ls -lth prompt_versions/ 2>/dev/null | head -8 | tail -7 | awk '{printf "  %s %s - %s (%s)\n", $6, $7, $9, $5}'

echo ""
echo "======================================================================"
echo "LATEST GENERATED LETTERS"
echo "======================================================================"
echo ""

ls -lth test_data/generated_letter_*.txt 2>/dev/null | head -5 | awk '{printf "  %s %s - %s\n", $6, $7, $9}'

echo ""
echo "======================================================================"
echo "SCORE TREND"
echo "======================================================================"
echo ""

# Extract scores from filenames
scores=$(ls -t prompt_versions/*.txt 2>/dev/null | head -10 | sed 's/.*_v\([0-9]*\)_\([0-9]*\)pct.txt/Iter \1: \2%/')
echo "$scores"

echo ""
echo "======================================================================"
echo "TARGET: 90%+"
echo "======================================================================"

