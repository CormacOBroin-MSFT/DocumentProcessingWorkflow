#!/bin/bash
# Update Content Understanding analyzer with improved field descriptions

ANALYZER_ID="customsDeclaration"
API_VERSION="2025-11-01"

if [ -z "$AZURE_CONTENT_UNDERSTANDING_ENDPOINT" ]; then
    echo "❌ AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set"
    exit 1
fi

ENDPOINT="${AZURE_CONTENT_UNDERSTANDING_ENDPOINT%/}"

echo "🔄 Updating Content Understanding analyzer with improved field descriptions..."
echo "   Endpoint: $ENDPOINT"
echo "   Analyzer: $ANALYZER_ID"

# Get access token
ACCESS_TOKEN=$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get access token. Run: az login"
    exit 1
fi

# Delete existing analyzer
echo "   Deleting existing analyzer..."
DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X DELETE "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

DELETE_STATUS=$(echo "$DELETE_RESPONSE" | tail -n 1)
if [ "$DELETE_STATUS" = "204" ] || [ "$DELETE_STATUS" = "404" ]; then
    echo "   ✅ Analyzer deleted (or didn't exist)"
else
    DELETE_BODY=$(echo "$DELETE_RESPONSE" | sed '$d')
    echo "   ⚠️  Delete response (HTTP $DELETE_STATUS): $DELETE_BODY"
fi

# Wait a moment for deletion to complete
sleep 2

# Create updated analyzer
echo "   Creating analyzer with improved descriptions..."
CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X PUT "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @infrastructure/customs-analyzer.json)

CREATE_STATUS=$(echo "$CREATE_RESPONSE" | tail -n 1)
CREATE_BODY=$(echo "$CREATE_RESPONSE" | sed '$d')

if [ "$CREATE_STATUS" = "201" ] || [ "$CREATE_STATUS" = "202" ] || [ "$CREATE_STATUS" = "200" ]; then
    echo "✅ Analyzer updated successfully with improved HS code and country of origin descriptions!"
else
    echo "❌ Failed to create updated analyzer (HTTP $CREATE_STATUS)"
    echo "$CREATE_BODY"
    exit 1
fi