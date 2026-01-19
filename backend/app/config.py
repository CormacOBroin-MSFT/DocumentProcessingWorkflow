"""
Configuration Management
Loads and validates environment variables
"""
import os
from typing import Optional

class Config:
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    AZURE_STORAGE_CONTAINER: str = os.getenv('AZURE_STORAGE_CONTAINER', 'customs-documents')
    
    # Azure Content Understanding Service
    AZURE_CONTENT_UNDERSTANDING_ENDPOINT: Optional[str] = os.getenv('AZURE_CONTENT_UNDERSTANDING_ENDPOINT')
    AZURE_CONTENT_UNDERSTANDING_KEY: Optional[str] = os.getenv('AZURE_CONTENT_UNDERSTANDING_KEY')
    
    # Legacy Document Intelligence (kept for fallback)
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: Optional[str] = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT')
    AZURE_DOCUMENT_INTELLIGENCE_KEY: Optional[str] = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_KEY')
    
    # Azure OpenAI (AI Foundry)
    AZURE_OPENAI_ENDPOINT: Optional[str] = os.getenv('AZURE_OPENAI_ENDPOINT')
    AZURE_OPENAI_KEY: Optional[str] = os.getenv('AZURE_OPENAI_KEY')
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
    
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG: bool = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    @classmethod
    def is_azure_configured(cls) -> bool:
        """Check if Azure services are properly configured"""
        return bool(
            cls.AZURE_STORAGE_CONNECTION_STRING and
            (cls.AZURE_CONTENT_UNDERSTANDING_ENDPOINT or cls.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT)
        )
    
    @classmethod
    def is_openai_configured(cls) -> bool:
        """Check if Azure OpenAI is properly configured"""
        return bool(
            cls.AZURE_OPENAI_ENDPOINT and
            cls.AZURE_OPENAI_DEPLOYMENT
        )
    
    @classmethod
    def get_ocr_service_type(cls) -> str:
        """Determine which OCR service to use - Content Understanding preferred"""
        if cls.AZURE_CONTENT_UNDERSTANDING_ENDPOINT:
            return "content_understanding"
        elif cls.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT:
            return "document_intelligence"
        else:
            return "none"

config = Config()
