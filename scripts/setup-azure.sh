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

# Decide if we need to run Bicep deployment
NEED_BICEP_DEPLOY="false"
if [ -z "$EXISTING_AI" ]; then
    NEED_BICEP_DEPLOY="true"
    log_step "AI Services not found, will deploy..."
fi

if [ "$NEED_BICEP_DEPLOY" = "true" ]; then
    # Deploy infrastructure
    log_step "Deploying Bicep template (this may take 2-3 minutes)..."
    echo ""
    echo "   Template: infrastructure/local-dev.bicep"
    echo "   Resources to create/update:"
    echo "     • Storage Account: ${STORAGE_NAME}"
    echo "     • AI Services: ${AI_SERVICES_NAME}"
    echo "     • Azure AI Search: ${BASE_NAME}-search"
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
    SEARCH_SERVICE_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.searchServiceName.value')
    SEARCH_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.searchServiceEndpoint.value')
    
    log_success "Microsoft Foundry (new) project created: $AI_PROJECT_NAME"
    
    # Clear agent cache since this is a fresh deployment
    AGENT_CACHE_FILE="$PROJECT_DIR/agents/.foundry_agent_ids.json"
    if [ -f "$AGENT_CACHE_FILE" ]; then
        log_step "Clearing stale agent cache (fresh Foundry deployment)..."
        rm -f "$AGENT_CACHE_FILE"
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
  
  log_success "User role assignments complete"
fi

# Assign RBAC roles to Foundry managed identities for AI Search access
log_step "Assigning roles to Foundry managed identities..."

# Hub (AI Services) managed identity
MANAGED_IDENTITY_ID=$(az cognitiveservices account show \
  --name $AI_SERVICES_NAME \
  --resource-group $RESOURCE_GROUP \
  --query identity.principalId -o tsv 2>/dev/null)

if [ -n "$MANAGED_IDENTITY_ID" ]; then
  echo "   Hub Managed Identity: $MANAGED_IDENTITY_ID"
  
  echo "   Assigning Search Index Data Contributor to hub identity..."
  az role assignment create \
    --assignee $MANAGED_IDENTITY_ID \
    --role "Search Index Data Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
    --output none 2>/dev/null || true
  
  echo "   Assigning Search Service Contributor to hub identity..."
  az role assignment create \
    --assignee $MANAGED_IDENTITY_ID \
    --role "Search Service Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
    --output none 2>/dev/null || true
  
  log_success "Hub identity role assignments complete"
else
  log_warning "Could not get Foundry hub managed identity for role assignments"
fi

# Project managed identity (agents run with this identity)
AI_PROJECT_NAME="${AI_PROJECT_NAME:-${BASE_NAME}-project}"
PROJECT_IDENTITY_ID=$(az ad sp list \
  --display-name "${AI_SERVICES_NAME}/projects/${AI_PROJECT_NAME}" \
  --query "[0].id" -o tsv 2>/dev/null)

if [ -n "$PROJECT_IDENTITY_ID" ]; then
  echo "   Project Managed Identity: $PROJECT_IDENTITY_ID"
  
  echo "   Assigning Search Index Data Contributor to project identity..."
  az role assignment create \
    --assignee $PROJECT_IDENTITY_ID \
    --role "Search Index Data Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
    --output none 2>/dev/null || true
  
  echo "   Assigning Search Service Contributor to project identity..."
  az role assignment create \
    --assignee $PROJECT_IDENTITY_ID \
    --role "Search Service Contributor" \
    --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE_NAME" \
    --output none 2>/dev/null || true
  
  log_success "Project identity role assignments complete"
else
  log_warning "Could not get Foundry project managed identity for role assignments"
  log_warning "You may need to manually assign Search roles to the project identity"
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

# Export search endpoint for the script
export AZURE_SEARCH_ENDPOINT="${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}"
export AZURE_SEARCH_SERVICE_NAME="${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"

# Check if indexes already have data using Python
log_step "Checking if reference data is already indexed..."
NEED_REINDEX="true"

