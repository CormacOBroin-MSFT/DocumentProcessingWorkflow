#!/bin/bash
# Shared function to setup Content Understanding analyzer
# Can be sourced by other scripts or run standalone

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

setup_analyzer() {
    local ENDPOINT="${1:-$AZURE_CONTENT_UNDERSTANDING_ENDPOINT}"
    local ANALYZER_ID="customsDeclaration"
    local API_VERSION="2025-11-01"
    
    if [ -z "$ENDPOINT" ]; then
        echo "❌ AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set"
        return 1
    fi
    
    ENDPOINT="${ENDPOINT%/}"
    
    echo "📋 Setting up Content Understanding analyzer..."
    echo "   Endpoint: $ENDPOINT"
    echo "   Analyzer: $ANALYZER_ID"
    
    # Get access token
    ACCESS_TOKEN=$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)
    
    if [ -z "$ACCESS_TOKEN" ]; then
        echo "❌ Failed to get access token. Run: az login"
        return 1
    fi
    
    # Set Content Understanding model defaults (maps model names to deployment names)
    # Content Understanding requires gpt-4.1, gpt-4.1-mini, and text-embedding-3-large
    # Retry a few times in case deployments are still initializing
    echo "   Setting Content Understanding defaults..."
    
    MAX_RETRIES=5
    RETRY_DELAY=10
    DEFAULTS_SET=false
    
    for i in $(seq 1 $MAX_RETRIES); do
        DEFAULTS_RESPONSE=$(curl -s -w "\n%{http_code}" \
            -X PATCH "${ENDPOINT}/contentunderstanding/defaults?api-version=${API_VERSION}" \
            -H "Authorization: Bearer ${ACCESS_TOKEN}" \
            -H "Content-Type: application/merge-patch+json" \
            -d '{"modelDeployments": {"gpt-4.1": "gpt-41", "gpt-4.1-mini": "gpt-41-mini", "text-embedding-3-large": "text-embedding-3-large"}}')
        
        DEFAULTS_STATUS=$(echo "$DEFAULTS_RESPONSE" | tail -n 1)
        if [ "$DEFAULTS_STATUS" = "200" ] || [ "$DEFAULTS_STATUS" = "201" ]; then
            echo "   ✅ Defaults configured"
            DEFAULTS_SET=true
            break
        else
            DEFAULTS_BODY=$(echo "$DEFAULTS_RESPONSE" | sed '$d')
            if [ $i -lt $MAX_RETRIES ]; then
                echo "   ⚠️  Defaults not ready (attempt $i/$MAX_RETRIES), waiting ${RETRY_DELAY}s..."
                sleep $RETRY_DELAY
            else
                echo "   ❌ Failed to set defaults after $MAX_RETRIES attempts"
                echo "   Response (HTTP $DEFAULTS_STATUS): $DEFAULTS_BODY"
            fi
        fi
    done
    
    if [ "$DEFAULTS_SET" != "true" ]; then
        echo "   ⚠️  Continuing without defaults - analyzer creation may fail"
    fi
    
    # Check if analyzer exists
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X GET "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}")
    
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "✅ Analyzer '${ANALYZER_ID}' already exists"
        return 0
    fi
    
    # Create the analyzer
    echo "   Creating analyzer..."
    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X PUT "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d @"$PROJECT_DIR/infrastructure/customs-analyzer.json")
    
    HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_STATUS" = "201" ] || [ "$HTTP_STATUS" = "202" ] || [ "$HTTP_STATUS" = "200" ]; then
        echo "✅ Analyzer created successfully!"
        return 0
    else
        echo "❌ Failed to create analyzer (HTTP $HTTP_STATUS)"
        echo "$BODY"
        return 1
    fi
}

# Run if executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -e
    setup_analyzer "$1"
fi
