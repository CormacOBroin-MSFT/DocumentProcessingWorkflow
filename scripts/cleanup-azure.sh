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

echo "⚠️  This will DELETE all resources in '$RESOURCE_GROUP':"
echo "   • Storage Account"
echo "   • AI Services (Content Understanding)"
echo ""
read -p "Are you sure? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🗑️  Deleting resource group '$RESOURCE_GROUP'..."
az group delete --name $RESOURCE_GROUP --yes --no-wait

echo "⏳ Waiting for resource group deletion..."
az group wait --name $RESOURCE_GROUP --deleted 2>/dev/null || true

# Purge AI Services to avoid soft-delete issues on next deploy
echo "🧹 Purging AI Services (avoiding soft-delete)..."
az cognitiveservices account purge \
    --name $AI_SERVICES_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION 2>/dev/null || true

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "💡 Run scripts/setup-azure.sh to recreate resources."
