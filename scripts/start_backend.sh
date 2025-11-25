#!/bin/bash
# Start FastAPI Backend

cd /Users/BRFlorida/Projects/Work/Finding_Emails/src

echo "================================================"
echo "Starting Legal Document Analysis API Backend"
echo "================================================"
echo ""
echo "API will be available at:"
echo "  • Main: http://localhost:8000"
echo "  • Docs: http://localhost:8000/docs"
echo "  • Health: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 -m uvicorn legal_portal.api.main:app --reload --port 8000

