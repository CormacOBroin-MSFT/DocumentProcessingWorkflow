"""
HS Code Reference Service

Provides access to HS code reference data stored in CosmosDB.
Used by the HS Code Validation Agent for code lookup and validation.
"""

import logging
from typing import Dict, Any, List, Optional
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from app.config import config

logger = logging.getLogger('autonomousflow.services.hs_codes')


class HSCodeReferenceService:
    """
    Service for querying HS code reference data from CosmosDB.
    
    Provides methods for:
    - Looking up codes by exact match
    - Searching descriptions by keywords
    - Finding codes by chapter/heading
    - Validating code format
    """
    
    DATABASE_NAME = 'customs-workflow'
    CONTAINER_NAME = 'hs-codes'
    
    def __init__(self):
        """Initialize the service with CosmosDB connection"""
        self._client: Optional[CosmosClient] = None
        self._container = None
    
    @property
    def container(self):
        """Lazy-load the container client"""
        if self._container is None:
            if not config.AZURE_COSMOS_ENDPOINT:
                raise ValueError("Azure Cosmos DB endpoint not configured")
            
            credential = DefaultAzureCredential()
            self._client = CosmosClient(config.AZURE_COSMOS_ENDPOINT, credential=credential)
            database = self._client.get_database_client(self.DATABASE_NAME)
            self._container = database.get_container_client(self.CONTAINER_NAME)
            logger.info(f"Connected to HS codes container: {self.DATABASE_NAME}/{self.CONTAINER_NAME}")
        
        return self._container
    
    def lookup_code(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Look up an HS code by exact match.
        
        Args:
            hs_code: The HS code to look up (4-10 digits)
            
        Returns:
            Dict with code details if found, None otherwise
        """
        # Normalize code (remove spaces/dashes, pad to 10 digits)
        clean_code = ''.join(filter(str.isdigit, hs_code))
        clean_code = clean_code.ljust(10, '0')
        
        # Get chapter for partition key
        chapter = clean_code[:2]
        
        query = """
        SELECT * FROM c 
        WHERE c.chapterCode = @chapter 
        AND c.code = @code
        """
        
        try:
            results = list(self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@chapter", "value": chapter},
                    {"name": "@code", "value": clean_code}
                ],
                enable_cross_partition_query=False
            ))
            
            if results:
                return self._format_result(results[0])
            return None
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error looking up HS code {hs_code}: {e.message}")
            return None
    
    def search_by_description(
        self, 
        keywords: List[str], 
        chapter: Optional[str] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for HS codes by description keywords.
        
        Args:
            keywords: List of keywords to search for
            chapter: Optional chapter code to limit search
            max_results: Maximum number of results to return
            
        Returns:
            List of matching HS codes with descriptions
        """
        # Build CONTAINS clauses for each keyword
        keyword_clauses = []
        parameters = []
        
        for i, keyword in enumerate(keywords[:5]):  # Limit to 5 keywords
            param_name = f"@kw{i}"
            keyword_clauses.append(f"CONTAINS(c.descriptionLower, {param_name})")
            parameters.append({"name": param_name, "value": keyword.lower()})
        
        where_clause = " OR ".join(keyword_clauses)
        
        if chapter:
            where_clause = f"c.chapterCode = @chapter AND ({where_clause})"
            parameters.append({"name": "@chapter", "value": chapter})
        
        query = f"""
        SELECT TOP {max_results} c.code, c.description, c.chapterCode, c.headingCode, c.subheadingCode
        FROM c 
        WHERE {where_clause}
        ORDER BY c.code
        """
        
        try:
            results = list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=(chapter is None)
            ))
            
            return [self._format_result(r) for r in results]
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error searching HS codes: {e.message}")
            return []
    
    def get_codes_by_chapter(self, chapter: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get all HS codes in a chapter.
        
        Args:
            chapter: 2-digit chapter code
            max_results: Maximum results to return
            
        Returns:
            List of HS codes in the chapter
        """
        query = f"""
        SELECT TOP {max_results} c.code, c.description, c.headingCode, c.subheadingCode
        FROM c 
        WHERE c.chapterCode = @chapter
        ORDER BY c.code
        """
        
        try:
            results = list(self.container.query_items(
                query=query,
                parameters=[{"name": "@chapter", "value": chapter}],
                enable_cross_partition_query=False
            ))
            
            return [self._format_result(r) for r in results]
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error getting chapter {chapter}: {e.message}")
            return []
    
    def get_codes_by_heading(self, heading: str) -> List[Dict[str, Any]]:
        """
        Get all HS codes under a heading (first 4 digits).
        
        Args:
            heading: 4-digit heading code
            
        Returns:
            List of HS codes under the heading
        """
        chapter = heading[:2]
        
        query = """
        SELECT c.code, c.description, c.headingCode, c.subheadingCode, c.suffix
        FROM c 
        WHERE c.chapterCode = @chapter 
        AND c.headingCode = @heading
        ORDER BY c.code
        """
        
        try:
            results = list(self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@chapter", "value": chapter},
                    {"name": "@heading", "value": heading}
                ],
                enable_cross_partition_query=False
            ))
            
            return [self._format_result(r) for r in results]
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error getting heading {heading}: {e.message}")
            return []
    
    def validate_code_format(self, hs_code: str) -> Dict[str, Any]:
        """
        Validate the format of an HS code.
        
        Args:
            hs_code: The HS code to validate
            
        Returns:
            Dict with validation results
        """
        clean_code = ''.join(filter(str.isdigit, hs_code))
        
        result = {
            'original': hs_code,
            'normalized': clean_code,
            'is_valid_format': False,
            'issues': [],
            'components': {}
        }
        
        # Check length
        if len(clean_code) < 4:
            result['issues'].append(f"Code too short ({len(clean_code)} digits, minimum 4)")
        elif len(clean_code) > 10:
            result['issues'].append(f"Code too long ({len(clean_code)} digits, maximum 10)")
        else:
            result['is_valid_format'] = True
            
            # Parse components
            padded = clean_code.ljust(10, '0')
            result['components'] = {
                'chapter': padded[:2],
                'heading': padded[:4],
                'subheading': padded[:6],
                'full': padded
            }
        
        # Check for valid chapter (01-99)
        if result['is_valid_format']:
            chapter = int(result['components']['chapter'])
            if chapter < 1 or chapter > 99:
                result['is_valid_format'] = False
                result['issues'].append(f"Invalid chapter code: {chapter}")
        
        return result
    
    def find_similar_codes(self, hs_code: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Find HS codes similar to the given code (same heading or subheading).
        
        Args:
            hs_code: The HS code to find similar codes for
            max_results: Maximum results to return
            
        Returns:
            List of similar HS codes
        """
        validation = self.validate_code_format(hs_code)
        if not validation['is_valid_format']:
            return []
        
        heading = validation['components']['heading']
        return self.get_codes_by_heading(heading)[:max_results]
    
    def _format_result(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format a CosmosDB document for return"""
        return {
            'code': doc.get('code', ''),
            'description': doc.get('description', ''),
            'chapter': doc.get('chapterCode', ''),
            'heading': doc.get('headingCode', ''),
            'subheading': doc.get('subheadingCode', ''),
            'suffix': doc.get('suffix', ''),
            'valid_from': doc.get('validFrom', ''),
            'valid_to': doc.get('validTo', ''),
        }


# Singleton instance
_service_instance: Optional[HSCodeReferenceService] = None


def get_hs_code_service() -> HSCodeReferenceService:
    """
    Get or create the HS code reference service instance.
    
    Raises:
        RuntimeError: If the service cannot be initialized (CosmosDB unavailable)
    """
    global _service_instance
    
    if _service_instance is None:
        try:
            _service_instance = HSCodeReferenceService()
        except Exception as e:
            logger.error(f"Failed to initialize HS code service: {e}")
            raise RuntimeError(
                f"HS Code reference service unavailable. "
                f"Ensure CosmosDB is configured and HS codes have been indexed. "
                f"Run: python scripts/index_hs_codes.py\n"
                f"Original error: {e}"
            ) from e
    
    return _service_instance
