#!/bin/bash
set -e

# Configuration
RESOURCE_GROUP="autonomousflow-rg"
LOCATION="swedencentral"
BASE_NAME="autonomousflow"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source shared functions
source "$SCRIPT_DIR/scripts/setup-analyzer.sh"

echo "🚀 Deploying AutonomousFlow to Azure..."
echo ""

# Check if logged in
if ! az account show &>/dev/null; then
    echo "❌ Not logged in to Azure. Run: az login"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo "📋 Using subscription: $SUBSCRIPTION"
echo ""

# Create resource group
echo "📦 Creating resource group '$RESOURCE_GROUP' in '$LOCATION'..."
az group create --name $RESOURCE_GROUP --location $LOCATION --output none

# Deploy infrastructure
echo "🏗️  Deploying Azure resources (this may take 2-3 minutes)..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infrastructure/app-service.bicep \
  --parameters baseName=$BASE_NAME location=$LOCATION \
  --query properties.outputs -o json)

# Parse outputs
APP_URL=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServiceUrl.value')
APP_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServiceName.value')
STORAGE_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.storageAccountName.value')
KV_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.keyVaultName.value')
CU_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.contentUnderstandingEndpoint.value')

echo ""
echo "✅ Infrastructure deployed!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Resources Created:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   App Service:             $APP_NAME"
echo "   Storage Account:         $STORAGE_NAME"  
echo "   Key Vault:               $KV_NAME"
echo "   Content Understanding:   $CU_ENDPOINT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Setup Content Understanding analyzer
setup_analyzer "$CU_ENDPOINT"

# Build and deploy the application
echo "🔨 Building application..."

# Build frontend
npm ci
npm run build

# Prepare deployment package
echo "📦 Creating deployment package..."
mkdir -p backend/static
cp -r dist/* backend/static/

cd backend
zip -r ../deploy.zip . -x "*.pyc" -x "__pycache__/*" -x "venv/*" -x ".env" -x "*.log"
cd ..

# Deploy to App Service
echo "🚢 Deploying to App Service..."
az webapp deploy \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --src-path deploy.zip \
  --type zip \
  --async true

# Cleanup
rm -f deploy.zip
rm -rf backend/static

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Application URL: $APP_URL"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Add your OpenAI API key to Key Vault:"
echo ""
echo "   az keyvault secret set \\"
echo "     --vault-name $KV_NAME \\"
echo "     --name OPENAI-API-KEY \\"
echo "     --value 'sk-your-key-here'"
echo ""
echo "2. (Optional) View logs:"
echo ""
echo "   az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
