#!/usr/bin/env python3
"""
Azure AI Search Indexer

Indexes HS codes and sanctions data into Azure AI Search for use by Foundry agents.
This replaces CosmosDB-based indexing with native Foundry tool integration.

Usage:
    python scripts/index_to_search.py [--index hs-codes|sanctions|all] [--force]
"""

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose Azure SDK logging
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logging.getLogger('azure.search').setLevel(logging.WARNING)

# Configuration
SEARCH_SERVICE_ENDPOINT = os.getenv('AZURE_SEARCH_ENDPOINT')
SEARCH_SERVICE_NAME = os.getenv('AZURE_SEARCH_SERVICE_NAME', 'autonomousflow-search')

# Default paths for data files
HS_CODES_CSV = os.path.join(
    os.path.dirname(__file__), 
    '..', 
    'StaticDataForAgents', 
    'uk-tariff-2021-01-01--v4.0.1205--commodities-report.csv'
)
SANCTIONS_CSV = os.path.join(
    os.path.dirname(__file__), 
    '..', 
    'StaticDataForAgents', 
    'UK-Sanctions-List.csv'
)

# Index names
HS_CODES_INDEX = 'hs-codes'
SANCTIONS_INDEX = 'sanctions'


def get_search_endpoint() -> str:
    """Get the Azure AI Search endpoint."""
    if SEARCH_SERVICE_ENDPOINT:
        return SEARCH_SERVICE_ENDPOINT
    return f"https://{SEARCH_SERVICE_NAME}.search.windows.net"


def get_index_client() -> SearchIndexClient:
    """Get the Search Index Client for managing indexes."""
    endpoint = get_search_endpoint()
    credential = DefaultAzureCredential()
    return SearchIndexClient(endpoint=endpoint, credential=credential)


def get_search_client(index_name: str) -> SearchClient:
    """Get the Search Client for a specific index."""
    endpoint = get_search_endpoint()
    credential = DefaultAzureCredential()
    return SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)


# =============================================================================
# HS Codes Index
# =============================================================================

