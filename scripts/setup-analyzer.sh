#!/bin/bash
# Shared function to setup Content Understanding analyzer
# Can be sourced by other scripts or run standalone

if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

setup_analyzer() {
    local ENDPOINT="${1:-${AZURE_CONTENT_UNDERSTANDING_ENDPOINT:-}}"
    local REPLACE_EXISTING="${2:-false}"
    local ANALYZER_ID="customsDeclaration"
    local API_VERSION="2025-11-01"
    local ACCESS_TOKEN DEFAULTS_RESPONSE DEFAULTS_STATUS DEFAULTS_BODY
    local DEFAULTS_SET=false
    local HTTP_STATUS RESPONSE BODY ANALYZER_RESPONSE ANALYZER_STATUS
    local MAX_RETRIES=5 RETRY_DELAY=10 i
    
    if [ -z "$ENDPOINT" ]; then
        echo "❌ AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set"
        return 1
    fi

    for command_name in az curl python3; do
        if ! command -v "$command_name" &>/dev/null; then
            echo "❌ Required command not found: $command_name"
            return 1
        fi
    done

    if [ ! -s "$PROJECT_DIR/infrastructure/customs-analyzer.json" ]; then
        echo "❌ Analyzer definition not found"
        return 1
    fi
    
    ENDPOINT="${ENDPOINT%/}"
    
    echo "📋 Setting up Content Understanding analyzer..."
    echo "   Endpoint: $ENDPOINT"
    echo "   Analyzer: $ANALYZER_ID"
    
    # Get access token
    ACCESS_TOKEN=$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv) || return 1
    
    if [ -z "$ACCESS_TOKEN" ]; then
        echo "❌ Failed to get access token. Run: az login"
        return 1
    fi
    
    # Set Content Understanding model defaults (maps model names to deployment names)
    # Content Understanding requires gpt-4.1, gpt-4.1-mini, and text-embedding-3-large
    # Retry a few times in case deployments are still initializing
    echo "   Setting Content Understanding defaults..."
    
    for ((i = 1; i <= MAX_RETRIES; i++)); do
        DEFAULTS_RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
            -X PATCH "${ENDPOINT}/contentunderstanding/defaults?api-version=${API_VERSION}" \
            -H "Authorization: Bearer ${ACCESS_TOKEN}" \
            -H "Content-Type: application/merge-patch+json" \
            -d '{"modelDeployments": {"gpt-4.1": "gpt-41", "gpt-4.1-mini": "gpt-41-mini", "text-embedding-3-large": "text-embedding-3-large"}}') || return 1
        
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
        echo "❌ Content Understanding defaults are required"
        return 1
    fi

    ANALYZER_RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
        -X GET "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}") || return 1
    HTTP_STATUS=$(echo "$ANALYZER_RESPONSE" | tail -n 1)

    if [ "$HTTP_STATUS" = "200" ]; then
        BODY=$(echo "$ANALYZER_RESPONSE" | sed '$d')
        ANALYZER_STATUS=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "").lower())' <<< "$BODY") || return 1
        if [ "$REPLACE_EXISTING" != "true" ]; then
            if [ "$ANALYZER_STATUS" = "ready" ]; then
                echo "✅ Analyzer '${ANALYZER_ID}' already exists and is ready"
                return 0
            fi
            if [ "$ANALYZER_STATUS" = "failed" ]; then
                echo "❌ Existing analyzer is in a failed state. Run scripts/update-analyzer.sh to replace it."
                return 1
            fi
            echo "   Analyzer status is '${ANALYZER_STATUS:-unknown}'; waiting for it to become ready..."
        else
            echo "   Deleting existing analyzer before replacement..."
            HTTP_STATUS=$(curl --silent --show-error --output /dev/null --write-out "%{http_code}" \
                -X DELETE "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
                -H "Authorization: Bearer ${ACCESS_TOKEN}") || return 1
            if [ "$HTTP_STATUS" != "202" ] && [ "$HTTP_STATUS" != "204" ]; then
                echo "❌ Failed to delete existing analyzer (HTTP $HTTP_STATUS)"
                return 1
            fi
            for ((i = 1; i <= 30; i++)); do
                HTTP_STATUS=$(curl --silent --show-error --output /dev/null --write-out "%{http_code}" \
                    -X GET "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
                    -H "Authorization: Bearer ${ACCESS_TOKEN}") || return 1
                if [ "$HTTP_STATUS" = "404" ]; then
                    break
                fi
                if [ "$i" -eq 30 ]; then
                    echo "❌ Existing analyzer was not deleted within 60 seconds"
                    return 1
                fi
                sleep 2
            done
        fi
    elif [ "$HTTP_STATUS" != "404" ]; then
        echo "❌ Could not inspect analyzer (HTTP $HTTP_STATUS)"
        echo "$(echo "$ANALYZER_RESPONSE" | sed '$d')"
        return 1
    fi

    if [ "$HTTP_STATUS" = "200" ] && [ "$REPLACE_EXISTING" != "true" ]; then
        for ((i = 1; i <= 30; i++)); do
            ANALYZER_RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
                -X GET "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
                -H "Authorization: Bearer ${ACCESS_TOKEN}") || return 1
            HTTP_STATUS=$(echo "$ANALYZER_RESPONSE" | tail -n 1)
            if [ "$HTTP_STATUS" = "200" ]; then
                BODY=$(echo "$ANALYZER_RESPONSE" | sed '$d')
                ANALYZER_STATUS=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "").lower())' <<< "$BODY") || return 1
                if [ "$ANALYZER_STATUS" = "ready" ]; then
                    echo "✅ Analyzer '${ANALYZER_ID}' is ready"
                    return 0
                fi
                if [ "$ANALYZER_STATUS" = "failed" ]; then
                    echo "❌ Analyzer provisioning failed: $BODY"
                    return 1
                fi
            fi
            sleep 2
        done
        echo "❌ Analyzer did not become ready within 60 seconds"
        return 1
    fi
    
    echo "   Applying analyzer definition..."
    RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
        -X PUT "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d @"$PROJECT_DIR/infrastructure/customs-analyzer.json") || return 1
    
    HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_STATUS" = "201" ] || [ "$HTTP_STATUS" = "202" ] || [ "$HTTP_STATUS" = "200" ]; then
        for ((i = 1; i <= 30; i++)); do
            ANALYZER_RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
                -X GET "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
                -H "Authorization: Bearer ${ACCESS_TOKEN}") || return 1
            HTTP_STATUS=$(echo "$ANALYZER_RESPONSE" | tail -n 1)
            if [ "$HTTP_STATUS" = "200" ]; then
                BODY=$(echo "$ANALYZER_RESPONSE" | sed '$d')
                ANALYZER_STATUS=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "").lower())' <<< "$BODY") || return 1
                if [ "$ANALYZER_STATUS" = "ready" ]; then
                    echo "✅ Analyzer '${ANALYZER_ID}' is ready"
                    return 0
                fi
                if [ "$ANALYZER_STATUS" = "failed" ]; then
                    echo "❌ Analyzer provisioning failed: $BODY"
                    return 1
                fi
            fi
            sleep 2
        done
        echo "❌ Analyzer did not become ready within 60 seconds"
        return 1
    else
        echo "❌ Failed to create analyzer (HTTP $HTTP_STATUS)"
        echo "$BODY"
        return 1
    fi
}

# Run if executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    setup_analyzer "${1:-}"
fi
