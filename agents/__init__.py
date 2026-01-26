"""
Customs Compliance Agents Module

This module provides the agent definitions and workflow for customs compliance analysis
using PERSISTENT agents in Azure AI Foundry.

Key Features:
- Agents are created and stored in Azure AI Foundry (visible in portal)
- Agents persist between workflow runs
- Agents can be managed via the Foundry portal or CLI

Components:
- Agent YAML definitions (7 specialized compliance agents)
- tools.py: Function tools for CosmosDB reference data
- workflow.py: Microsoft Agent Framework workflow with Foundry agents

Usage:
    from agents.workflow import (
        run_compliance_check,
        create_foundry_agents,
        cleanup_foundry_agents,
        list_foundry_agents,
    )
    
    # Create agents in Foundry (one-time setup)
    agent_ids = await create_foundry_agents()
    
    # Run compliance check
    report = await run_compliance_check({
        "shipper": "...",
        "goods_description": "...",
        "hs_code": "...",
        ...
    })
"""

from .workflow import (
    run_compliance_check,
    create_foundry_agents,
    cleanup_foundry_agents,
    list_foundry_agents,
    Finding,
    AgentResult,
    ComplianceReport,
    Severity,
    Confidence,
)

from .tools import (
    initialize_services,
    lookup_hs_code,
    search_hs_codes_by_description,
    validate_hs_code_format,
    find_similar_hs_codes,
    search_sanctions_by_name,
    search_sanctions_by_country,
    check_entity_sanctions,
    get_sanctions_regimes,
    HS_CODE_TOOLS,
    SANCTIONS_TOOLS,
    ALL_TOOLS,
)

__all__ = [
    # Workflow functions
    "run_compliance_check",
    "create_foundry_agents",
    "cleanup_foundry_agents",
    "list_foundry_agents",
    
    # Data models
    "Finding",
    "AgentResult",
    "ComplianceReport",
    "Severity",
    "Confidence",
    
    # Services init
    "initialize_services",
    
    # Tool functions
    "lookup_hs_code",
    "search_hs_codes_by_description",
    "validate_hs_code_format",
    "find_similar_hs_codes",
    "search_sanctions_by_name",
    "search_sanctions_by_country",
    "check_entity_sanctions",
    "get_sanctions_regimes",
    
    # Tool collections
    "HS_CODE_TOOLS",
    "SANCTIONS_TOOLS",
    "ALL_TOOLS",
]