def create_hs_codes_index_schema() -> SearchIndex:
    """Create the schema for the HS codes index."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="code", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchableField(name="description", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SimpleField(name="chapter_code", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="heading_code", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="subheading_code", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="chapter_description", type=SearchFieldDataType.String),
        SimpleField(name="valid_from", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="valid_to", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="parent_code", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="data_source", type=SearchFieldDataType.String, filterable=True),
    ]
    
    # Semantic configuration for better search results
    semantic_config = SemanticConfiguration(
        name="hs-codes-semantic",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="code"),
            content_fields=[SemanticField(field_name="description")],
            keywords_fields=[SemanticField(field_name="chapter_description")]
        )
    )
    
    return SearchIndex(
        name=HS_CODES_INDEX,
        fields=fields,
        semantic_search=SemanticSearch(configurations=[semantic_config])
    )


def parse_hs_code(code: str) -> dict[str, str]:
    """Parse a 10-digit HS code into its components."""
    clean_code = ''.join(filter(str.isdigit, code))
    clean_code = clean_code.ljust(10, '0')
    
    return {
        'chapter': clean_code[:2],
        'heading': clean_code[:4],
        'subheading': clean_code[:6],
        'full_code': clean_code,
    }


def transform_hs_code_row(row: dict[str, str], row_id: int) -> dict[str, Any] | None:
    """Transform a CSV row into a search document."""
    code = row.get('commodity__code', '')
    description = row.get('commodity__description', '')
    
    if not code or not description:
        return None
    
    parsed = parse_hs_code(code)
    
    return {
        "id": f"hs-{row.get('id', row_id)}",
        "code": parsed['full_code'],
        "description": description,
        "chapter_code": parsed['chapter'],
        "heading_code": parsed['heading'],
        "subheading_code": parsed['subheading'],
        "chapter_description": "",  # Could be enriched later
        "valid_from": row.get('commodity__validity_start', ''),
        "valid_to": row.get('commodity__validity_end', ''),
        "parent_code": row.get('parent__code', ''),
        "data_source": "uk-tariff-2021",
    }


async def index_hs_codes(force: bool = False):
    """Index HS codes into Azure AI Search."""
    logger.info(f"Starting HS codes indexing from: {HS_CODES_CSV}")
    
    # Create or update index
    index_client = get_index_client()
    
    try:
        existing = index_client.get_index(HS_CODES_INDEX)
        if not force:
            logger.info(f"Index '{HS_CODES_INDEX}' already exists. Use --force to recreate.")
            return
        logger.info(f"Deleting existing index '{HS_CODES_INDEX}'...")
        index_client.delete_index(HS_CODES_INDEX)
    except Exception:
        pass  # Index doesn't exist
    
    logger.info(f"Creating index '{HS_CODES_INDEX}'...")
    index_client.create_index(create_hs_codes_index_schema())
    
    # Load and transform documents
    logger.info("Loading documents from CSV...")
    documents = []
    with open(HS_CODES_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row_id, row in enumerate(reader, start=1):
            doc = transform_hs_code_row(row, row_id)
            if doc:
                documents.append(doc)
    
    logger.info(f"Prepared {len(documents):,} documents")
    
    # Upload in batches
    search_client = get_search_client(HS_CODES_INDEX)
    batch_size = 1000
    total_uploaded = 0
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        result = search_client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        total_uploaded += succeeded
        pct = (i + len(batch)) / len(documents) * 100
        logger.info(f"Progress: {i + len(batch):,}/{len(documents):,} ({pct:.1f}%) - {total_uploaded:,} uploaded")
    
    logger.info(f"✓ Indexed {total_uploaded:,} HS codes to Azure AI Search")


# =============================================================================
# Sanctions Index
# =============================================================================

# Regime code mapping
REGIME_CODES = {
    'afghanistan': 'AFG', 'belarus': 'BLR', 'burundi': 'BDI',
    'central african republic': 'CAF', 'chemical weapons': 'CW',
    'cyber': 'CYBER', 'democratic republic of the congo': 'COD',
    'guinea': 'GIN', 'guinea-bissau': 'GNB', 'haiti': 'HTI',
    'iran': 'IRN', 'iraq': 'IRQ', 'isil': 'ISIL', 'lebanon': 'LBN',
    'libya': 'LBY', 'mali': 'MLI', 'myanmar': 'MMR', 'nicaragua': 'NIC',
    'north korea': 'PRK', 'russia': 'RUS', 'somalia': 'SOM',
    'south sudan': 'SSD', 'sudan': 'SDN', 'syria': 'SYR',
    'terrorism': 'TERR', 'venezuela': 'VEN', 'yemen': 'YEM',
    'zimbabwe': 'ZWE', 'global human rights': 'GHR',
    'global anti-corruption': 'GAC', 'counter-terrorism': 'CT',
}


def create_sanctions_index_schema() -> SearchIndex:
    """Create the schema for the sanctions index."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="unique_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="name", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SearchableField(name="aliases", type=SearchFieldDataType.String),
        SimpleField(name="entity_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="regime_code", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="regime_name", type=SearchFieldDataType.String),
        SimpleField(name="country", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="sanctions_imposed", type=SearchFieldDataType.String),
        SearchableField(name="other_information", type=SearchFieldDataType.String),
        SimpleField(name="designation_date", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="last_updated", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="data_source", type=SearchFieldDataType.String, filterable=True),
    ]
    
    # Semantic configuration
    semantic_config = SemanticConfiguration(
        name="sanctions-semantic",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="name"),
            content_fields=[
                SemanticField(field_name="other_information"),
                SemanticField(field_name="sanctions_imposed")
            ],
            keywords_fields=[
                SemanticField(field_name="regime_name"),
                SemanticField(field_name="country")
            ]
        )
    )
    
    return SearchIndex(
        name=SANCTIONS_INDEX,
        fields=fields,
        semantic_search=SemanticSearch(configurations=[semantic_config])
    )


def extract_regime_code(regime_name: str) -> str:
    """Extract a regime code from the regime name."""
    if not regime_name:
        return 'UNK'
    
    regime_lower = regime_name.lower()
    for key, code in REGIME_CODES.items():
        if key in regime_lower:
            return code
    
    return 'OTHER'


