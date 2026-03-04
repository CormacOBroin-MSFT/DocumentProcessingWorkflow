"""
Azure Blob Storage Service
Handles document upload and retrieval from Azure Blob Storage
"""
import os
import re
import uuid
import logging
from typing import Optional, BinaryIO
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential
from app.config import config

logger = logging.getLogger('autonomousflow.blob')

class AzureBlobService:
    """Service for interacting with Azure Blob Storage"""
    
    def __init__(self):
        # Extract account name from connection string or use directly
        self.account_name = self._get_account_name()
        if not self.account_name:
            raise ValueError("Azure Storage account not configured")
        
        # Use DefaultAzureCredential (Azure CLI login) instead of connection string keys
        logger.info(f"Initializing Blob Storage with DefaultAzureCredential for account: {self.account_name}")
        account_url = f"https://{self.account_name}.blob.core.windows.net"
        
        self.credential = DefaultAzureCredential()
        self.blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=self.credential
        )
        self.container_name = config.AZURE_STORAGE_CONTAINER
        self._ensure_container_exists()
    
    def _get_account_name(self) -> Optional[str]:
        """Extract storage account name from connection string"""
        conn_str = config.AZURE_STORAGE_CONNECTION_STRING
        if not conn_str:
            return None
        
        # Parse AccountName from connection string
        match = re.search(r'AccountName=([^;]+)', conn_str)
        if match:
            return match.group(1)
        return None
    
    def _ensure_container_exists(self):
        """Create container if it doesn't exist"""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            if not container_client.exists():
                logger.info(f"Creating container: {self.container_name}")
                container_client.create_container()
        except Exception as e:
            logger.warning(f"Could not verify/create container: {e}")
    
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
            str: Plain blob URL (Content Understanding accesses via its managed identity)
        """
        blob_name = f"{uuid.uuid4()}-{filename}"
        logger.info(f"   Creating blob: {blob_name}")
        
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        
        content_settings = ContentSettings(content_type=content_type)
        
        logger.info(f"   Uploading to container: {self.container_name}")
        blob_client.upload_blob(
            file_stream,
            content_settings=content_settings,
            overwrite=True
        )
        
        logger.info(f"   Upload successful!")
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
