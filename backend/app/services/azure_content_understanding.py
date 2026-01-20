"""
Azure AI Content Understanding Service
Handles document analysis using Azure AI Content Understanding with custom analyzer
Extracts structured customs declaration fields using a defined schema
"""
import logging
import requests
import time
from typing import Dict, Optional, Any
from azure.identity import DefaultAzureCredential
from app.config import config

logger = logging.getLogger('autonomousflow.content_understanding')

# Analyzer ID for customs declarations (created via setup-analyzer.sh)
CUSTOMS_ANALYZER_ID = "customsDeclaration"

# Expected fields from our customs analyzer schema
CUSTOMS_FIELDS = ['shipper', 'receiver', 'goodsDescription', 'value', 'countryOfOrigin', 'hsCode', 'weight']


class AzureContentUnderstandingService:
    """Service for document analysis using Azure AI Content Understanding"""
    
    def __init__(self):
        if not config.AZURE_CONTENT_UNDERSTANDING_ENDPOINT:
            raise ValueError("Azure Content Understanding endpoint not configured")
        
        self.endpoint = config.AZURE_CONTENT_UNDERSTANDING_ENDPOINT.rstrip('/')
        self.api_version = "2025-11-01"
        
        # Use DefaultAzureCredential for local dev (uses Azure CLI login)
        # Falls back to key-based auth if key is provided
        if config.AZURE_CONTENT_UNDERSTANDING_KEY:
            self.api_key = config.AZURE_CONTENT_UNDERSTANDING_KEY
            self.use_api_key = True
        else:
            self.credential = DefaultAzureCredential()
            self.use_api_key = False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.use_api_key:
            headers['Ocp-Apim-Subscription-Key'] = self.api_key
        else:
            token = self.credential.get_token("https://cognitiveservices.azure.com/.default")
            headers['Authorization'] = f'Bearer {token.token}'
            
        return headers
    
    def analyze_document(self, blob_url: str) -> Dict[str, Any]:
        """
        Analyze a document using the customs declaration analyzer
        
        Args:
            blob_url: URL of the document to analyze (must be accessible)
            
        Returns:
            Dict with structured_data (customs fields with confidence) and overall confidence
        """
        try:
            # Submit document for analysis using our custom analyzer
            analyze_url = f"{self.endpoint}/contentunderstanding/analyzers/{CUSTOMS_ANALYZER_ID}:analyze"
            
            payload = {
                "inputs": [
                    {"url": blob_url}
                ]
            }
            
            headers = self._get_headers()
            
            # Start analysis
            response = requests.post(
                analyze_url,
                json=payload,
                headers=headers,
                params={'api-version': self.api_version}
            )
            
            if response.status_code == 202:
                # Get result ID from response body
                result = response.json()
                result_id = result.get('id')
                
                if not result_id:
                    raise ValueError("No result ID returned from Content Understanding")
                
                return self._poll_for_results(result_id)
            else:
                error_detail = response.text
                logger.error(f"Content Understanding API error: {response.status_code} - {error_detail}")
                raise ValueError(f"Content Understanding API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Content Understanding analysis failed: {e}")
            raise ValueError(f"Content Understanding API error: {e}")
    
    def _poll_for_results(self, result_id: str, max_attempts: int = 60) -> Dict[str, Any]:
        """Poll for analysis results"""
        headers = self._get_headers()
        result_url = f"{self.endpoint}/contentunderstanding/analyzerResults/{result_id}"
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(
                    result_url,
                    headers=headers,
                    params={'api-version': self.api_version}
                )
                response.raise_for_status()
                result = response.json()
                
                status = result.get('status', '').lower()
                
                if status == 'succeeded':
                    return self._extract_customs_fields(result)
                elif status == 'failed':
                    error_msg = result.get('error', {}).get('message', 'Unknown error')
                    raise Exception(f"Content Understanding analysis failed: {error_msg}")
                
                # Still running, wait and retry
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error polling results (attempt {attempt + 1}): {e}")
                if attempt == max_attempts - 1:
                    raise
        
        raise Exception("Content Understanding analysis timed out")
    
    def _extract_customs_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract customs fields from Content Understanding results
        
        The analyzer returns fields directly based on our schema definition
        """
        try:
            # Get the first content result
            contents = result.get('result', {}).get('contents', [])
            
            if not contents:
                raise ValueError("No content returned from analysis")
            
            content = contents[0]
            fields = content.get('fields', {})
            
            # Log the raw fields for debugging
            logger.info("=== Content Understanding Raw Response ===")
            logger.info(f"Fields received: {list(fields.keys())}")
            for field_name, field_data in fields.items():
                logger.info(f"  {field_name}: {field_data}")
            
            # Also log the markdown content to see what was extracted
            markdown = content.get('markdown', '')
            if markdown:
                logger.info(f"Markdown content (first 1000 chars):\n{markdown[:1000]}")
            
            # Log tables if present
            tables = content.get('tables', [])
            if tables:
                logger.info(f"Tables found: {len(tables)}")
                for i, table in enumerate(tables[:2]):  # Log first 2 tables
                    logger.info(f"  Table {i}: {table}")
            
            # Build structured data from extracted fields
            structured_data: Dict[str, Dict[str, Any]] = {}
            confidences = []
            
            for field_name in CUSTOMS_FIELDS:
                field_data = fields.get(field_name, {})
                
                # Extract value based on field type
                value = ''
                if field_data.get('type') == 'string':
                    value = field_data.get('valueString', '')
                elif field_data.get('type') == 'number':
                    value = str(field_data.get('valueNumber', ''))
                elif 'value' in field_data:
                    value = str(field_data.get('value', ''))
                
                confidence = field_data.get('confidence', 0.0)
                
                structured_data[field_name] = {
                    'value': value,
                    'confidence': confidence
                }
                
                if value and confidence > 0:
                    confidences.append(confidence)
            
            # Calculate overall confidence
            overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            # Also collect raw key-value pairs for debugging/display
            raw_data = {}
            key_value_pairs = content.get('keyValuePairs', [])
            for kv in key_value_pairs:
                key = kv.get('key', {}).get('content', '')
                value = kv.get('value', {}).get('content', '')
                conf = kv.get('confidence', 0.8)
                if key and value:
                    raw_data[key] = {'value': value, 'confidence': conf}
            
            return {
                'structured_data': structured_data,
                'raw_data': raw_data,
                'ocr_confidence': overall_confidence
            }
            
        except Exception as e:
            logger.error(f"Error extracting customs fields: {e}")
            raise


def get_content_understanding_service() -> Optional[AzureContentUnderstandingService]:
    """Factory function to get Content Understanding service instance"""
    try:
        return AzureContentUnderstandingService()
    except Exception as e:
        logger.error(f"Could not initialize Azure Content Understanding Service: {e}")
        return None