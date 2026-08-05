#!/bin/bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

set -euo pipefail

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

cleanup_deployment_artifacts() {
    rm -f "$PROJECT_DIR/deploy.zip"
    rm -rf "$PROJECT_DIR/backend/static"
}
trap cleanup_deployment_artifacts EXIT

# Source shared functions (for setup_analyzer)
source "$SCRIPT_DIR/setup-analyzer.sh"

for command_name in az curl jq npm zip; do
    if ! command -v "$command_name" &>/dev/null; then
        log_error "Required command not found: $command_name"
        exit 1
    fi
done

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

for required_value in CU_ENDPOINT SEARCH_ENDPOINT COSMOS_ENDPOINT; do
    if [ -z "${!required_value}" ]; then
        log_error "Required endpoint is missing: $required_value"
        exit 1
    fi
done

log_step "Reconciling Content Understanding analyzer..."
setup_analyzer "$CU_ENDPOINT"
log_success "Content Understanding analyzer is ready"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Using Existing Resources:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Storage Account:     $STORAGE_NAME"
echo "   AI Services:         $AI_SERVICES_NAME"
echo "   AI Search:           $SEARCH_SERVICE_NAME"
echo "   Cosmos DB:           $COSMOS_ACCOUNT_NAME"
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

APP_URL=$(jq -r '.appServiceUrl.value // empty' <<< "$DEPLOYMENT_OUTPUT")
APP_NAME=$(jq -r '.appServiceName.value // empty' <<< "$DEPLOYMENT_OUTPUT")
APP_PRINCIPAL_ID=$(jq -r '.appServicePrincipalId.value // empty' <<< "$DEPLOYMENT_OUTPUT")

for required_value in APP_URL APP_NAME APP_PRINCIPAL_ID; do
    if [ -z "${!required_value}" ]; then
        log_error "App Service deployment output is missing: $required_value"
        exit 1
    fi
done

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

log_step "Allowing App Service outbound addresses through the Cosmos DB firewall..."
APP_OUTBOUND_IPS=$(az webapp show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --query outboundIpAddresses -o tsv)
DEV_IP=$(curl --fail --silent --show-error https://api4.ipify.org)
if [[ ! "$DEV_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    log_error "Could not detect a valid developer public IP"
    exit 1
fi
EXISTING_COSMOS_IPS=$(az cosmosdb show \
    --name "$COSMOS_ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "ipRules[].ipAddressOrRange" -o tsv | tr '\n' ',')
COSMOS_IPS=$(printf '%s,%s' "$DEV_IP" "$APP_OUTBOUND_IPS" | tr ',' '\n' | sed '/^$/d' | awk '!seen[$0]++' | paste -sd, -)
NORMALIZED_EXISTING_IPS=$(printf '%s' "$EXISTING_COSMOS_IPS" | tr ',' '\n' | sed '/^$/d' | sort -u | paste -sd, -)
NORMALIZED_COSMOS_IPS=$(printf '%s' "$COSMOS_IPS" | tr ',' '\n' | sed '/^$/d' | sort -u | paste -sd, -)

if [ -z "$COSMOS_IPS" ]; then
    log_error "Could not determine any Cosmos DB firewall addresses"
    exit 1
fi

if [ "$NORMALIZED_EXISTING_IPS" = "$NORMALIZED_COSMOS_IPS" ]; then
    log_success "Cosmos DB firewall already includes App Service outbound addresses"
else
    az cosmosdb update \
        --name "$COSMOS_ACCOUNT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --public-network-access ENABLED \
        --ip-range-filter "$COSMOS_IPS" \
        --output none
    log_success "Cosmos DB firewall includes App Service outbound addresses"
fi
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

if [ ! -s deploy.zip ]; then
    log_error "Deployment package was not created or is empty"
    exit 1
fi

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

log_step "Waiting for app health check..."
HEALTH_STATUS="000"
for ((attempt = 1; attempt <= 60; attempt++)); do
    HEALTH_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" "$APP_URL/health" || true)
    if [ "$HEALTH_STATUS" = "200" ]; then
        break
    fi
    sleep 2
done

if [ "$HEALTH_STATUS" != "200" ]; then
    log_error "App did not become healthy within two minutes (status: ${HEALTH_STATUS:-000})"
    echo "   Check logs: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
    exit 1
fi

log_success "App is healthy!"

log_step "Validating deployed service configuration and Cosmos access..."
STATUS_RESPONSE=$(curl --fail --silent "$APP_URL/api/status")
if ! jq -e '.azureConfigured and .openaiConfigured and .cosmosConfigured' <<< "$STATUS_RESPONSE" >/dev/null; then
    log_error "Deployed service configuration is incomplete: $STATUS_RESPONSE"
    exit 1
fi

COSMOS_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" "$APP_URL/api/cosmosdb/declarations?limit=1")
if [ "$COSMOS_STATUS" != "200" ]; then
    log_error "Deployed service could not read Cosmos DB (status: $COSMOS_STATUS)"
    exit 1
fi

log_success "Deployed Azure services and Cosmos DB access validated"

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
