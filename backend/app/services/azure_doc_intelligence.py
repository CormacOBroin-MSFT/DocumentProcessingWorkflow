"""
Azure Document Intelligence Service
Handles OCR and document analysis using Azure AI Document Intelligence
"""
from typing import Dict, Optional
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from app.config import config

class AzureDocumentIntelligenceService:
    """Service for OCR and document analysis"""
    
    def __init__(self):
        if not config.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT:
            raise ValueError("Azure Document Intelligence endpoint not configured")
        
        # Use DefaultAzureCredential for local dev (uses Azure CLI login)
        # Falls back to key-based auth if key is provided and credential fails
        if config.AZURE_DOCUMENT_INTELLIGENCE_KEY:
            credential = AzureKeyCredential(config.AZURE_DOCUMENT_INTELLIGENCE_KEY)
        else:
            credential = DefaultAzureCredential()
        
        self.client = DocumentAnalysisClient(
            endpoint=config.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
            credential=credential
        )
    
    def analyze_document(self, blob_url: str) -> Dict:
        """
        Analyze a document from a URL using Azure AI Document Intelligence
        
        Args:
            blob_url: URL of the document to analyze
            
        Returns:
            Dict with raw_data and confidence score
        """
        poller = self.client.begin_analyze_document_from_url(
            model_id="prebuilt-document",
            document_url=blob_url
        )
        
        result = poller.result()
        
        raw_data = {}
        total_confidence = 0
        field_count = 0
        
        if result.key_value_pairs:
            for kv_pair in result.key_value_pairs:
                if kv_pair.key and kv_pair.value:
                    key_text = kv_pair.key.content.upper() if kv_pair.key.content else "UNKNOWN"
                    value_text = kv_pair.value.content if kv_pair.value.content else ""
                    confidence = kv_pair.confidence if kv_pair.confidence else 0.0
                    
                    raw_data[key_text] = {
                        'value': value_text,
                        'confidence': confidence
                    }
                    
                    total_confidence += confidence
                    field_count += 1
        
        if not raw_data and result.content:
            raw_data['DOCUMENT_TEXT'] = {
                'value': result.content[:500],
                'confidence': 0.85
            }
            total_confidence = 0.85
            field_count = 1
        
        ocr_confidence = total_confidence / field_count if field_count > 0 else 0.0
        
        return {
            'raw_data': raw_data,
            'ocr_confidence': ocr_confidence
        }

def get_document_intelligence_service() -> Optional[AzureDocumentIntelligenceService]:
    """Factory function to get document intelligence service instance"""
    try:
        return AzureDocumentIntelligenceService()
    except Exception as e:
        print(f"Could not initialize Azure Document Intelligence Service: {e}")
        return None
