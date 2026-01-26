#!/bin/bash
set -e

# Configuration
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
NC='\033[0m' # No Color

log_step() { echo -e "${BLUE}▶${NC} $1"; }
log_success() { echo -e "${GREEN}✅${NC} $1"; }
log_warning() { echo -e "${YELLOW}⚠️${NC} $1"; }
log_error() { echo -e "${RED}❌${NC} $1"; }

# Error handler
handle_error() {
    local line=$1
    log_error "Script failed at line $line"
    echo ""
    echo "To debug, check:"
    echo "  • Azure portal > Resource Groups > $RESOURCE_GROUP > Deployments"
    echo "  • Run: az deployment group list -g $RESOURCE_GROUP -o table"
    echo ""
    exit 1
}
trap 'handle_error $LINENO' ERR

# Source shared functions
source "$SCRIPT_DIR/setup-analyzer.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Azure Infrastructure Setup"
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

# Create resource group (idempotent)
log_step "Creating resource group '$RESOURCE_GROUP' in '$LOCATION'..."
az group create --name $RESOURCE_GROUP --location $LOCATION --output none
log_success "Resource group ready"
echo ""

# Check if resources already exist
AI_SERVICES_NAME="${BASE_NAME}-foundry"
STORAGE_NAME="${BASE_NAME//-/}storage"

log_step "Checking for existing resources..."
EXISTING_AI=$(az cognitiveservices account show --name $AI_SERVICES_NAME --resource-group $RESOURCE_GROUP 2>/dev/null || echo "")
EXISTING_COSMOS=$(az cosmosdb show --name "${BASE_NAME}-cosmos" --resource-group $RESOURCE_GROUP 2>/dev/null || echo "")

# Decide if we need to run Bicep deployment
NEED_BICEP_DEPLOY="false"
if [ -z "$EXISTING_AI" ]; then
    NEED_BICEP_DEPLOY="true"
    log_step "AI Services not found, will deploy..."
fi
if [ -z "$EXISTING_COSMOS" ]; then
    NEED_BICEP_DEPLOY="true"
    log_step "Cosmos DB not found, will deploy..."
fi

if [ "$NEED_BICEP_DEPLOY" = "true" ]; then
    # Deploy infrastructure
    log_step "Deploying Bicep template (this may take 2-3 minutes)..."
    echo ""
    echo "   Template: infrastructure/local-dev.bicep"
    echo "   Resources to create/update:"
    echo "     • Storage Account: ${STORAGE_NAME}"
    echo "     • AI Services: ${AI_SERVICES_NAME}"
    echo "     • Cosmos DB: ${BASE_NAME}-cosmos"
    echo "     • Foundry Project: ${BASE_NAME}-project"
    echo "     • Model Deployments: gpt-41, gpt-41-mini, text-embedding-3-large"
    echo ""
    
    # Run deployment
    if ! az deployment group create \
      --resource-group $RESOURCE_GROUP \
      --template-file "$PROJECT_DIR/infrastructure/local-dev.bicep" \
      --parameters baseName=$BASE_NAME location=$LOCATION \
      --output none 2>&1 | tee /tmp/bicep-deploy.log; then
        log_error "Bicep deployment failed!"
        echo ""
        echo "📋 Deployment log: /tmp/bicep-deploy.log"
        echo ""
        echo "Recent deployment operations:"
        az deployment operation group list \
          --resource-group $RESOURCE_GROUP \
          --name local-dev \
          --query "[?properties.provisioningState=='Failed'].{Resource:properties.targetResource.resourceName, Error:properties.statusMessage.error.message}" \
          -o table 2>/dev/null || true
        exit 1
    fi
    
    log_success "Bicep deployment complete"

    # Parse outputs from successful deployment
    log_step "Parsing deployment outputs..."
    DEPLOYMENT_OUTPUT=$(az deployment group show \
      --resource-group $RESOURCE_GROUP \
      --name local-dev \
      --query properties.outputs -o json)
    
    STORAGE_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.storageAccountName.value')
    CU_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.contentUnderstandingEndpoint.value')
    AI_SERVICES_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.aiServicesName.value')
    OPENAI_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.openAIEndpoint.value')
    OPENAI_DEPLOYMENT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.openAIDeploymentName.value')
    COSMOS_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.cosmosDbEndpoint.value')
    COSMOS_ACCOUNT_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.cosmosDbAccountName.value')
    
    # Create Foundry project via CLI (avoids ARM timing issues with managed identity)
    log_step "Creating Foundry project..."
    if az cognitiveservices account show --name "${BASE_NAME}-foundry/projects/${BASE_NAME}-project" --resource-group $RESOURCE_GROUP &>/dev/null; then
        log_success "Foundry project already exists"
    else
        az rest --method PUT \
          --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${AI_SERVICES_NAME}/projects/${BASE_NAME}-project?api-version=2025-06-01" \
          --body '{"location":"'$LOCATION'","properties":{}}' \
          --output none 2>/dev/null || log_success "Project may already exist"
        log_success "Foundry project created"
    fi
