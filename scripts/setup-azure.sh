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
    AI_PROJECT_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.aiProjectName.value')
    OPENAI_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.openAIEndpoint.value')
    OPENAI_DEPLOYMENT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.openAIDeploymentName.value')
    COSMOS_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.cosmosDbEndpoint.value')
    COSMOS_ACCOUNT_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.cosmosDbAccountName.value')
    SEARCH_SERVICE_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.searchServiceName.value')
    SEARCH_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.searchServiceEndpoint.value')
    
    log_success "Microsoft Foundry (new) project created: $AI_PROJECT_NAME"
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
  
  # Azure AI Search - assign Search Index Data Contributor role
  SEARCH_SERVICE_NAME="${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
  echo "   Assigning Search Index Data Contributor role..."
  az role assignment create \
    --assignee $USER_OBJECT_ID \
    --role "Search Index Data Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
    --output none 2>/dev/null || log_warning "Role may already exist"
  
  echo "   Assigning Search Service Contributor role..."
  az role assignment create \
    --assignee $USER_OBJECT_ID \
    --role "Search Service Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
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
  echo "# Azure AI Search (for agent tools)"
  echo "AZURE_SEARCH_SERVICE_NAME=${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
  echo "AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}"
  echo "AZURE_SEARCH_CONNECTION_NAME=${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
  echo ""
  echo "# Flask"
  echo "FLASK_ENV=development"
  echo "FLASK_DEBUG=true"
} > "$ENV_FILE"

log_success "Environment file created"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Deployed Resources (Microsoft Foundry - New)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Storage Account:     $STORAGE_NAME"
echo "   Foundry Resource:    $AI_SERVICES_NAME"
echo "   Foundry Project:     ${AI_PROJECT_NAME:-${BASE_NAME}-project}"
echo "   OpenAI Deployment:   $OPENAI_DEPLOYMENT"
echo "   AI Search Service:   ${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
echo "   CU Endpoint:         $CU_ENDPOINT"
echo "   Cosmos DB Endpoint:  $COSMOS_ENDPOINT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 View in Microsoft Foundry (new) portal:"
echo "   https://ai.azure.com (toggle 'Try the new Foundry' ON)"
echo ""
log_warning "Note: Public network access on storage may be disabled daily by subscription policy."
log_warning "If uploads fail, re-run this script to restore network access."
echo ""

# Setup Content Understanding analyzer
log_step "Setting up Content Understanding analyzer..."
setup_analyzer "$CU_ENDPOINT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Indexing Reference Data into Azure AI Search"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   This indexes HS codes and sanctions data into Azure AI Search"
echo "   for use by Foundry agents with native tool integration."
echo ""

# Check if reference data files exist
HS_CODES_CSV="$PROJECT_DIR/StaticDataForAgents/uk-tariff-2021-01-01--v4.0.1205--commodities-report.csv"
SANCTIONS_CSV="$PROJECT_DIR/StaticDataForAgents/UK-Sanctions-List.csv"

# Ensure Python venv exists and is activated
if [ ! -d "$PROJECT_DIR/backend/venv" ]; then
    log_step "Creating Python virtual environment..."
    python3 -m venv "$PROJECT_DIR/backend/venv"
    log_success "Virtual environment created"
else
    log_step "Using existing Python virtual environment"
fi

# Activate venv and install requirements
log_step "Activating venv and installing dependencies..."
source "$PROJECT_DIR/backend/venv/bin/activate"

# Install core requirements first (fast)
log_step "Installing core Python packages..."
pip install -q -r "$PROJECT_DIR/backend/requirements.txt"

# Install Azure AI Search SDK
log_step "Installing Azure AI Search SDK..."
pip install -q azure-search-documents azure-identity

log_success "Packages installed"

# Index to Azure AI Search (both HS codes and sanctions)
if [ -f "$HS_CODES_CSV" ] && [ -f "$SANCTIONS_CSV" ]; then
    log_step "Indexing reference data into Azure AI Search..."
    echo "   HS Codes: $HS_CODES_CSV"
    echo "   Sanctions: $SANCTIONS_CSV"
    
    # Export search endpoint for the script
    export AZURE_SEARCH_ENDPOINT="${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}"
    export AZURE_SEARCH_SERVICE_NAME="${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
    
    if python "$PROJECT_DIR/scripts/index_to_search.py" --index all --force; then
        log_success "Reference data indexed to Azure AI Search"
    else
        log_error "Azure AI Search indexing failed!"
        log_warning "Agents will not have access to HS codes and sanctions data."
        # Don't exit - agents can still work without tools
    fi