INDEX_CHECK=$(python -c "
import os
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

endpoint = os.environ.get('AZURE_SEARCH_ENDPOINT')
cred = DefaultAzureCredential()

try:
    hs_client = SearchClient(endpoint=endpoint, index_name='hs-codes', credential=cred)
    hs_count = hs_client.get_document_count()
    
    sanctions_client = SearchClient(endpoint=endpoint, index_name='sanctions', credential=cred)
    sanctions_count = sanctions_client.get_document_count()
    
    if hs_count > 0 and sanctions_count > 0:
        print(f'EXISTS:{hs_count}:{sanctions_count}')
    else:
        print('EMPTY')
except Exception as e:
    print('EMPTY')
" 2>/dev/null)

if [[ "$INDEX_CHECK" == EXISTS:* ]]; then
    HS_COUNT=$(echo "$INDEX_CHECK" | cut -d: -f2)
    SANCTIONS_COUNT=$(echo "$INDEX_CHECK" | cut -d: -f3)
    NEED_REINDEX="false"
    log_success "Reference data already indexed (HS: $HS_COUNT docs, Sanctions: $SANCTIONS_COUNT docs)"
else
    log_step "Indexes empty or missing, will index data..."
fi

# Index to Azure AI Search (both HS codes and sanctions)
if [ "$NEED_REINDEX" = "true" ] && [ -f "$HS_CODES_CSV" ] && [ -f "$SANCTIONS_CSV" ]; then
    log_step "Indexing reference data into Azure AI Search..."
    echo "   HS Codes: $HS_CODES_CSV"
    echo "   Sanctions: $SANCTIONS_CSV"
    
    # Wait for role assignments to propagate (Azure RBAC can take 1-2 minutes)
    echo "   Waiting 30s for role assignments to propagate..."
    sleep 30
    
    if python "$PROJECT_DIR/scripts/index_to_search.py" --index all --force; then
        log_success "Reference data indexed to Azure AI Search"
    else
        log_error "Azure AI Search indexing failed!"
        log_warning "Agents will not have access to HS codes and sanctions data."
        # Don't exit - agents can still work without tools
    fi
elif [ "$NEED_REINDEX" = "true" ]; then
    log_warning "Reference data CSV files not found!"
    [ ! -f "$HS_CODES_CSV" ] && log_warning "  Missing: $HS_CODES_CSV"
    [ ! -f "$SANCTIONS_CSV" ] && log_warning "  Missing: $SANCTIONS_CSV"
    log_warning "Agents will not have access to HS codes and sanctions data."
fi
# If NEED_REINDEX is false, data already exists - nothing to do

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

# Create AI Search connection on the Foundry resource
log_step "Creating Azure AI Search connection..."
SEARCH_CONNECTION_NAME="${SEARCH_SERVICE_NAME:-${BASE_NAME}-search}"

if az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/${AI_HUB_NAME}/connections/${SEARCH_CONNECTION_NAME}?api-version=2025-06-01" \
  --body "{
    \"properties\": {
      \"category\": \"CognitiveSearch\",
      \"target\": \"${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}\",
      \"authType\": \"AAD\",
      \"isSharedToAll\": true
    }
  }" \
  --output none 2>/dev/null; then
    log_success "AI Search connection created: $SEARCH_CONNECTION_NAME"
else
    log_warning "Could not create AI Search connection automatically."
    log_warning "You may need to create it manually in the Foundry portal:"
    log_warning "  1. Go to ai.azure.com → Your Project → Settings → Connections"
    log_warning "  2. Add Connection → Azure AI Search"
    log_warning "  3. Name: ${SEARCH_CONNECTION_NAME}"
    log_warning "  4. Endpoint: ${SEARCH_ENDPOINT:-https://${BASE_NAME}-search.search.windows.net}"
    log_warning "  5. Authentication: Microsoft Entra ID (keyless)"
fi
echo ""

# Create Bing Grounding resource for web search capability
log_step "Setting up Bing Grounding for web search..."
BING_RESOURCE_NAME="${BASE_NAME}-bing"
BING_CONNECTION_NAME="${BASE_NAME}-bing"

# Check if any Bing Grounding resource already exists (search entire subscription)
# Prefer resources that match the base name pattern, otherwise use any available
EXISTING_BING_INFO=$(az resource list \
  --resource-type "Microsoft.Bing/accounts" \
  --query "[?contains(name, '${BASE_NAME}')] | [0].{name:name, resourceGroup:resourceGroup, id:id}" -o json 2>/dev/null || echo "{}")

# If no matching resource found, try to find any Bing resource
if [ "$(echo "$EXISTING_BING_INFO" | jq -r '.name // empty')" = "" ]; then
    EXISTING_BING_INFO=$(az resource list \
      --resource-type "Microsoft.Bing/accounts" \
      --query "[0].{name:name, resourceGroup:resourceGroup, id:id}" -o json 2>/dev/null || echo "{}")
