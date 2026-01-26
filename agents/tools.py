"""
Compliance Tools Module

This module defines tools (functions) that agents can invoke to access
reference data from CosmosDB and perform compliance checks.

Tools are defined using the @ai_function decorator from Microsoft Agent Framework.
"""

from typing import Annotated, Optional, Any
from pydantic import Field

from agent_framework import ai_function

# These will be initialized when the workflow starts
_hs_code_service = None
_sanctions_service = None


def initialize_services(hs_code_service, sanctions_service):
    """Initialize the reference data services for tools to use."""
    global _hs_code_service, _sanctions_service
    _hs_code_service = hs_code_service
    _sanctions_service = sanctions_service


# =============================================================================
# HS Code Tools
# =============================================================================

@ai_function(
    name="lookup_hs_code",
    description="Look up an HS code in the UK Tariff database to get its description and details"
)
def lookup_hs_code(
    code: Annotated[str, Field(description="The HS code to look up (4-10 digits)")]
) -> dict[str, Any]:
    """
    Look up an HS code in the UK Tariff database.
    
    Returns the code description, chapter, heading, and validity information.
    """
    if _hs_code_service is None:
        return {"error": "HS code service not initialized", "found": False}
    
    try:
        result = _hs_code_service.lookup_code(code)
        if result:
            return {
                "found": True,
                "code": result.get("code", code),
                "description": result.get("description", ""),
                "chapter": result.get("chapterCode", ""),
                "chapter_description": result.get("chapterDescription", ""),
                "heading": result.get("headingCode", ""),
                "valid_from": result.get("validFrom", ""),
                "valid_to": result.get("validTo", ""),
            }
        else:
            return {"found": False, "code": code, "message": "Code not found in UK Tariff database"}
    except Exception as e:
        return {"error": str(e), "found": False}


@ai_function(
    name="search_hs_codes_by_description",
    description="Search for HS codes matching a goods description"
)
def search_hs_codes_by_description(
    description: Annotated[str, Field(description="The goods description to search for")],
    max_results: Annotated[int, Field(description="Maximum number of results to return")] = 10
) -> dict[str, Any]:
    """
    Search for HS codes that match a goods description.
    
    Uses text search against the UK Tariff database.
    """
    if _hs_code_service is None:
        return {"error": "HS code service not initialized", "results": []}
    
    try:
        results = _hs_code_service.search_by_description(description, max_results=max_results)
        return {
            "query": description,
            "result_count": len(results),
            "results": [
                {
                    "code": r.get("code", ""),
                    "description": r.get("description", ""),
                    "chapter": r.get("chapterCode", ""),
                }
                for r in results
            ]
        }
    except Exception as e:
        return {"error": str(e), "results": []}


@ai_function(
    name="validate_hs_code_format",
    description="Validate the format of an HS code"
)
def validate_hs_code_format(
    code: Annotated[str, Field(description="The HS code to validate")]
) -> dict[str, Any]:
    """
    Validate that an HS code has the correct format.
    
    HS codes should be 4-10 digits, optionally with dots or spaces.
    """
    if _hs_code_service is None:
        # Basic validation without service
        import re
        cleaned = re.sub(r'[\s\.\-]', '', code)
        is_valid = bool(re.match(r'^\d{4,10}$', cleaned))
        return {
            "code": code,
            "normalized": cleaned,
            "is_valid_format": is_valid,
            "message": "Valid format" if is_valid else "Invalid format: must be 4-10 digits"
        }
    
    try:
        result = _hs_code_service.validate_code_format(code)
        return result
    except Exception as e:
        return {"error": str(e), "is_valid_format": False}


@ai_function(
    name="find_similar_hs_codes",
    description="Find HS codes similar to a given code (for suggestions when code not found)"
)
def find_similar_hs_codes(
    code: Annotated[str, Field(description="The HS code to find similar codes for")],
    max_results: Annotated[int, Field(description="Maximum number of results")] = 5
) -> dict[str, Any]:
    """
    Find HS codes with similar prefixes or in the same chapter.
    
    Useful for suggesting alternatives when a code is not found.
    """
    if _hs_code_service is None:
        return {"error": "HS code service not initialized", "similar_codes": []}
    
    try:
        results = _hs_code_service.find_similar_codes(code, max_results=max_results)
        return {
            "original_code": code,
            "similar_codes": [
                {
                    "code": r.get("code", ""),
                    "description": r.get("description", ""),
                }
                for r in results
            ]
        }
    except Exception as e:
        return {"error": str(e), "similar_codes": []}


# =============================================================================
# Sanctions Tools
# =============================================================================

