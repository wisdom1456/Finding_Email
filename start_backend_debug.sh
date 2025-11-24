#!/bin/bash
# Start backend with full console output for debugging

cd /Users/BRFlorida/Projects/Work/Finding_Emails/src

echo "================================"
echo "Starting Backend with Debug Mode"
echo "================================"
echo "Backend will run in foreground with full output"
echo "Press Ctrl+C to stop"
echo "================================"
echo ""

python3 -m uvicorn legal_portal.api.main:app --reload --port 8000

