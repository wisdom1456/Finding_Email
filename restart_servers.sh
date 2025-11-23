#!/bin/bash

echo "🔄 Restarting servers for SSE implementation..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if servers are already running
echo "${BLUE}Checking for running servers...${NC}"

# Kill any existing uvicorn processes
pkill -f "uvicorn.*legal_portal" 2>/dev/null && echo "  ✓ Stopped existing backend server"

# Kill any existing npm dev servers
pkill -f "vite.*5173" 2>/dev/null && echo "  ✓ Stopped existing frontend server"

echo ""
echo "${GREEN}Starting Backend Server...${NC}"
echo "Backend will be available at: http://localhost:8000"
echo "API docs available at: http://localhost:8000/docs"
echo ""

# Start backend in background
cd /Users/BRFlorida/Projects/Work/Finding_Emails
source venv/bin/activate
export PYTHONPATH=/Users/BRFlorida/Projects/Work/Finding_Emails/src
nohup python -m uvicorn legal_portal.api.main:app --reload --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!

sleep 3

if ps -p $BACKEND_PID > /dev/null; then
    echo "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"
else
    echo "❌ Backend failed to start. Check backend.log"
    exit 1
fi

echo ""
echo "${GREEN}Starting Frontend Server...${NC}"
echo "Frontend will be available at: http://localhost:5173"
echo ""

# Start frontend in background
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
nohup npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!

sleep 3

if ps -p $FRONTEND_PID > /dev/null; then
    echo "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"
else
    echo "⚠️  Frontend may still be starting. Check frontend.log"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "${GREEN}🎉 Servers restarted successfully!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Server Information:"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Frontend: http://localhost:5173"
echo ""
echo "📝 Log files:"
echo "  Backend:  backend.log"
echo "  Frontend: frontend.log"
echo ""
echo "🔍 To verify SSE is working:"
echo "  1. Open http://localhost:5173 in your browser"
echo "  2. Go to a case and upload files"
echo "  3. Watch for progress updates with filenames"
echo "  4. Start analysis and watch SSE stream in Network tab"
echo ""
echo "🛑 To stop servers:"
echo "  pkill -f 'uvicorn.*legal_portal'"
echo "  pkill -f 'vite.*5173'"
echo ""

