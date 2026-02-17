#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ENDPOINT="${1:-${AZURE_CONTENT_UNDERSTANDING_ENDPOINT:-}}"
ANALYZER_ID="${AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID:-customsDeclaration}"
SCHEMA_FILE="${2:-$PROJECT_DIR/infrastructure/customs-analyzer.json}"
API_VERSION="${AZURE_CONTENT_UNDERSTANDING_API_VERSION:-2025-11-01}"
POLL_MAX_ATTEMPTS="${POLL_MAX_ATTEMPTS:-120}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-2}"
DEBUG_MODE="${DEBUG_MODE:-0}"
CLIENT_REQUEST_ID="${CLIENT_REQUEST_ID:-cu-create-${ANALYZER_ID}-$(date +%Y%m%d%H%M%S)-$$}"

if [ "${3:-}" = "--debug" ]; then
  DEBUG_MODE=1
fi

if [ -z "$ENDPOINT" ]; then
  echo "❌ Missing endpoint. Pass it as arg1 or set AZURE_CONTENT_UNDERSTANDING_ENDPOINT"
  exit 1
fi

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "❌ Schema file not found: $SCHEMA_FILE"
  exit 1
fi

ENDPOINT="${ENDPOINT%/}"

echo "📋 Creating Content Understanding analyzer"
echo "   Endpoint: $ENDPOINT"
echo "   Analyzer: $ANALYZER_ID"
echo "   Schema:   $SCHEMA_FILE"
echo ""
echo "   Client Request ID: $CLIENT_REQUEST_ID"

ACCESS_TOKEN="$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)"
if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Failed to get Azure access token. Run az login"
  exit 1
fi

HEADERS_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"
trap 'rm -f "$HEADERS_FILE" "$BODY_FILE"' EXIT

HTTP_STATUS=$(curl -sS -D "$HEADERS_FILE" -o "$BODY_FILE" -w "%{http_code}" \
  -X PUT "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "x-ms-client-request-id: ${CLIENT_REQUEST_ID}" \
  -H "Content-Type: application/json" \
  --data-binary @"$SCHEMA_FILE")

echo "PUT status: ${HTTP_STATUS}"
if [ "$HTTP_STATUS" != "200" ] && [ "$HTTP_STATUS" != "201" ] && [ "$HTTP_STATUS" != "202" ]; then
  echo "❌ Analyzer create request failed"
  cat "$BODY_FILE"
  if [ "$DEBUG_MODE" = "1" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔎 Diagnostic Details"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Request URL: ${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}?api-version=${API_VERSION}"
    echo "x-ms-client-request-id: ${CLIENT_REQUEST_ID}"
    echo "Response headers:"
    cat "$HEADERS_FILE"
    echo "Response body:"
    cat "$BODY_FILE"
    echo ""
    echo "For Azure Support include:"
    echo "  - UTC time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "  - x-ms-client-request-id: ${CLIENT_REQUEST_ID}"
    echo "  - Endpoint: ${ENDPOINT}"
    echo "  - Analyzer ID: ${ANALYZER_ID}"
  fi
  exit 1
fi

OPERATION_LOCATION=$(grep -i '^Operation-Location:' "$HEADERS_FILE" | sed 's/Operation-Location:[[:space:]]*//I' | tr -d '\r')

if [ -z "$OPERATION_LOCATION" ]; then
  echo "ℹ️ No Operation-Location header returned. Attempting immediate analyzer test..."
  TEST_STATUS=$(curl -sS -o /dev/null -w "%{http_code}" \
    -X POST "${ENDPOINT}/contentunderstanding/analyzers/${ANALYZER_ID}:analyze?api-version=${API_VERSION}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"inputs":[{"url":"https://github.com/Azure-Samples/azure-ai-content-understanding-python/raw/refs/heads/main/data/receipt.png"}]}')

  if [ "$TEST_STATUS" = "202" ]; then
    echo "✅ Analyzer appears available (analyze returned 202)"
    exit 0
  fi

  echo "⚠️ Analyzer create returned success but analyze returned HTTP ${TEST_STATUS}"
  exit 1
fi

echo "Operation-Location: $OPERATION_LOCATION"
echo ""
echo "⏳ Polling analyzer creation operation..."

for attempt in $(seq 1 "$POLL_MAX_ATTEMPTS"); do
  STATUS_BODY=$(curl -sS \
    -X GET "$OPERATION_LOCATION" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "x-ms-client-request-id: ${CLIENT_REQUEST_ID}-poll-${attempt}" \
    -H "Accept: application/json")

  STATUS_VALUE=$(echo "$STATUS_BODY" | python3 - <<'PY'
import json,sys
try:
    data=json.load(sys.stdin)
    status=str(data.get("status","")).lower()
    print(status)
except Exception:
    print("")
PY
)

  if [ "$STATUS_VALUE" = "succeeded" ]; then
    echo "✅ Analyzer creation succeeded"
    exit 0
  fi

  if [ "$STATUS_VALUE" = "failed" ] || [ "$STATUS_VALUE" = "canceled" ]; then
    echo "❌ Analyzer creation failed"
    echo "$STATUS_BODY"
    if [ "$DEBUG_MODE" = "1" ]; then
      echo ""
      echo "For Azure Support include:"
      echo "  - UTC time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "  - x-ms-client-request-id: ${CLIENT_REQUEST_ID}"
      echo "  - Operation-Location: ${OPERATION_LOCATION}"
      echo "  - Status body: ${STATUS_BODY}"
    fi
    exit 1
  fi

  echo "   Attempt ${attempt}/${POLL_MAX_ATTEMPTS}: status=${STATUS_VALUE:-unknown}"
  sleep "$POLL_INTERVAL_SECONDS"
done

echo "❌ Timed out waiting for analyzer creation"
if [ "$DEBUG_MODE" = "1" ]; then
  echo "For Azure Support include:"
  echo "  - UTC time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "  - x-ms-client-request-id: ${CLIENT_REQUEST_ID}"
  echo "  - Operation-Location: ${OPERATION_LOCATION}"
fi
exit 1
