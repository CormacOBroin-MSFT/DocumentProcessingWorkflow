#!/bin/bash
set -e

# Configuration
RESOURCE_GROUP="autonomousflow-rg"
LOCATION="swedencentral"
BASE_NAME="autonomousflow"

echo "🔧 Setting up Azure infrastructure for local development..."
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

# Deploy infrastructure only (no App Service)
echo "🏗️  Deploying Azure resources (this may take 1-2 minutes)..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infrastructure/local-dev.bicep \
  --parameters baseName=$BASE_NAME location=$LOCATION \
  --query properties.outputs -o json)

# Parse outputs
STORAGE_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.storageAccountName.value')
DOCINT_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.documentIntelligenceEndpoint.value')
DOCINT_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.documentIntelligenceName.value')

echo ""
echo "✅ Infrastructure deployed!"
echo ""

# Get current user ID for role assignment
echo "🔑 Retrieving credentials and setting up access..."
USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "")

STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name $STORAGE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query connectionString -o tsv)

# Assign Cognitive Services User role to current user for local development
if [ -n "$USER_OBJECT_ID" ]; then
  echo "   Assigning Cognitive Services User role..."
  az role assignment create \
    --assignee $USER_OBJECT_ID \
    --role "Cognitive Services User" \
    --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$DOCINT_NAME" \
    --output none 2>/dev/null || echo "   (Role may already exist)"
fi

# Note: Document Intelligence key is not needed - we use DefaultAzureCredential
# which uses your Azure CLI login automatically

# Create .env file in backend folder
ENV_FILE="backend/.env"
echo "📝 Creating $ENV_FILE..."

cat > $ENV_FILE << EOF
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONNECTION_STRING
AZURE_STORAGE_CONTAINER=customs-documents

# Azure Document Intelligence (uses Azure CLI credentials - no key needed)
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=$DOCINT_ENDPOINT
# AZURE_DOCUMENT_INTELLIGENCE_KEY= (not needed - uses DefaultAzureCredential)

# OpenAI (add your key here)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Flask
FLASK_ENV=development
FLASK_DEBUG=true
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Resources Created:"
echo "   • Storage Account:       $STORAGE_NAME"
echo "   • Document Intelligence: $DOCINT_NAME"
echo ""
echo "📄 Environment file created: $ENV_FILE"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Add your OpenAI API key to backend/.env:"
echo "   OPENAI_API_KEY=sk-your-key-here"
echo ""
echo "2. Start the backend:"
echo "   cd backend && pip install -r requirements.txt && python run.py"
echo ""
echo "3. Start the frontend (in another terminal):"
echo "   npm run dev"
echo ""
echo "4. Open http://localhost:5173"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 To deploy the full app to Azure later, run: ./deploy.sh"
echo ""
