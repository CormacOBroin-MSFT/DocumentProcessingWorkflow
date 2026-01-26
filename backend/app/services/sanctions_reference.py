"""
Sanctions Reference Service

Provides queries against the UK Sanctions list stored in CosmosDB.
Used by the Country Restrictions Agent for sanctions screening.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

DATABASE_NAME = 'customs-workflow'
CONTAINER_NAME = 'sanctions'


@dataclass
class SanctionedEntity:
    """Represents a sanctioned entity from the UK sanctions list"""
    unique_id: str
    name: str
    entity_type: str  # Individual, Entity, Ship
    regime_code: str
    regime_name: str
    sanctions_imposed: str
    nationality: str
    address_country: str
    designation_type: str
    ofsi_group_id: str
    date_designated: str
    other_information: str


class SanctionsReferenceService:
    """
    Service for querying the UK Sanctions List in CosmosDB.
    
    This service enables:
    - Name-based entity searches (fuzzy matching)
    - Country-based sanctions queries
    - Regime-based lookups
    - Entity screening for compliance checks
    """
    
    def __init__(self, cosmos_client: Optional[CosmosClient] = None):
        """
        Initialize the sanctions reference service.
        
        Args:
            cosmos_client: Optional pre-configured CosmosDB client.
                          If not provided, creates one using DefaultAzureCredential.
        """
        if cosmos_client:
            self._client = cosmos_client
        else:
            endpoint = os.getenv('AZURE_COSMOS_ENDPOINT')
            if not endpoint:
                raise ValueError("AZURE_COSMOS_ENDPOINT environment variable not set")
            credential = DefaultAzureCredential()
            self._client = CosmosClient(endpoint, credential=credential)
        
        self._database = self._client.get_database_client(DATABASE_NAME)
        self._container = self._database.get_container_client(CONTAINER_NAME)
    
    def search_by_name(
        self, 
        name: str, 
        max_results: int = 20,
        entity_type: Optional[str] = None
    ) -> List[SanctionedEntity]:
        """
        Search for sanctioned entities by name (case-insensitive).
        
        Uses CONTAINS for partial matching.
        
        Args:
            name: Name to search for (partial match supported)
            max_results: Maximum number of results to return
            entity_type: Optional filter for entity type (Individual, Entity, Ship)
            
        Returns:
            List of matching sanctioned entities
        """
        name_lower = name.lower().strip()
        
        # Build query
        if entity_type:
            query = """
                SELECT TOP @maxResults * FROM c 
                WHERE CONTAINS(c.nameLower, @nameLower)
                AND c.entityType = @entityType
            """
            params = [
                {"name": "@nameLower", "value": name_lower},
                {"name": "@maxResults", "value": max_results},
                {"name": "@entityType", "value": entity_type}
            ]
        else:
            query = """
                SELECT TOP @maxResults * FROM c 
                WHERE CONTAINS(c.nameLower, @nameLower)
            """
            params = [
                {"name": "@nameLower", "value": name_lower},
                {"name": "@maxResults", "value": max_results}
            ]
        
        try:
            items = list(self._container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))
            return [self._doc_to_entity(item) for item in items]
        except Exception as e:
            logger.error(f"Error searching sanctions by name '{name}': {e}")
            return []
    
    def search_by_country(
        self, 
        country: str, 
        max_results: int = 50
    ) -> List[SanctionedEntity]:
        """
        Search for sanctioned entities associated with a country.
        
        Searches both address country and nationality fields.
        
        Args:
            country: Country name to search for
            max_results: Maximum number of results
            
        Returns:
            List of matching sanctioned entities
        """
        country_lower = country.lower().strip()
        
        query = """
            SELECT TOP @maxResults * FROM c 
            WHERE CONTAINS(LOWER(c.addressCountry), @country)
               OR CONTAINS(LOWER(c.nationality), @country)
        """
        params = [
            {"name": "@country", "value": country_lower},
            {"name": "@maxResults", "value": max_results}
        ]
        
        try:
            items = list(self._container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))
            return [self._doc_to_entity(item) for item in items]
        except Exception as e:
            logger.error(f"Error searching sanctions by country '{country}': {e}")
            return []
    
    def get_by_regime(
        self, 
        regime_code: str, 
        max_results: int = 100
    ) -> List[SanctionedEntity]:
        """
        Get all sanctioned entities for a specific sanctions regime.
        
        This is a partition-targeted query (efficient).
        
        Args:
            regime_code: Regime code (e.g., 'RUS', 'IRN', 'PRK')
            max_results: Maximum number of results
            
        Returns:
            List of sanctioned entities under that regime
        """
        query = "SELECT TOP @maxResults * FROM c WHERE c.regimeCode = @regimeCode"
        params = [
            {"name": "@regimeCode", "value": regime_code},
            {"name": "@maxResults", "value": max_results}
        ]
        
        try:
            items = list(self._container.query_items(
                query=query,
                parameters=params,
                partition_key=regime_code
            ))
            return [self._doc_to_entity(item) for item in items]
        except Exception as e:
            logger.error(f"Error getting sanctions by regime '{regime_code}': {e}")
            return []
    
    def check_entity(
        self, 
        name: str, 
        country: Optional[str] = None,
        strict_match: bool = False
    ) -> Dict[str, Any]:
        """
        Comprehensive entity screening against the sanctions list.
        
        This is the main method for compliance screening. Returns detailed
        match information including potential matches and confidence levels.
        
        Args:
            name: Entity name to screen
            country: Optional country for filtering/relevance scoring
            strict_match: If True, require more exact name matching
            
        Returns:
            Dictionary with:
            - matched: bool indicating if any matches found
            - matches: List of matching entities with relevance scores
            - exact_matches: Count of exact name matches
            - partial_matches: Count of partial matches
        """
        result = {
            "matched": False,
            "matches": [],
            "exact_matches": 0,
            "partial_matches": 0,
            "screened_name": name,
            "screened_country": country
        }
        
        name_lower = name.lower().strip()
        
        # Search for matches
        entities = self.search_by_name(name, max_results=50)
        
        for entity in entities:
            entity_name_lower = entity.name.lower()
            
            # Calculate match type
            if entity_name_lower == name_lower:
                match_type = "exact"
                relevance = 1.0
                result["exact_matches"] += 1
            elif name_lower in entity_name_lower or entity_name_lower in name_lower:
                match_type = "strong_partial"
                relevance = 0.8
                result["partial_matches"] += 1
            else:
                match_type = "partial"
                relevance = 0.5
                result["partial_matches"] += 1
            
            # Boost relevance if country matches
            if country:
                country_lower = country.lower()
                if country_lower in entity.nationality.lower() or \
                   country_lower in entity.address_country.lower():
                    relevance = min(1.0, relevance + 0.2)
            
            # Skip weak matches in strict mode
            if strict_match and relevance < 0.8:
                continue
            
            result["matches"].append({
                "entity": {
                    "unique_id": entity.unique_id,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "regime_name": entity.regime_name,
                    "sanctions_imposed": entity.sanctions_imposed,
                    "nationality": entity.nationality,
                    "address_country": entity.address_country
                },
                "match_type": match_type,
                "relevance": relevance
            })
        
        # Sort by relevance
        result["matches"].sort(key=lambda x: x["relevance"], reverse=True)
        result["matched"] = len(result["matches"]) > 0
        
        return result
    
    def get_sanctioned_countries(self) -> List[str]:
        """
        Get list of unique regime codes in the sanctions database.
        
        Returns:
            List of regime codes (e.g., ['RUS', 'IRN', 'PRK', ...])
        """
        query = "SELECT DISTINCT c.regimeCode FROM c"
        
        try:
            items = list(self._container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            return [item['regimeCode'] for item in items if item.get('regimeCode')]
        except Exception as e:
            logger.error(f"Error getting sanctioned countries: {e}")
            return []
    
    def get_regime_statistics(self) -> Dict[str, int]:
        """
        Get count of sanctioned entities per regime.
        
        Returns:
            Dictionary mapping regime codes to entity counts
        """
        query = """
            SELECT c.regimeCode, COUNT(1) as count 
            FROM c 
            GROUP BY c.regimeCode
        """
        
        try:
            items = list(self._container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            return {item['regimeCode']: item['count'] for item in items}
        except Exception as e:
            logger.error(f"Error getting regime statistics: {e}")
            return {}
    
    def _doc_to_entity(self, doc: Dict[str, Any]) -> SanctionedEntity:
        """Convert a CosmosDB document to a SanctionedEntity"""
        return SanctionedEntity(
            unique_id=doc.get('uniqueId', ''),
            name=doc.get('name', ''),
            entity_type=doc.get('entityType', ''),
            regime_code=doc.get('regimeCode', ''),
            regime_name=doc.get('regimeName', ''),
            sanctions_imposed=doc.get('sanctionsImposed', ''),
            nationality=doc.get('nationality', ''),
            address_country=doc.get('addressCountry', ''),
            designation_type=doc.get('designationType', ''),
            ofsi_group_id=doc.get('ofsiGroupId', ''),
            date_designated=doc.get('dateDesignated', ''),
            other_information=doc.get('otherInformation', '')
        )
