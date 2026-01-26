"""
Azure Cosmos DB Service
Handles storing and retrieving customs declaration records
"""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential
from app.config import config

logger = logging.getLogger('autonomousflow.cosmos')


class AzureCosmosService:
    """Service for storing customs declarations in Azure Cosmos DB"""
    
    def __init__(self):
        if not config.AZURE_COSMOS_ENDPOINT:
            raise ValueError("Azure Cosmos DB endpoint not configured")
        
        self.endpoint = config.AZURE_COSMOS_ENDPOINT
        self.database_name = config.AZURE_COSMOS_DATABASE
        self.container_name = config.AZURE_COSMOS_CONTAINER
        
        # Use DefaultAzureCredential for identity-based authentication
        credential = DefaultAzureCredential()
        self.client = CosmosClient(self.endpoint, credential=credential)
        
        # Get database and container references
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)
        
        logger.info(f"Connected to Cosmos DB: {self.database_name}/{self.container_name}")
    
    def store_declaration(self, declaration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store a processed customs declaration in Cosmos DB
        
        Args:
            declaration_data: The customs declaration data to store
            
        Returns:
            Dict with the stored document including id and metadata
        """
        try:
            # Generate unique document ID if not provided
            document_id = declaration_data.get('documentId') or str(uuid.uuid4())
            
            # Build the document to store
            document = {
                'id': document_id,
                'documentId': document_id,  # Partition key
                'type': 'customs_declaration',
                'status': declaration_data.get('status', 'processed'),
                'createdAt': datetime.utcnow().isoformat() + 'Z',
                'updatedAt': datetime.utcnow().isoformat() + 'Z',
                
                # Document metadata
                'fileName': declaration_data.get('fileName'),
                'blobUrl': declaration_data.get('blobUrl'),
                
                # Extracted customs fields
                'structuredData': declaration_data.get('structuredData', {}),
                
                # Confidence scores
                'confidenceScores': declaration_data.get('confidenceScores', {}),
                
                # Compliance results
                'complianceChecks': declaration_data.get('complianceChecks', []),
                'complianceDescriptions': declaration_data.get('complianceDescriptions', []),
                
                # Approval info
                'approvalStatus': declaration_data.get('approvalStatus', 'pending'),
                'reviewerNotes': declaration_data.get('reviewerNotes', ''),
                'approvedAt': declaration_data.get('approvedAt'),
                'approvedBy': declaration_data.get('approvedBy'),
                
                # Submission info
                'submissionId': declaration_data.get('submissionId'),
                'submittedAt': declaration_data.get('submittedAt'),
            }
            
            # Store in Cosmos DB
            result = self.container.create_item(body=document)
            
            logger.info(f"✅ Stored declaration {document_id} in Cosmos DB")
            
            return {
                'id': result['id'],
                'documentId': result['documentId'],
                'status': 'stored',
                'createdAt': result['createdAt'],
            }
            
        except exceptions.CosmosResourceExistsError:
            # Document already exists, update it instead
            logger.info(f"Document {document_id} exists, updating...")
            document['updatedAt'] = datetime.utcnow().isoformat() + 'Z'
            result = self.container.upsert_item(body=document)
            
            return {
                'id': result['id'],
                'documentId': result['documentId'],
                'status': 'updated',
                'updatedAt': result['updatedAt'],
            }
            
        except Exception as e:
            logger.error(f"Failed to store declaration: {e}")
            raise
    
    def get_declaration(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a customs declaration from Cosmos DB
        
        Args:
            document_id: The document ID to retrieve
            
        Returns:
            The declaration document or None if not found
        """
        try:
            result = self.container.read_item(
                item=document_id,
                partition_key=document_id
            )
            return result
            
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Declaration {document_id} not found")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get declaration: {e}")
            raise
    
    def list_declarations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List recent customs declarations
        
        Args:
            limit: Maximum number of declarations to return
            
        Returns:
            List of declaration documents
        """
        try:
            query = """
                SELECT * FROM c 
                WHERE c.type = 'customs_declaration' 
                ORDER BY c.createdAt DESC 
                OFFSET 0 LIMIT @limit
            """
            
            items = list(self.container.query_items(
                query=query,
                parameters=[{'name': '@limit', 'value': limit}],
                enable_cross_partition_query=True
            ))
            
            return items
            
        except Exception as e:
            logger.error(f"Failed to list declarations: {e}")
            raise
    
    def update_declaration(self, document_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing customs declaration
        
        Args:
            document_id: The document ID to update
            updates: Dictionary of fields to update
            
        Returns:
            The updated document
        """
        try:
            # Get existing document
            existing = self.get_declaration(document_id)
            if not existing:
                raise ValueError(f"Declaration {document_id} not found")
            
            # Merge updates
            existing.update(updates)
            existing['updatedAt'] = datetime.utcnow().isoformat() + 'Z'
            
            # Save back to Cosmos DB
            result = self.container.upsert_item(body=existing)
            
            logger.info(f"✅ Updated declaration {document_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to update declaration: {e}")
            raise


def get_cosmos_service() -> Optional[AzureCosmosService]:
    """Factory function to get Cosmos DB service instance"""
    try:
        if not config.is_cosmos_configured():
            logger.warning("Cosmos DB not configured")
            return None
        return AzureCosmosService()
    except Exception as e:
        logger.error(f"Could not initialize Azure Cosmos DB Service: {e}")
        return None
