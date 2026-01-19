"""
Azure Blob Storage Service
Handles document upload and retrieval from Azure Blob Storage
"""
import os
import re
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, BinaryIO
from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions
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
    
    def _get_user_delegation_sas(self, blob_name: str, expiry_hours: int = 1) -> str:
        """
        Generate a User Delegation SAS token using identity-based auth.
        This doesn't require storage account keys.
        """
        # Get user delegation key (valid for up to 7 days)
        delegation_key_start = datetime.utcnow()
        delegation_key_expiry = delegation_key_start + timedelta(hours=expiry_hours)
        
        user_delegation_key = self.blob_service_client.get_user_delegation_key(
            key_start_time=delegation_key_start,
            key_expiry_time=delegation_key_expiry
        )
        
        # Generate SAS token using the delegation key
        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=delegation_key_expiry
        )
        
        return sas_token
    
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
            str: URL of the uploaded blob with SAS token for external access
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
        
        # Generate SAS URL for external services (like Document Intelligence) to access
        logger.info(f"   Generating User Delegation SAS token...")
        sas_token = self._get_user_delegation_sas(blob_name)
        sas_url = f"{blob_client.url}?{sas_token}"
        
        logger.info(f"   Upload successful!")
        return sas_url
    
    def get_blob_url(self, blob_name: str, with_sas: bool = True) -> str:
        """Get the URL for a specific blob, optionally with SAS token"""
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        if with_sas:
            sas_token = self._get_user_delegation_sas(blob_name)
            return f"{blob_client.url}?{sas_token}"
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
