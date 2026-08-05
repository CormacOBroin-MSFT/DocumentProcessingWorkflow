#!/bin/bash

# Flask Backend Setup Script
# This script sets up the Python virtual environment and installs dependencies

set -e

echo "🚀 Setting up Flask Backend for AI Document Processing..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
    echo "❌ Python 3.9 or newer is required."
    exit 1
fi
echo ""

# Navigate to backend directory
cd "$(dirname "$0")"

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet
echo "✅ pip upgraded"
echo ""

# Install dependencies
echo "📥 Installing dependencies from requirements.txt..."
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Check if .env exists
if [ -f ".env" ]; then
    echo "✅ .env file exists"
else
    echo "⚠️  .env file not found"
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your actual Azure credentials before running the server!"
    echo ""
fi

# Test imports
echo "🧪 Testing imports..."
python3 -c "import flask; import azure.storage.blob; import azure.ai.formrecognizer; import openai; print('✅ All imports successful')"
echo ""

echo "✨ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Edit .env file with your Azure credentials"
echo "  2. Activate the virtual environment: source venv/bin/activate"
echo "  3. Run the server: python run.py"
echo "  4. Test health endpoint: curl http://localhost:5000/health"
echo ""
echo "📚 Documentation:"
echo "  - Backend README: ./README.md"
echo "  - Integration Guide: ../INTEGRATION_GUIDE.md"
echo ""
