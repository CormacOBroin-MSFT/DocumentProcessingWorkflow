"""
Azure Blob Storage Service
Handles document upload and retrieval from Azure Blob Storage
"""
import os
import uuid
from typing import Optional, BinaryIO
from azure.storage.blob import BlobServiceClient, ContentSettings
from app.config import config

class AzureBlobService:
    """Service for interacting with Azure Blob Storage"""
    
    def __init__(self):
        if not config.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError("Azure Storage connection string not configured")
        
        self.blob_service_client = BlobServiceClient.from_connection_string(
            config.AZURE_STORAGE_CONNECTION_STRING
        )
        self.container_name = config.AZURE_STORAGE_CONTAINER
        self._ensure_container_exists()
    
    def _ensure_container_exists(self):
        """Create container if it doesn't exist"""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            if not container_client.exists():
                container_client.create_container()
        except Exception as e:
            print(f"Warning: Could not verify/create container: {e}")
    
    def upload_file(
        self, 
        file_stream: BinaryIO, 
        filename: str,
        content_type: str = 'application/octet-stream'
    ) -> str:
        """
        Upload a file to Azure Blob Storage
        
        Args:
            file_stream: File-like object to upload
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            str: URL of the uploaded blob
        """
        blob_name = f"{uuid.uuid4()}-{filename}"
        
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        
        content_settings = ContentSettings(content_type=content_type)
        
        blob_client.upload_blob(
            file_stream,
            content_settings=content_settings,
            overwrite=True
        )
        
        return blob_client.url
    
    def get_blob_url(self, blob_name: str) -> str:
        """Get the URL for a specific blob"""
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        return blob_client.url
    
    def delete_blob(self, blob_name: str) -> bool:
        """Delete a blob from storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            blob_client.delete_blob()
            return True
        except Exception as e:
            print(f"Error deleting blob: {e}")
            return False

def get_blob_service() -> Optional[AzureBlobService]:
    """Factory function to get blob service instance"""
    try:
        return AzureBlobService()
    except Exception as e:
        print(f"Could not initialize Azure Blob Service: {e}")
        return None
