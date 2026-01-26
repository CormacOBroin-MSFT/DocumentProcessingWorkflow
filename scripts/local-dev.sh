#!/bin/bash

# Local Development Script
# Starts both frontend and backend, with optional Azure setup

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

echo "🚀 AutonomousFlow Local Development"
echo ""

# Parse arguments
SETUP_AZURE=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --setup-azure|-a) SETUP_AZURE=true ;;
        --help|-h)
            echo "Usage: scripts/local-dev.sh [options]"
            echo ""
            echo "Options:"
            echo "  --setup-azure, -a   Run Azure setup first (creates resources + .env)"
            echo "  --help, -h          Show this help"
            echo ""
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Run Azure setup if requested or if no .env exists
if [ "$SETUP_AZURE" = true ]; then
    echo "📦 Running Azure setup..."
    echo ""
    "$SCRIPT_DIR/setup-azure.sh"
    echo ""
elif [ ! -f "$PROJECT_DIR/backend/.env" ]; then
    echo "⚠️  No backend/.env found."
    echo ""
    echo "Options:"
    echo "  1. Run scripts/setup-azure.sh to create Azure resources"
    echo "  2. Copy backend/.env.example to backend/.env for mock mode"
    echo "  3. Run scripts/local-dev.sh --setup-azure to do both"
    echo ""
    read -p "Run Azure setup now? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        "$SCRIPT_DIR/setup-azure.sh"
        echo ""
    else
        echo "📝 Creating backend/.env from template (mock mode)..."
        cp "$PROJECT_DIR/backend/.env.example" "$PROJECT_DIR/backend/.env"
        echo ""
    fi
fi

# Setup backend
echo "🐍 Setting up Python backend..."
cd "$PROJECT_DIR/backend"

if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q

echo "   Starting Flask backend on http://localhost:5000..."
python run.py &
BACKEND_PID=$!
cd "$PROJECT_DIR"

# Give backend time to start
sleep 2

# Check if npm dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

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
echo "   Health:   http://localhost:5000/api/health"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for processes
wait