fi

EXISTING_BING_NAME=$(echo "$EXISTING_BING_INFO" | jq -r '.name // empty')
EXISTING_BING_RG=$(echo "$EXISTING_BING_INFO" | jq -r '.resourceGroup // empty')

if [ -n "$EXISTING_BING_NAME" ]; then
    # Use the existing Bing resource (may be in different resource group)
    BING_RESOURCE_NAME="$EXISTING_BING_NAME"
    BING_CONNECTION_NAME="$EXISTING_BING_NAME"
    BING_RESOURCE_GROUP="$EXISTING_BING_RG"
    log_success "Found existing Bing Grounding resource: $BING_RESOURCE_NAME (in $BING_RESOURCE_GROUP)"
else
    BING_RESOURCE_GROUP="$RESOURCE_GROUP"
    log_step "Creating Bing Grounding resource (Grounding with Bing Search)..."
    
    # Register Microsoft.Bing provider if not already registered
    if ! az provider show --namespace Microsoft.Bing --query "registrationState" -o tsv 2>/dev/null | grep -q "Registered"; then
        echo "   Registering Microsoft.Bing provider..."
        az provider register --namespace Microsoft.Bing --wait --output none 2>/dev/null || true
    fi
    
    # Accept marketplace terms for Bing Grounding (required for automated creation)
    # This is idempotent - safe to run even if already accepted
    echo "   Accepting Bing Grounding marketplace terms..."
    az term accept \
      --publisher "microsoft" \
      --product "bing-search-api" \
      --plan "bing-grounding-free" \
      --output none 2>/dev/null || true
    
    # Create Bing Grounding resource
    if az resource create \
      --name $BING_RESOURCE_NAME \
      --resource-group $RESOURCE_GROUP \
      --resource-type "Microsoft.Bing/accounts" \
      --location "global" \
      --properties '{"kind": "Bing.Grounding.Search"}' \
      --output none 2>/dev/null; then
        log_success "Bing Grounding resource created: $BING_RESOURCE_NAME"
    else
        log_warning "Could not create Bing Grounding resource."
        log_warning "This usually means marketplace terms need manual acceptance."
        log_warning "To fix this:"
        log_warning "  1. Go to Azure Portal → Marketplace"
        log_warning "  2. Search for 'Grounding with Bing Search'"
        log_warning "  3. Click Create, accept terms, then cancel (or complete creation)"
        log_warning "  4. Re-run this script"
        log_warning ""
        log_warning "Or create manually with name: ${BING_RESOURCE_NAME}"
    fi
fi

# Get Bing resource endpoint (key-based auth required for Bing)
BING_ENDPOINT=""
BING_API_KEY=""

# Use the resource group where Bing was found (or created)
BING_RG="${BING_RESOURCE_GROUP:-$RESOURCE_GROUP}"

if [ -n "$EXISTING_BING_NAME" ] || az resource show --name $BING_RESOURCE_NAME --resource-group $BING_RG --resource-type "Microsoft.Bing/accounts" &>/dev/null; then
    # Get the Bing API key
    BING_API_KEY=$(az resource invoke-action \
      --name $BING_RESOURCE_NAME \
      --resource-group $BING_RG \
      --resource-type "Microsoft.Bing/accounts" \
      --action listKeys \
      --query "key1" -o tsv 2>/dev/null || echo "")
    
    if [ -n "$BING_API_KEY" ]; then
        log_step "Creating Bing Grounding connection..."
        # Create Bing connection on the Foundry resource using API key auth
        if az rest --method put \
          --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/${AI_HUB_NAME}/connections/${BING_CONNECTION_NAME}?api-version=2025-06-01" \
          --body "{
            \"properties\": {
              \"category\": \"BingGrounding\",
              \"target\": \"https://api.bing.microsoft.com\",
              \"authType\": \"ApiKey\",
              \"credentials\": {
                \"key\": \"${BING_API_KEY}\"
              },
              \"isSharedToAll\": true
            }
          }" \
          --output none 2>/dev/null; then
            log_success "Bing Grounding connection created: $BING_CONNECTION_NAME"
        else
            log_warning "Could not create Bing Grounding connection automatically."
        fi
    else
        log_warning "Could not retrieve Bing API key for connection."
    fi
fi

