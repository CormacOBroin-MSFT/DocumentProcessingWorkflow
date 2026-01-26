#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}▶${NC} $1"; }
log_success() { echo -e "${GREEN}✅${NC} $1"; }
log_warning() { echo -e "${YELLOW}⚠️${NC} $1"; }
log_error() { echo -e "${RED}❌${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗑️  Cleanup Azure AI Foundry Agents"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if logged in
log_step "Checking Azure CLI login..."
if ! az account show &>/dev/null; then
    log_error "Not logged in to Azure. Run: az login"
    exit 1
fi
log_success "Logged in to Azure"

# Load environment
if [ -f "$PROJECT_DIR/backend/.env" ]; then
    log_step "Loading environment from .env..."
    export $(grep -v '^#' "$PROJECT_DIR/backend/.env" | xargs)
    log_success "Environment loaded"
else
    log_error "No .env file found. Run setup-azure.sh first."
    exit 1
fi

# Activate venv
if [ -d "$PROJECT_DIR/backend/venv" ]; then
    source "$PROJECT_DIR/backend/venv/bin/activate"
else
    log_error "Python venv not found. Run setup-azure.sh first."
    exit 1
fi

# Run cleanup
log_step "Deleting agents from Azure AI Foundry..."
if python "$PROJECT_DIR/agents/workflow.py" --cleanup; then
    log_success "Agents deleted from Azure AI Foundry"
else
    log_error "Cleanup failed"
    exit 1
fi

deactivate

echo ""
log_success "Cleanup complete!"
echo ""
