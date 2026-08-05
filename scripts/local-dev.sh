#!/bin/bash

if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

# Local Development Script
# Starts both frontend and backend, with optional Azure setup

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

for command_name in curl lsof npm python3; do
    if ! command -v "$command_name" &>/dev/null; then
        echo "Required command not found: $command_name"
        exit 1
    fi
done

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
    echo "Python 3.9 or newer is required."
    exit 1
fi

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

for port in 5000 5173; do
    LISTENER_PID=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)
    if [ -n "$LISTENER_PID" ]; then
        echo "Port $port is already in use by PID $LISTENER_PID. Stop that process before starting local development."
        exit 1
    fi
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
        echo "📝 Creating backend/.env for mock mode..."
        {
            echo "# Local mock mode: Azure variables intentionally unset"
            echo "FLASK_ENV=development"
            echo "FLASK_DEBUG=true"
        } > "$PROJECT_DIR/backend/.env"
        echo ""
    fi
fi

# Setup backend
echo "🐍 Setting up Python backend..."
cd "$PROJECT_DIR/backend"

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    echo ""
    echo "🛑 Shutting down servers..."
    [ -z "$BACKEND_PID" ] || kill "$BACKEND_PID" 2>/dev/null || true
    [ -z "$FRONTEND_PID" ] || kill "$FRONTEND_PID" 2>/dev/null || true
    [ -z "$BACKEND_PID" ] || wait "$BACKEND_PID" 2>/dev/null || true
    [ -z "$FRONTEND_PID" ] || wait "$FRONTEND_PID" 2>/dev/null || true
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

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

for ((attempt = 1; attempt <= 30; attempt++)); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        wait "$BACKEND_PID" 2>/dev/null || true
        echo "Backend failed to start. Review the error output above."
        exit 1
    fi
    if curl --fail --silent http://localhost:5000/health >/dev/null; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "Backend did not become healthy within 30 seconds."
        exit 1
    fi
    sleep 1
done

# Install npm dependencies if missing or incomplete (a partial node_modules
# directory would otherwise pass a bare directory check but lack the vite binary)
if [ ! -x "node_modules/.bin/vite" ]; then
    echo "📦 Installing npm dependencies..."
    npm ci
fi

# Start frontend
echo ""
echo "⚛️  Starting Vite dev server..."
npm run dev &
FRONTEND_PID=$!

for ((attempt = 1; attempt <= 30; attempt++)); do
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        wait "$FRONTEND_PID" 2>/dev/null || true
        echo "Frontend failed to start. Review the error output above."
        exit 1
    fi
    if curl --fail --silent http://localhost:5173 >/dev/null; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "Frontend did not become ready within 30 seconds."
        exit 1
    fi
    sleep 1
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Local development servers running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:5000"
echo "   Health:   http://localhost:5000/health"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done

echo "A development server stopped unexpectedly."
exit 1