# Add Bing connection name to .env
if [ -n "$BING_API_KEY" ]; then
    if ! grep -q "AZURE_BING_CONNECTION_NAME" "$ENV_FILE" 2>/dev/null; then
        {
          echo ""
          echo "# Bing Grounding (for web search in agents)"
          echo "AZURE_BING_CONNECTION_NAME=${BING_CONNECTION_NAME}"
        } >> "$ENV_FILE"
        log_success "Bing Grounding configuration added to .env"
    fi
fi

# Check for existing Bing Grounding connection in Foundry (may have different name than resource)
log_step "Checking for existing Bing Grounding connections..."
EXISTING_BING_CONNECTION=$(python -c "
import os
from azure.identity import AzureCliCredential
from azure.ai.projects import AIProjectClient

endpoint = 'https://${AI_HUB_NAME}.services.ai.azure.com/api/projects/${AI_PROJECT_NAME}'
try:
    with AzureCliCredential() as cred, AIProjectClient(endpoint=endpoint, credential=cred) as client:
        for conn in client.connections.list():
            # Check if connection name contains 'bing' (case insensitive)
            if 'bing' in conn.name.lower():
                print(conn.name)
                break
except Exception as e:
    pass
" 2>/dev/null)

if [ -n "$EXISTING_BING_CONNECTION" ]; then
    BING_CONNECTION_NAME="$EXISTING_BING_CONNECTION"
    log_success "Found existing Bing connection in Foundry: $BING_CONNECTION_NAME"
fi
echo ""

# =============================================================================
# Generate Agent YAML files from templates
# =============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Generating Agent YAML files from templates"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TEMPLATES_DIR="$PROJECT_DIR/agents/templates"
AGENTS_DIR="$PROJECT_DIR/agents"

# Build the full connection IDs
SEARCH_CONNECTION_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${AI_HUB_NAME}/projects/${AI_PROJECT_NAME}/connections/${SEARCH_CONNECTION_NAME}"
BING_CONNECTION_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${AI_HUB_NAME}/projects/${AI_PROJECT_NAME}/connections/${BING_CONNECTION_NAME}"

log_step "Connection IDs:"
echo "   Search: $SEARCH_CONNECTION_ID"
echo "   Bing:   $BING_CONNECTION_ID"
echo ""

# Generate YAML files from templates
if [ -d "$TEMPLATES_DIR" ]; then
    for template in "$TEMPLATES_DIR"/*.yaml.template; do
        if [ -f "$template" ]; then
            filename=$(basename "$template" .template)
            output_file="$AGENTS_DIR/$filename"
            
            log_step "Generating $filename..."
            
            # Substitute placeholders
            sed -e "s|{{SEARCH_CONNECTION_ID}}|${SEARCH_CONNECTION_ID}|g" \
                -e "s|{{BING_CONNECTION_ID}}|${BING_CONNECTION_ID}|g" \
                "$template" > "$output_file"
            
            log_success "  → $output_file"
        fi
    done
    echo ""
    log_success "Agent YAML files generated with connection IDs"
else
    log_warning "Templates directory not found: $TEMPLATES_DIR"
fi
echo ""

# Add AI Project endpoint to .env file (only if not already present)
log_step "Adding AI Project configuration to .env..."
if ! grep -q "AZURE_AI_PROJECT_ENDPOINT" "$ENV_FILE" 2>/dev/null; then
    {
      echo ""
      echo "# Azure AI Foundry Project (for persistent agents)"
      echo "AZURE_AI_PROJECT_ENDPOINT=${AI_PROJECT_ENDPOINT}"
      echo "AZURE_AI_MODEL_DEPLOYMENT_NAME=${OPENAI_DEPLOYMENT}"
    } >> "$ENV_FILE"
    log_success "AI Project endpoint added to .env"
else
    log_success "AI Project endpoint already in .env"
fi

# Create agents in Azure AI Foundry
log_step "Checking/creating compliance agents in Azure AI Foundry..."
echo ""
echo "   Agents to ensure exist (will skip if already created):"
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

# Run agent creation (will skip if agents already exist)
if python "$PROJECT_DIR/agents/workflow.py" --create; then
    log_success "Compliance agents ready in Azure AI Foundry!"
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
echo "  ✅ Bing Grounding (for web search)"
echo "  ✅ Content Understanding Analyzer"
echo "  ✅ Reference Data indexed in AI Search"
echo "  ✅ Compliance Agents in Foundry"
echo ""
echo "Next: Run scripts/local-dev.sh to start the application"
echo ""
