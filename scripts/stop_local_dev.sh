#!/bin/bash
# Stop Local Development Servers

echo "🛑 Stopping all development servers..."

# Kill processes on ports 5173, 5174, and 8000
lsof -ti:5173,5174,8000 | xargs kill -9 2>/dev/null || true

echo "✅ All servers stopped!"
echo ""
echo "Ports cleaned up:"
echo "  - 5173 (Frontend)"
echo "  - 5174 (Frontend alternate)"
echo "  - 8000 (Backend)"