else
    log_success "All resources already exist, skipping Bicep deployment"
    CU_ENDPOINT=$(az cognitiveservices account show --name $AI_SERVICES_NAME --resource-group $RESOURCE_GROUP --query properties.endpoint -o tsv)
    OPENAI_ENDPOINT=$CU_ENDPOINT
    OPENAI_DEPLOYMENT=$(az cognitiveservices account deployment list --name $AI_SERVICES_NAME --resource-group $RESOURCE_GROUP --query "[?contains(name, 'gpt-41')].name | [0]" -o tsv 2>/dev/null || echo "gpt-41")
fi

echo ""
log_success "Infrastructure deployed"
echo ""

# Get current user ID for role assignment
log_step "Setting up role assignments..."
USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "")

log_step "Getting storage connection string..."
STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name $STORAGE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query connectionString -o tsv)

# Assign roles
if [ -n "$USER_OBJECT_ID" ]; then
  echo "   Assigning Cognitive Services User role..."
  az role assignment create \
    --assignee $USER_OBJECT_ID \
    --role "Cognitive Services User" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AI_SERVICES_NAME" \
    --output none 2>/dev/null || log_warning "Role may already exist"
  
  echo "   Assigning Storage Blob Data Contributor role..."
  az role assignment create \
    --assignee $USER_OBJECT_ID \
    --role "Storage Blob Data Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_NAME" \
    --output none 2>/dev/null || log_warning "Role may already exist"
  
  # Get Cosmos DB account name for existing deployments
  if [ -z "$COSMOS_ACCOUNT_NAME" ]; then
    COSMOS_ACCOUNT_NAME="${BASE_NAME}-cosmos"
  fi
  
  # Get the full Cosmos DB account resource ID for account-level scope
  COSMOS_ACCOUNT_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT_NAME"
  
  # Cosmos DB requires SQL Role Assignment for data plane access (different from Azure RBAC)
  # Built-in Data Contributor role ID: 00000000-0000-0000-0000-000000000002
  # We need ACCOUNT-LEVEL scope (not database-level) for the SDK to read metadata
  echo "   Assigning Cosmos DB SQL Role (Data Contributor) at account level..."
  az cosmosdb sql role assignment create \
    --account-name $COSMOS_ACCOUNT_NAME \
    --resource-group $RESOURCE_GROUP \
    --role-definition-id "00000000-0000-0000-0000-000000000002" \
    --principal-id $USER_OBJECT_ID \
    --scope "$COSMOS_ACCOUNT_ID" \
    --output none 2>/dev/null || log_warning "Role may already exist"
  
  log_success "Role assignments complete"
else
  log_warning "Could not get user ID for role assignments"
fi

# Configure storage account network access
log_step "Configuring storage account network access..."
echo "   Enabling public network access (required for development)"
az storage account update \
  --name $STORAGE_NAME \
  --resource-group $RESOURCE_GROUP \
  --public-network-access Enabled \
  --output none

log_success "Storage account configured for secure access"

# Get Cosmos DB endpoint
log_step "Getting Cosmos DB endpoint..."
COSMOS_ENDPOINT=$(az cosmosdb show --name "${BASE_NAME}-cosmos" --resource-group $RESOURCE_GROUP --query documentEndpoint -o tsv 2>/dev/null || echo "")

# Create .env file
ENV_FILE="$PROJECT_DIR/backend/.env"
log_step "Creating $ENV_FILE..."

# Write .env file line by line to avoid formatting issues with long values
{
  echo "# Azure Storage"
  printf '%s\n' "AZURE_STORAGE_CONNECTION_STRING=${STORAGE_CONNECTION_STRING}"
  echo "AZURE_STORAGE_CONTAINER=customs-documents"
  echo ""
  echo "# Azure Content Understanding (uses Azure CLI credentials)"
  echo "AZURE_CONTENT_UNDERSTANDING_ENDPOINT=${CU_ENDPOINT}"
  echo ""
  echo "# Azure OpenAI (same AI Services endpoint)"
  echo "AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}"
  echo "AZURE_OPENAI_DEPLOYMENT=${OPENAI_DEPLOYMENT}"
  echo ""
  echo "# Azure Cosmos DB (uses Azure CLI credentials)"
  echo "AZURE_COSMOS_ENDPOINT=${COSMOS_ENDPOINT}"
  echo "AZURE_COSMOS_DATABASE=customs-workflow"
  echo "AZURE_COSMOS_CONTAINER=declarations"
  echo ""
  echo "# Flask"
  echo "FLASK_ENV=development"
  echo "FLASK_DEBUG=true"
} > "$ENV_FILE"

log_success "Environment file created"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Deployed Resources"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Storage Account:     $STORAGE_NAME"
echo "   AI Services:         $AI_SERVICES_NAME"
echo "   OpenAI Deployment:   $OPENAI_DEPLOYMENT"
echo "   CU Endpoint:         $CU_ENDPOINT"
echo "   Cosmos DB Endpoint:  $COSMOS_ENDPOINT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_warning "Note: Public network access on storage may be disabled daily by subscription policy."
log_warning "If uploads fail, re-run this script to restore network access."
echo ""

# Setup Content Understanding analyzer
log_step "Setting up Content Understanding analyzer..."
setup_analyzer "$CU_ENDPOINT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next: Run scripts/local-dev.sh to start the application"
echo ""