@ai_function(
    name="search_sanctions_by_name",
    description="Search UK Sanctions List (OFSI) for entities by name"
)
def search_sanctions_by_name(
    name: Annotated[str, Field(description="The name to search for (partial match supported)")],
    entity_type: Annotated[Optional[str], Field(description="Filter by entity type: Individual, Entity, or Ship")] = None,
    max_results: Annotated[int, Field(description="Maximum number of results")] = 20
) -> dict[str, Any]:
    """
    Search the UK Sanctions List for entities matching a name.
    
    Performs case-insensitive partial matching.
    """
    if _sanctions_service is None:
        return {"error": "Sanctions service not initialized", "matches": []}
    
    try:
        entities = _sanctions_service.search_by_name(name, max_results=max_results, entity_type=entity_type)
        return {
            "query": name,
            "match_count": len(entities),
            "matches": [
                {
                    "name": e.name,
                    "unique_id": e.unique_id,
                    "entity_type": e.entity_type,
                    "regime_name": e.regime_name,
                    "sanctions_imposed": e.sanctions_imposed[:200] if e.sanctions_imposed else "",
                    "nationality": e.nationality,
                    "address_country": e.address_country,
                }
                for e in entities
            ]
        }
    except Exception as e:
        return {"error": str(e), "matches": []}


@ai_function(
    name="search_sanctions_by_country",
    description="Search UK Sanctions List for entities associated with a country"
)
def search_sanctions_by_country(
    country: Annotated[str, Field(description="The country name to search for")],
    max_results: Annotated[int, Field(description="Maximum number of results")] = 50
) -> dict[str, Any]:
    """
    Search for sanctioned entities associated with a country.
    
    Searches both address country and nationality fields.
    """
    if _sanctions_service is None:
        return {"error": "Sanctions service not initialized", "matches": []}
    
    try:
        entities = _sanctions_service.search_by_country(country, max_results=max_results)
        
        # Group by regime for summary
        regimes = {}
        for e in entities:
            regime = e.regime_name or "Unknown"
            if regime not in regimes:
                regimes[regime] = 0
            regimes[regime] += 1
        
        return {
            "query_country": country,
            "total_matches": len(entities),
            "regimes_involved": regimes,
            "sample_entities": [
                {
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "regime_name": e.regime_name,
                }
                for e in entities[:10]  # First 10 as sample
            ]
        }
    except Exception as e:
        return {"error": str(e), "matches": []}


@ai_function(
    name="check_entity_sanctions",
    description="Comprehensive sanctions screening for an entity name with relevance scoring"
)
def check_entity_sanctions(
    name: Annotated[str, Field(description="The entity name to screen")],
    country: Annotated[Optional[str], Field(description="Country for filtering/relevance boost")] = None,
    strict_match: Annotated[bool, Field(description="If true, require stricter name matching")] = False
) -> dict[str, Any]:
    """
    Perform comprehensive sanctions screening on an entity name.
    
    Returns detailed match information including relevance scores and match types.
    This is the main method for compliance screening.
    """
    if _sanctions_service is None:
        return {"error": "Sanctions service not initialized", "matched": False}
    
    try:
        result = _sanctions_service.check_entity(name, country=country, strict_match=strict_match)
        return {
            "screened_name": result["screened_name"],
            "screened_country": result["screened_country"],
            "matched": result["matched"],
            "exact_matches": result["exact_matches"],
            "partial_matches": result["partial_matches"],
            "total_matches": len(result["matches"]),
            "matches": result["matches"][:10],  # Top 10 matches with details
        }
    except Exception as e:
        return {"error": str(e), "matched": False}


@ai_function(
    name="get_sanctions_regimes",
    description="Get list of active sanctions regimes in the database"
)
def get_sanctions_regimes() -> dict[str, Any]:
    """
    Get statistics on sanctions regimes in the database.
    
    Returns regime codes and entity counts.
    """
    if _sanctions_service is None:
        return {"error": "Sanctions service not initialized", "regimes": {}}
    
    try:
        stats = _sanctions_service.get_regime_statistics()
        return {
            "regime_count": len(stats),
            "regimes": stats,
        }
    except Exception as e:
        return {"error": str(e), "regimes": {}}


# =============================================================================
# Export all tools
# =============================================================================

HS_CODE_TOOLS = [
    lookup_hs_code,
    search_hs_codes_by_description,
    validate_hs_code_format,
    find_similar_hs_codes,
]

SANCTIONS_TOOLS = [
    search_sanctions_by_name,
    search_sanctions_by_country,
    check_entity_sanctions,
    get_sanctions_regimes,
]

ALL_TOOLS = HS_CODE_TOOLS + SANCTIONS_TOOLS
