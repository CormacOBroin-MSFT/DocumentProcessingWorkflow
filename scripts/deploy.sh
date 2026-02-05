#!/bin/bash
set -e

# ============================================================================
# Deploy App Service to Azure
# ============================================================================
# This script deploys an App Service that connects to EXISTING Azure resources
# created by setup-azure.sh. It does NOT create new AI, Storage, or Cosmos resources.
#
# Prerequisites:
#   - Run setup-azure.sh first to create Azure resources
#   - Be logged in with: az login
#
# Usage:
#   ./scripts/deploy.sh
# ============================================================================

# Configuration - MUST match setup-azure.sh
RESOURCE_GROUP="autonomousflow-rg"
LOCATION="swedencentral"
BASE_NAME="autonomousflow"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

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

# Error handler
handle_error() {
    local line=$1
    log_error "Script failed at line $line"
    exit 1
}
trap 'handle_error $LINENO' ERR

# Source shared functions (for setup_analyzer)
source "$SCRIPT_DIR/setup-analyzer.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Deploy App Service to Azure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if logged in
log_step "Checking Azure CLI login..."
if ! az account show &>/dev/null; then
    log_error "Not logged in to Azure. Run: az login"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
log_success "Logged in to: $SUBSCRIPTION"
echo ""

# Verify resource group exists
log_step "Verifying resource group '$RESOURCE_GROUP' exists..."
if ! az group show --name $RESOURCE_GROUP &>/dev/null; then
    log_error "Resource group '$RESOURCE_GROUP' does not exist!"
    echo ""
    echo "   Run setup-azure.sh first to create Azure resources:"
    echo ""
    echo "   ./scripts/setup-azure.sh"
    echo ""
    exit 1
fi
log_success "Resource group exists"

# Verify required resources exist
log_step "Verifying existing resources..."

STORAGE_NAME="${BASE_NAME//-/}storage"
AI_SERVICES_NAME="${BASE_NAME}-foundry"
SEARCH_SERVICE_NAME="${BASE_NAME}-search"
COSMOS_ACCOUNT_NAME="${BASE_NAME}-cosmos"
KEY_VAULT_NAME="${BASE_NAME}-kv"

# Check each required resource
MISSING_RESOURCES=""

if ! az storage account show --name $STORAGE_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    MISSING_RESOURCES="$MISSING_RESOURCES Storage($STORAGE_NAME)"
fi

if ! az cognitiveservices account show --name $AI_SERVICES_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    MISSING_RESOURCES="$MISSING_RESOURCES AI-Services($AI_SERVICES_NAME)"
fi

if ! az search service show --name $SEARCH_SERVICE_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    MISSING_RESOURCES="$MISSING_RESOURCES AI-Search($SEARCH_SERVICE_NAME)"
fi

if ! az cosmosdb show --name $COSMOS_ACCOUNT_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    MISSING_RESOURCES="$MISSING_RESOURCES CosmosDB($COSMOS_ACCOUNT_NAME)"
fi

if [ -n "$MISSING_RESOURCES" ]; then
    log_error "Missing required resources:$MISSING_RESOURCES"
    echo ""
    echo "   Run setup-azure.sh first to create Azure resources:"
    echo ""
    echo "   ./scripts/setup-azure.sh"
    echo ""
    exit 1
fi

log_success "All required resources exist"
echo ""

# Get resource endpoints for display
CU_ENDPOINT=$(az cognitiveservices account show --name $AI_SERVICES_NAME --resource-group $RESOURCE_GROUP --query properties.endpoint -o tsv)
SEARCH_ENDPOINT="https://${SEARCH_SERVICE_NAME}.search.windows.net"
COSMOS_ENDPOINT=$(az cosmosdb show --name $COSMOS_ACCOUNT_NAME --resource-group $RESOURCE_GROUP --query documentEndpoint -o tsv)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Using Existing Resources:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Storage Account:     $STORAGE_NAME"
echo "   AI Services:         $AI_SERVICES_NAME"
echo "   AI Search:           $SEARCH_SERVICE_NAME"
echo "   Cosmos DB:           $COSMOS_ACCOUNT_NAME"
echo "   Key Vault:           $KEY_VAULT_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Deploy App Service (only)
log_step "Deploying App Service (this may take 1-2 minutes)..."
echo ""

DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file "$PROJECT_DIR/infrastructure/appservice-only.bicep" \
  --parameters baseName=$BASE_NAME location=$LOCATION \
  --query properties.outputs -o json)

APP_URL=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServiceUrl.value')
APP_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServiceName.value')
APP_PRINCIPAL_ID=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServicePrincipalId.value')

log_success "App Service deployed: $APP_NAME"
echo ""

# Assign Cosmos DB SQL RBAC role to App Service managed identity
# (This is a data-plane role, different from Azure RBAC, and must be done via CLI)
log_step "Assigning Cosmos DB data plane role to App Service..."

COSMOS_ACCOUNT_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT_NAME"

az cosmosdb sql role assignment create \
  --account-name $COSMOS_ACCOUNT_NAME \
  --resource-group $RESOURCE_GROUP \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --principal-id $APP_PRINCIPAL_ID \
  --scope "$COSMOS_ACCOUNT_ID" \
  --output none 2>/dev/null || log_warning "Cosmos DB role may already exist"

log_success "Cosmos DB role assigned"
echo ""

# Build the application
log_step "Building frontend..."
npm ci --silent
npm run build

log_success "Frontend built"

# Prepare deployment package
log_step "Creating deployment package..."
mkdir -p backend/static
cp -r dist/* backend/static/

cd backend
zip -rq ../deploy.zip . -x "*.pyc" -x "__pycache__/*" -x "venv/*" -x ".env" -x "*.log"
cd ..

log_success "Deployment package created"

# Deploy to App Service
log_step "Deploying code to App Service..."
az webapp deploy \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --src-path deploy.zip \
  --type zip \
  --async false

log_success "Code deployed"

# Cleanup
rm -f deploy.zip
rm -rf backend/static

# Wait for app to start
log_step "Waiting for app to start..."
sleep 10

# Check app health
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$APP_URL/health" 2>/dev/null || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
    log_success "App is healthy!"
else
    log_warning "App may still be starting (status: $HEALTH_STATUS)"
    echo "   Check logs: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Application URL: $APP_URL"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 App Service Managed Identity Access:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   ✅ Azure Blob Storage      - Storage Blob Data Contributor"
echo "   ✅ Azure AI Services       - Cognitive Services User"
echo "   ✅ Azure Key Vault         - Key Vault Secrets User"
echo "   ✅ Azure AI Search         - Search Index Data Contributor"
echo "   ✅ Azure AI Search         - Search Service Contributor"
echo "   ✅ Azure Cosmos DB         - SQL Data Contributor"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Useful Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   View logs:"
echo "   az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "   Restart app:"
echo "   az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
