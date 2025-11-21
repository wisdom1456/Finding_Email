#!/bin/bash
# Start Local Development Servers
# This script starts both backend and frontend on 127.0.0.1

set -e

echo "🧹 Cleaning up any existing processes..."
lsof -ti:5173,5174,8000 | xargs kill -9 2>/dev/null || true

echo ""
echo "🚀 Starting Backend (FastAPI) on 127.0.0.1:8000..."
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 -m uvicorn src.legal_portal.api.main:app --reload --host 127.0.0.1 --port 8000 > backend_live.log 2>&1 &
BACKEND_PID=$!

echo "⏳ Waiting for backend to start..."
sleep 3

# Check if backend is running
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo "✅ Backend running on http://127.0.0.1:8000"
    echo "   API Docs: http://127.0.0.1:8000/docs"
else
    echo "❌ Backend failed to start. Check backend_live.log"
    exit 1
fi

echo ""
echo "🚀 Starting Frontend (SvelteKit) on 0.0.0.0:5173..."
cd frontend
npm run dev > ../frontend_live.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo "⏳ Waiting for frontend to start..."
sleep 5

# Check if frontend is running
if lsof -i:5173 > /dev/null 2>&1; then
    echo "✅ Frontend running on http://127.0.0.1:5173"
else
    echo "❌ Frontend failed to start. Check frontend_live.log"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Development servers are running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Application:  http://127.0.0.1:5173"
echo "🔌 Backend API:  http://127.0.0.1:8000"
echo "📚 API Docs:     http://127.0.0.1:8000/docs"
echo ""
echo "📋 Process IDs:"
echo "   Backend:  $BACKEND_PID"
echo "   Frontend: $FRONTEND_PID"
echo ""
echo "📝 Logs:"
echo "   Backend:  tail -f backend_live.log"
echo "   Frontend: tail -f frontend_live.log"
echo ""
echo "🛑 To stop servers:"
echo "   kill $BACKEND_PID $FRONTEND_PID"
echo "   or: ./stop_local_dev.sh"
echo ""
echo "Press Ctrl+C to stop monitoring (servers will continue running)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Keep script running to show live logs
tail -f backend_live.log frontend_live.log