def build_name(row: dict[str, str]) -> str:
    """Build full name from name components."""
    name_parts = []
    for i in range(1, 7):
        name = row.get(f'Name {i}', '').strip()
        if name:
            name_parts.append(name)
    return ' '.join(name_parts) if name_parts else ''


def transform_sanctions_row(row: dict[str, str], row_num: int) -> dict[str, Any] | None:
    """Transform a CSV row into a search document."""
    unique_id = row.get('Unique ID', '')
    name = build_name(row)
    
    if not unique_id or not name:
        return None
    
    regime_name = row.get('Regime Name', '')
    
    return {
        "id": f"sanc-{unique_id}-{row_num}",
        "unique_id": unique_id,
        "name": name,
        "aliases": row.get('Name non-latin script', ''),
        "entity_type": row.get('Type of entity', '') or row.get('Designation Type', ''),
        "regime_code": extract_regime_code(regime_name),
        "regime_name": regime_name,
        "country": row.get('Address Country', '') or row.get('Country of birth', ''),
        "sanctions_imposed": row.get('Sanctions Imposed', ''),
        "other_information": row.get('Other Information', ''),
        "designation_date": row.get('Date Designated', ''),
        "last_updated": row.get('Last Updated', ''),
        "data_source": "uk-sanctions-ofsi",
    }


async def index_sanctions(force: bool = False):
    """Index sanctions into Azure AI Search."""
    logger.info(f"Starting sanctions indexing from: {SANCTIONS_CSV}")
    
    # Create or update index
    index_client = get_index_client()
    
    try:
        existing = index_client.get_index(SANCTIONS_INDEX)
        if not force:
            logger.info(f"Index '{SANCTIONS_INDEX}' already exists. Use --force to recreate.")
            return
        logger.info(f"Deleting existing index '{SANCTIONS_INDEX}'...")
        index_client.delete_index(SANCTIONS_INDEX)
    except Exception:
        pass  # Index doesn't exist
    
    logger.info(f"Creating index '{SANCTIONS_INDEX}'...")
    index_client.create_index(create_sanctions_index_schema())
    
    # Load and transform documents
    logger.info("Loading documents from CSV...")
    documents = []
    seen_ids = set()
    
    with open(SANCTIONS_CSV, 'r', encoding='utf-8') as f:
        # Skip report date line if present
        first_line = f.readline()
        if not first_line.startswith('Last Updated'):
            pass
        else:
            f.seek(0)
        
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=1):
            doc = transform_sanctions_row(row, row_num)
            if doc:
                # Handle duplicates
                entity_key = f"{doc['unique_id']}-{doc['name']}"
                if entity_key in seen_ids:
                    doc['id'] = f"sanc-{doc['unique_id']}-{row_num}"
                seen_ids.add(entity_key)
                documents.append(doc)
    
    logger.info(f"Prepared {len(documents):,} documents ({len(seen_ids):,} unique entities)")
    
    # Upload in batches
    search_client = get_search_client(SANCTIONS_INDEX)
    batch_size = 1000
    total_uploaded = 0
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        result = search_client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        total_uploaded += succeeded
        pct = (i + len(batch)) / len(documents) * 100
        logger.info(f"Progress: {i + len(batch):,}/{len(documents):,} ({pct:.1f}%) - {total_uploaded:,} uploaded")
    
    logger.info(f"✓ Indexed {total_uploaded:,} sanctions records to Azure AI Search")


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description='Index data into Azure AI Search')
    parser.add_argument(
        '--index',
        choices=['hs-codes', 'sanctions', 'all'],
        default='all',
        help='Which index to create/update'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force recreate indexes even if they exist'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Azure AI Search Indexer")
    logger.info("=" * 60)
    logger.info(f"Search Endpoint: {get_search_endpoint()}")
    logger.info("")
    
    if args.index in ['hs-codes', 'all']:
        await index_hs_codes(force=args.force)
        logger.info("")
    
    if args.index in ['sanctions', 'all']:
        await index_sanctions(force=args.force)
        logger.info("")
    
    logger.info("=" * 60)
    logger.info("Indexing complete!")
    logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
