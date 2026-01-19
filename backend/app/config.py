"""
Configuration Management
Loads and validates environment variables
"""
import os
from typing import Optional

class Config:
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    AZURE_STORAGE_CONTAINER: str = os.getenv('AZURE_STORAGE_CONTAINER', 'customs-documents')
    
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: Optional[str] = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT')
    AZURE_DOCUMENT_INTELLIGENCE_KEY: Optional[str] = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_KEY')
    
    OPENAI_API_KEY: Optional[str] = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL: str = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG: bool = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    @classmethod
    def is_azure_configured(cls) -> bool:
        """Check if Azure services are properly configured"""
        return bool(
            cls.AZURE_STORAGE_CONNECTION_STRING and
            cls.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and
            cls.AZURE_DOCUMENT_INTELLIGENCE_KEY
        )
    
    @classmethod
    def is_openai_configured(cls) -> bool:
        """Check if OpenAI is properly configured"""
        return bool(cls.OPENAI_API_KEY)

config = Config()
