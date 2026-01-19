#!/bin/bash

# Local Development Setup Script
# Run this to start both frontend and backend locally

set -e

echo "🚀 Starting AutonomousFlow Local Development"
echo ""

# Check if backend .env exists
if [ ! -f "backend/.env" ]; then
    echo "📝 Creating backend/.env from template..."
    cp backend/.env.example backend/.env
    echo ""
    echo "⚠️  Edit backend/.env with your credentials (or leave empty for mock mode)"
    echo ""
    echo "💡 Tip: Run ./setup-azure.sh to deploy Azure resources and auto-populate .env"
    echo ""
fi

# Setup backend
echo "🐍 Setting up Python backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q

echo "   Starting Flask backend on http://localhost:5000..."
python run.py &
BACKEND_PID=$!
cd ..

# Give backend time to start
sleep 2

# Start frontend
echo ""
echo "⚛️  Starting Vite dev server..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Local development servers running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:5000"
echo "   API Docs: http://localhost:5000/api/health"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for processes
wait
