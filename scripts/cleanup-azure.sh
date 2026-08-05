#!/bin/bash
set -e

RESOURCE_GROUP="autonomousflow-rg"
LOCATION="swedencentral"
AI_SERVICES_NAME="autonomousflow-foundry"

echo "🧹 Cleaning up Azure resources..."
echo ""

# Check if logged in
if ! az account show &>/dev/null; then
    echo "❌ Not logged in to Azure. Run: az login"
    exit 1
fi

# Check if resource group exists
if ! az group show --name $RESOURCE_GROUP &>/dev/null; then
    echo "ℹ️  Resource group '$RESOURCE_GROUP' does not exist. Nothing to clean up."
    exit 0
fi

AI_LOCATION=$(az cognitiveservices account show \
    --name "$AI_SERVICES_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query location -o tsv 2>/dev/null || true)

echo "⚠️  This will DELETE all resources in '$RESOURCE_GROUP':"
echo "   • Storage Account"
echo "   • AI Services (Content Understanding)"
echo "   • Azure AI Search (and indexed data)"
echo ""
read -p "Are you sure? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🗑️  Deleting resource group '$RESOURCE_GROUP'..."
az group delete --name $RESOURCE_GROUP --yes

if [ -n "$AI_LOCATION" ]; then
    echo "🧹 Purging AI Services (avoiding soft-delete)..."
    az cognitiveservices account purge \
        --name "$AI_SERVICES_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$AI_LOCATION"
fi

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "💡 Run scripts/setup-azure.sh to recreate resources."
