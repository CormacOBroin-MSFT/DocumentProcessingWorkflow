"""
Azure AI Content Understanding Service
Analyzes customs declaration documents using Content Understanding.

Supports two modes:
  1. prebuilt-invoice (default) — works immediately, maps invoice fields to customs fields
  2. customsDeclaration — custom analyzer with our exact schema (requires setup)

Set AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID in .env to choose.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from azure.identity import DefaultAzureCredential
from app.config import config
from app.services.content_understanding_client import ContentUnderstandingClient

logger = logging.getLogger("autonomousflow.content_understanding")

# Which analyzer to use — prebuilt-invoice works out of the box
ANALYZER_ID = os.getenv("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", "prebuilt-invoice")

# Our target customs fields
CUSTOMS_FIELDS = ["shipper", "receiver", "goodsDescription", "value", "countryOfOrigin", "hsCode", "weight"]

# ISO-3166 alpha-3 → country name mapping for CountryRegion field
COUNTRY_CODES = {
    "DEU": "Germany", "USA": "United States", "GBR": "United Kingdom",
    "CHN": "China", "JPN": "Japan", "FRA": "France", "IND": "India",
    "KOR": "South Korea", "ITA": "Italy", "CAN": "Canada", "AUS": "Australia",
    "BRA": "Brazil", "MEX": "Mexico", "NLD": "Netherlands", "ESP": "Spain",
    "TWN": "Taiwan", "SGP": "Singapore", "MYS": "Malaysia", "THA": "Thailand",
    "VNM": "Vietnam", "IDN": "Indonesia", "TUR": "Turkey", "CHE": "Switzerland",
    "SWE": "Sweden", "POL": "Poland", "BEL": "Belgium", "AUT": "Austria",
}


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
        self._is_prebuilt_invoice = ANALYZER_ID == "prebuilt-invoice"

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

        if self._is_prebuilt_invoice:
            return self._map_invoice_fields(fields, content)
        else:
            return self._map_custom_fields(fields, content)

    # ── Prebuilt-invoice field mapping ────────────────────────────

    def _map_invoice_fields(self, fields: Dict[str, Any], content: Dict) -> Dict[str, Any]:
        """Map prebuilt-invoice fields to our customs schema."""
        # Shipper = Vendor name + address
        vendor_name = self._read_string(fields.get("VendorName"))
        vendor_addr = self._read_string(fields.get("VendorAddress"))
        shipper = f"{vendor_name}, {vendor_addr}".strip(", ") if vendor_name else vendor_addr

        # Receiver = Customer name + address
        cust_name = self._read_string(fields.get("CustomerName"))
        cust_addr = self._read_string(fields.get("CustomerAddress"))
        receiver = f"{cust_name}, {cust_addr}".strip(", ") if cust_name else cust_addr

        # Goods description from line items
        goods = self._extract_line_items_description(fields.get("LineItems"))

        # Value from TotalAmount (object type with amount + currency)
        value = self._read_amount(fields.get("TotalAmount"))
        if not value:
            value = self._read_amount(fields.get("SubtotalAmount"))

        # Country of origin from CountryRegion
        country_raw = self._read_string(fields.get("CountryRegion"))
        country = COUNTRY_CODES.get(country_raw, country_raw) if country_raw else ""
        # If no CountryRegion, try to derive from vendor address
        if not country and vendor_addr:
            country = self._extract_country_from_address(vendor_addr)

        # HS codes and weight — not available in prebuilt-invoice,
        # will be filled by the LLM transform step
        hs_code = ""
        weight = ""

        # Build structured_data in our standard format
        field_map = {
            "shipper": (shipper, self._confidence(fields.get("VendorName"))),
            "receiver": (receiver, self._confidence(fields.get("CustomerName"))),
            "goodsDescription": (goods, 0.75 if goods else 0.0),
            "value": (value, self._confidence(fields.get("TotalAmount"))),
            "countryOfOrigin": (country, self._confidence(fields.get("CountryRegion")) if country_raw else 0.5),
            "hsCode": (hs_code, 0.0),
            "weight": (weight, 0.0),
        }

        return self._build_result(field_map, content)

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
    def _read_string(field: Optional[Dict]) -> str:
        if not field:
            return ""
        return field.get("valueString", "") or ""

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
    def _read_amount(field: Optional[Dict]) -> str:
        """Read an amount object field (e.g. TotalAmount with amount + currencyCode)."""
        if not field:
            return ""
        obj = field.get("valueObject", {})
        if obj:
            amt = obj.get("amount", {}).get("valueNumber")
            cur = obj.get("currencyCode", {}).get("valueString", "")
            if amt is not None:
                return f"{cur} {amt:,.2f}".strip() if cur else f"{amt:,.2f}"
        # Fallback for string-typed amount
        return field.get("valueString", "")

    @staticmethod
    def _confidence(field: Optional[Dict]) -> float:
        if not field:
            return 0.0
        return field.get("confidence", 0.0)

    def _extract_line_items_description(self, line_items_field: Optional[Dict]) -> str:
        """Extract goods descriptions from LineItems array."""
        if not line_items_field:
            return ""
        items = line_items_field.get("valueArray", [])
        descriptions: List[str] = []
        for item in items:
            obj = item.get("valueObject", {})
            desc = obj.get("Description", {}).get("valueString", "")
            if desc:
                descriptions.append(desc.strip())
        return "; ".join(descriptions) if descriptions else ""

    @staticmethod
    def _extract_country_from_address(address: str) -> str:
        """Try to extract a country name from the end of an address string."""
        if not address:
            return ""
        # Common pattern: "City, Country" at the end
        known = {
            "germany": "Germany", "united states": "United States", "usa": "United States",
            "united kingdom": "United Kingdom", "uk": "United Kingdom",
            "china": "China", "japan": "Japan", "france": "France", "india": "India",
            "canada": "Canada", "australia": "Australia", "brazil": "Brazil",
            "mexico": "Mexico", "netherlands": "Netherlands", "spain": "Spain",
            "italy": "Italy", "south korea": "South Korea", "singapore": "Singapore",
            "switzerland": "Switzerland", "sweden": "Sweden", "taiwan": "Taiwan",
        }
        # Check the last word/segment of the address
        parts = [p.strip() for p in address.replace("\n", ",").split(",") if p.strip()]
        if parts:
            last = parts[-1].lower()
            if last in known:
                return known[last]
        return ""


def get_content_understanding_service() -> Optional[AzureContentUnderstandingService]:
    """Factory function to get Content Understanding service instance."""
    try:
        return AzureContentUnderstandingService()
    except Exception as e:
        logger.error(f"Could not initialize Content Understanding service: {e}")
        return None