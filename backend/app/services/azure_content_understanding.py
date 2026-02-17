"""
Azure AI Content Understanding Service
Analyzes customs declaration documents using a custom Content Understanding analyzer.

The custom analyzer extracts 7 customs fields directly from the document.
Set AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID in .env (created by setup-azure.sh).
"""
import logging
import os
from typing import Any, Dict, Optional

from azure.identity import DefaultAzureCredential
from app.config import config
from app.services.content_understanding_client import ContentUnderstandingClient

logger = logging.getLogger("autonomousflow.content_understanding")

ANALYZER_ID = os.getenv("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID")
if not ANALYZER_ID:
    raise ValueError(
        "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID is not set. "
        "Run ./scripts/setup-azure.sh to create the custom analyzer and generate backend/.env."
    )

# Our target customs fields
CUSTOMS_FIELDS = ["shipper", "receiver", "goodsDescription", "value", "countryOfOrigin", "hsCode", "weight"]


def _token_provider() -> str:
    """Get a bearer token using Azure CLI credentials."""
    credential = DefaultAzureCredential(
        exclude_managed_identity_credential=True,
        exclude_shared_token_cache_credential=True,
    )
    return credential.get_token("https://cognitiveservices.azure.com/.default").token


def _build_client() -> ContentUnderstandingClient:
    """Build a ContentUnderstandingClient from environment config."""
    endpoint = config.AZURE_CONTENT_UNDERSTANDING_ENDPOINT
    if not endpoint:
        raise ValueError("AZURE_CONTENT_UNDERSTANDING_ENDPOINT not configured")

    key = config.AZURE_CONTENT_UNDERSTANDING_KEY
    return ContentUnderstandingClient(
        endpoint=endpoint,
        subscription_key=key if key else None,
        token_provider=_token_provider if not key else None,
    )


class AzureContentUnderstandingService:
    """Service for document analysis using Azure AI Content Understanding."""

    def __init__(self):
        self.client = _build_client()

    def analyze_document(self, blob_url: str) -> Dict[str, Any]:
        """
        Analyze a document and extract customs declaration fields.

        Args:
            blob_url: URL of the document in Azure Blob Storage (CU accesses via managed identity).

        Returns:
            Dict with structured_data, raw_data, ocr_confidence, fields_extracted, total_fields.
        """
        logger.info(f"Analyzing document with analyzer '{ANALYZER_ID}'")

        # 1. Submit for analysis
        response = self.client.begin_analyze(ANALYZER_ID, blob_url)

        # 2. Poll until complete
        result = self.client.poll_result(response)

        # 3. Extract and map fields
        contents = result.get("result", {}).get("contents", [])
        if not contents:
            raise ValueError("No content returned from Content Understanding")

        content = contents[0]
        fields = content.get("fields", {})
        logger.info(f"Fields returned: {list(fields.keys())}")

        return self._map_custom_fields(fields, content)

    # ── Custom analyzer field mapping (direct) ─────────────────

    def _map_custom_fields(self, fields: Dict[str, Any], content: Dict) -> Dict[str, Any]:
        """Map custom analyzer fields (1:1 with our schema)."""
        field_map = {}
        for name in CUSTOMS_FIELDS:
            field = fields.get(name, {})
            field_map[name] = (self._read_field_value(field), self._confidence(field))
        return self._build_result(field_map, content)

    # ── Shared result builder ─────────────────────────────────────

    def _build_result(self, field_map: Dict[str, tuple], content: Dict) -> Dict[str, Any]:
        """Build the standard result dict from a field_map of {name: (value, confidence)}."""
        structured_data = {}
        raw_data = {}
        confidences = []
        extracted_count = 0

        for name in CUSTOMS_FIELDS:
            value, confidence = field_map.get(name, ("", 0.0))
            structured_data[name] = {"value": value, "confidence": confidence}
            if value.strip():
                extracted_count += 1
                if confidence > 0:
                    confidences.append(confidence)
                raw_data[name] = {"value": value, "confidence": confidence}

        # Also grab any key-value pairs from the document
        for kv in content.get("keyValuePairs", []):
            key = kv.get("key", {}).get("content", "")
            val = kv.get("value", {}).get("content", "")
            if key and val:
                raw_data[key] = {"value": val, "confidence": kv.get("confidence", 0.8)}

        overall = sum(confidences) / len(confidences) if confidences else 0.0

        result_data = {
            "structured_data": structured_data,
            "raw_data": raw_data,
            "ocr_confidence": overall,
            "fields_extracted": extracted_count,
            "total_fields": len(CUSTOMS_FIELDS),
        }

        if extracted_count == 0:
            result_data["extraction_warning"] = (
                "Document analyzed but no customs fields identified. "
                "You can continue and enter values manually."
            )
        elif extracted_count < len(CUSTOMS_FIELDS) // 2:
            result_data["extraction_warning"] = (
                f"Only {extracted_count}/{len(CUSTOMS_FIELDS)} fields extracted. "
                "Some information may need manual entry."
            )

        return result_data

    # ── Field value readers ───────────────────────────────────────

    @staticmethod
    def _read_field_value(field: Optional[Dict]) -> str:
        """Read value from any typed CU field."""
        if not field:
            return ""
        t = field.get("type", "")
        if t == "string":
            return field.get("valueString", "")
        if t == "number":
            n = field.get("valueNumber")
            return str(n) if n is not None else ""
        if t == "date":
            return field.get("valueDate", "")
        # Generic fallbacks
        for key in ("value", "content"):
            if key in field:
                return str(field[key])
        return ""

    @staticmethod
    def _confidence(field: Optional[Dict]) -> float:
        if not field:
            return 0.0
        return field.get("confidence", 0.0)

def get_content_understanding_service() -> Optional[AzureContentUnderstandingService]:
    """Factory function to get Content Understanding service instance."""
    try:
        return AzureContentUnderstandingService()
    except Exception as e:
        logger.error(f"Could not initialize Content Understanding service: {e}")
        return None