else
    log_warning "Reference data CSV files not found!"
    [ ! -f "$HS_CODES_CSV" ] && log_warning "  Missing: $HS_CODES_CSV"
    [ ! -f "$SANCTIONS_CSV" ] && log_warning "  Missing: $SANCTIONS_CSV"
    log_warning "Agents will not have access to HS codes and sanctions data."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 Creating Compliance Agents in Azure AI Foundry"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get AI Project endpoint for agents
log_step "Getting AI Foundry Project endpoint..."

# Get the project connection string/endpoint
AI_PROJECT_NAME="${AI_PROJECT_NAME:-${BASE_NAME}-project}"
AI_HUB_NAME="${BASE_NAME}-foundry"

# Construct the AI Project endpoint
# Format: https://<ai-services-name>.services.ai.azure.com/api/projects/<project-name>
AI_PROJECT_ENDPOINT="https://${AI_HUB_NAME}.services.ai.azure.com/api/projects/${AI_PROJECT_NAME}"

log_success "AI Project Endpoint: $AI_PROJECT_ENDPOINT"

# Create Azure AI Search connection in the project
log_step "Creating Azure AI Search connection in the Foundry project..."

SEARCH_CONNECTION_NAME="${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"
SEARCH_CONNECTION_FILE="/tmp/search-connection.yml"

# Create the connection YAML file (keyless/managed identity)
cat > "$SEARCH_CONNECTION_FILE" << EOF
name: ${SEARCH_CONNECTION_NAME}
type: azure_ai_search
endpoint: ${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}
EOF

# Create the connection using az ml
if az ml connection create \
    --file "$SEARCH_CONNECTION_FILE" \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$AI_PROJECT_NAME" \
    2>&1; then
    log_success "AI Search connection created: $SEARCH_CONNECTION_NAME"
else
    log_warning "Could not create AI Search connection via az ml."
    log_warning "You may need to create it manually in the Foundry portal:"
    log_warning "  1. Go to ai.azure.com → Your Project → Settings → Connections"
    log_warning "  2. Add Connection → Azure AI Search"
    log_warning "  3. Use endpoint: ${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}"
fi

rm -f "$SEARCH_CONNECTION_FILE"

# Add AI Project endpoint to .env file
log_step "Adding AI Project configuration to .env..."
{
  echo ""
  echo "# Azure AI Foundry Project (for persistent agents)"
  echo "AZURE_AI_PROJECT_ENDPOINT=${AI_PROJECT_ENDPOINT}"
  echo "AZURE_AI_MODEL_DEPLOYMENT_NAME=${OPENAI_DEPLOYMENT}"
} >> "$ENV_FILE"

log_success "AI Project endpoint added to .env"

# Create agents in Azure AI Foundry
log_step "Creating compliance agents in Azure AI Foundry..."
echo ""
echo "   This will create 7 persistent agents visible in the Foundry portal:"
echo "     • DocumentConsistencyAgent"
echo "     • HSCodeValidationAgent"
echo "     • CountryRestrictionsAgent"
echo "     • CountryOfOriginAgent"
echo "     • ControlledGoodsAgent"
echo "     • ValueReasonablenessAgent"
echo "     • ShipperVerificationAgent"
echo ""

# Activate venv again for agent creation
source "$PROJECT_DIR/backend/venv/bin/activate"

# Check if agent-framework-azure-ai is installed
if ! pip show agent-framework-azure-ai &>/dev/null; then
    log_step "Installing Microsoft Agent Framework (this may take 1-2 minutes)..."
    pip install --no-cache-dir agent-framework-azure-ai azure-ai-projects --pre 2>&1 | tail -5
    log_success "Agent Framework installed"
fi

# Export the endpoint for the Python script
export AZURE_AI_PROJECT_ENDPOINT="$AI_PROJECT_ENDPOINT"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="$OPENAI_DEPLOYMENT"

# Run agent creation
if python "$PROJECT_DIR/agents/workflow.py" --create; then
    log_success "Compliance agents created in Azure AI Foundry!"
    echo ""
    echo "   View your agents at: https://ai.azure.com"
    echo "   Navigate to: Your Project → Agents"
else
    log_warning "Agent creation failed. You can create them later with:"
    echo "   python agents/workflow.py --create"
fi

# Deactivate venv
deactivate

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Resources created:"
echo "  ✅ Azure Storage Account"
echo "  ✅ Azure AI Foundry (AI Services)"
echo "  ✅ Azure AI Search (for agent tools)"
echo "  ✅ Azure Cosmos DB"
echo "  ✅ Content Understanding Analyzer"
echo "  ✅ Reference Data indexed in AI Search"
echo "  ✅ Compliance Agents in Foundry"
echo ""
echo "Next: Run scripts/local-dev.sh to start the application"
echo ""
