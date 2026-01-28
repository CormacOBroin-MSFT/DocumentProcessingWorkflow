"""
Customs Compliance Workflow with Azure AI Foundry Persistent Agents

This module implements the customs compliance workflow using Microsoft Agent Framework
with PERSISTENT agents created in Azure AI Foundry. These agents are visible in
the Azure AI Foundry portal and can be managed, monitored, and reused.

WORKFLOW ARCHITECTURE:
The workflow uses a fan-out/fan-in pattern for concurrent agent execution:

    ┌─────────────┐
    │  Dispatcher │  (receives declaration data)
    └──────┬──────┘
           │ fan-out (parallel execution)
    ┌──────┼──────┬──────┬──────┬──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐
  │Doc│  │HS │  │Cty│  │Org│  │Ctl│  │Val│  │Shp│
  │Con│  │Cod│  │Rst│  │Cty│  │Gds│  │Rsn│  │Ver│
  └───┘  └───┘  └───┘  └───┘  └───┘  └───┘  └───┘
    │      │      │      │      │      │      │
    └──────┴──────┴──────┴──────┴──────┴──────┘
           │ fan-in (aggregation)
    ┌──────┴──────┐
    │  Aggregator │  (combines findings → ComplianceReport)
    └─────────────┘

TRACING & VISUALIZATION:
- Uses OpenTelemetry for distributed tracing
- Traces are visible in VS Code AI Toolkit's trace viewer
- Each agent execution is a separate span within the workflow

Best Practices Reference:
- https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/azure-ai-foundry-agent
- https://learn.microsoft.com/en-us/agent-framework/tutorials/workflows/simple-concurrent-workflow

Usage:
    # Create agents in Foundry and run workflow
    python workflow.py --create
    
    # Run workflow with tracing enabled (viewable in AI Toolkit)
    python workflow.py --run --trace
    
    # Delete agents from Foundry
    python workflow.py --cleanup

Or import and use programmatically:
    from workflow import run_compliance_check, create_foundry_agents, cleanup_foundry_agents
"""

import asyncio
import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from agent_framework import (
    AgentResponseUpdate,
    ChatAgent,
    ConcurrentBuilder,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    ExecutorInvokedEvent,
    ExecutorCompletedEvent,
    handler,
)
from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
    BingGroundingAgentTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from typing_extensions import Never

# Add backend to path for service imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Import tools for local workflow execution
from tools import (
    initialize_services,
    HS_CODE_TOOLS,
    SANCTIONS_TOOLS,
    lookup_hs_code,
    search_hs_codes_by_description,
    validate_hs_code_format,
    find_similar_hs_codes,
    search_sanctions_by_name,
    search_sanctions_by_country,
    check_entity_sanctions,
    get_sanctions_regimes,
)

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

# Configuration
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
AZURE_AI_MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-41")
AZURE_AI_MODEL_MINI_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_MINI_DEPLOYMENT_NAME", "gpt-41-mini")

# File to store created agent IDs for reuse
AGENT_IDS_FILE = os.path.join(os.path.dirname(__file__), ".foundry_agent_ids.json")

# File to store workflow ID for reuse
WORKFLOW_IDS_FILE = os.path.join(os.path.dirname(__file__), ".foundry_workflow_ids.json")


# =============================================================================
# OpenTelemetry Tracing Setup
# =============================================================================

def setup_tracing(enable: bool = True) -> None:
    """Configure OpenTelemetry tracing for workflow visualization.
    
    When enabled, traces are exported to the AI Toolkit trace viewer in VS Code.
    This allows you to see the fan-out/fan-in pattern visually with timing info.
    """
    if not enable:
        return
    
    try:
        from agent_framework.observability import configure_otel_providers
        
        configure_otel_providers(
            vs_code_extension_port=4317,  # AI Toolkit gRPC port
            enable_sensitive_data=True,   # Capture prompts and completions
        )
        print("✓ OpenTelemetry tracing enabled (AI Toolkit port 4317)")
        print("  View traces in VS Code: AI Toolkit → Tracing")
    except ImportError:
        print("⚠ OpenTelemetry not available. Install with: pip install opentelemetry-exporter-otlp-proto-grpc")
    except Exception as e:
        print(f"⚠ Could not enable tracing: {e}")


# =============================================================================
# Data Models
# =============================================================================

class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Finding:
    """A compliance finding from an agent"""
    code: str
    title: str
    description: str
    severity: Severity
    confidence: Confidence
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    agent: str = ""


@dataclass
class AgentResult:
    """Result from a single agent"""
    agent_name: str
    findings: list[Finding]
    processing_time_ms: int
    error: Optional[str] = None


@dataclass
class ComplianceReport:
    """Aggregated compliance report from all agents"""
    declaration_id: str
    timestamp: str
    agent_results: list[AgentResult]
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    overall_risk: str
    requires_manual_review: bool
    processing_time_ms: int
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# Agent Configuration
# =============================================================================

def load_agent_yaml(yaml_file: str) -> dict:
    """Load full agent configuration from a YAML file."""
    import yaml
    agent_dir = os.path.dirname(__file__)
    filepath = os.path.join(agent_dir, yaml_file)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def load_agent_instructions(yaml_file: str) -> str:
    """Load agent instructions from a YAML file."""
    data = load_agent_yaml(yaml_file)
    return data.get('instructions', '')


def load_agent_tools(yaml_file: str) -> list:
    """Load agent tools configuration from a YAML file.
    
    Returns a list of tool definitions that can be passed to the Foundry API.
    The YAML should contain tools in the Azure AI Foundry format with connection IDs.
    """
    data = load_agent_yaml(yaml_file)
    tools = data.get('tools', [])
    
    if not tools:
        return []
    
    # Convert YAML tool definitions to SDK tool objects
    sdk_tools = []
    for tool_def in tools:
        tool_type = tool_def.get('type')
        
        if tool_type == 'azure_ai_search':
            ai_search_config = tool_def.get('azure_ai_search', {})
            indexes = ai_search_config.get('indexes', [])
            
            index_resources = []
            for idx in indexes:
                # Map query_type string to enum
                query_type_str = idx.get('query_type', 'simple')
                query_type_map = {
                    'simple': AzureAISearchQueryType.SIMPLE,
                    'semantic': AzureAISearchQueryType.SEMANTIC,
                    'vector': AzureAISearchQueryType.VECTOR,
                    'hybrid': AzureAISearchQueryType.VECTOR_SIMPLE_HYBRID,
                    'hybrid_semantic': AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                }
                query_type = query_type_map.get(query_type_str, AzureAISearchQueryType.SIMPLE)
                
                index_resources.append(AISearchIndexResource(
                    project_connection_id=idx.get('project_connection_id'),
                    index_name=idx.get('index_name'),
                    query_type=query_type,
                    top_k=idx.get('top_k', 5),
                ))
            
            if index_resources:
                sdk_tools.append(AzureAISearchAgentTool(
                    azure_ai_search=AzureAISearchToolResource(indexes=index_resources)
                ))
        
        elif tool_type == 'bing_grounding':
            bing_config = tool_def.get('bing_grounding', {})
            search_configs = bing_config.get('search_configurations', [])
            
            if search_configs:
                config_objs = []
                for cfg in search_configs:
                    config_objs.append(BingGroundingSearchConfiguration(
                        project_connection_id=cfg.get('project_connection_id'),
                        market=cfg.get('market'),
                        set_lang=cfg.get('set_lang'),
                        count=cfg.get('count'),
                    ))
                
                sdk_tools.append(BingGroundingAgentTool(
                    bing_grounding=BingGroundingSearchToolParameters(
                        search_configurations=config_objs
                    )
                ))
    
    return sdk_tools


def get_agent_configs():
    """Get agent configurations.
    
    Tools are now loaded from YAML files (generated by setup-azure.sh with connection IDs).
    The 'local_tools' are only used for local workflow execution without Foundry.
    """
    return {
        "DocumentConsistencyAgent": {
            "yaml": "document-consistency-agent.yaml",
            "local_tools": [],
            "model": AZURE_AI_MODEL_MINI_DEPLOYMENT_NAME,
        },
        "HSCodeValidationAgent": {
            "yaml": "hs-code-validation-agent.yaml",
            "local_tools": [lookup_hs_code, search_hs_codes_by_description, validate_hs_code_format, find_similar_hs_codes],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
        "CountryRestrictionsAgent": {
            "yaml": "country-restrictions-agent.yaml",
            "local_tools": [search_sanctions_by_name, search_sanctions_by_country, check_entity_sanctions, get_sanctions_regimes],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
        "CountryOfOriginAgent": {
            "yaml": "country-of-origin-agent.yaml",
            "local_tools": [],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
        "ControlledGoodsAgent": {
            "yaml": "controlled-goods-agent.yaml",
            "local_tools": [],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
        "ValueReasonablenessAgent": {
            "yaml": "value-reasonableness-agent.yaml",
            "local_tools": [],
            "model": AZURE_AI_MODEL_MINI_DEPLOYMENT_NAME,
        },
        "ShipperVerificationAgent": {
            "yaml": "shipper-verification-agent.yaml",
            "local_tools": [search_sanctions_by_name, search_sanctions_by_country, check_entity_sanctions, get_sanctions_regimes],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
        "ComplianceAggregatorAgent": {
            "yaml": "compliance-aggregator-agent.yaml",
            "local_tools": [],
            "model": AZURE_AI_MODEL_DEPLOYMENT_NAME,
        },
    }


# Keep AGENT_CONFIGS for backward compatibility (evaluated at import time)
AGENT_CONFIGS = None  # Will be set in functions that need it


# =============================================================================
# Azure AI Foundry Agent Management
# =============================================================================

async def create_foundry_agents(delete_existing: bool = False) -> dict[str, str]:
    """
    Create PERSISTENT agents in Azure AI Foundry.
    
    These agents will be visible in the Azure AI Foundry portal and can be
    reused across multiple workflow runs.
    
    Args:
        delete_existing: If True, delete existing agents before creating new ones
        
    Returns:
        Dictionary mapping agent names to their Foundry agent IDs
    """
    if not AZURE_AI_PROJECT_ENDPOINT:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT environment variable is required")
    
    print("=" * 70)
    print("Creating Persistent Agents in Azure AI Foundry")
    print("=" * 70)
    print(f"Project Endpoint: {AZURE_AI_PROJECT_ENDPOINT}")
    print()
    
    agent_ids = {}
    
    # Load existing agent IDs if available
    existing_ids = {}
    if os.path.exists(AGENT_IDS_FILE) and not delete_existing:
        with open(AGENT_IDS_FILE, 'r') as f:
            existing_ids = json.load(f)
            print(f"Found {len(existing_ids)} existing agent IDs")
    
    # Get agent configs with current env vars
    agent_configs = get_agent_configs()
    
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=AZURE_AI_PROJECT_ENDPOINT, credential=credential) as project_client,
    ):
        # Verify existing agents still exist in Foundry
        if existing_ids and not delete_existing:
            all_exist = True
            for name in agent_configs.keys():
                if name not in existing_ids:
                    print(f"  Agent {name} not in cached IDs, will create")
                    all_exist = False
                    break
                try:
                    agent_name = existing_ids[name].split(":")[0] if ":" in existing_ids[name] else name
                    await project_client.agents.get(agent_name)
                except Exception:
                    print(f"  Agent {name} not found in Foundry, will recreate")
                    all_exist = False
                    break
            
            if all_exist:
                print("All agents exist in Foundry, skipping creation")
                return existing_ids
            else:
                existing_ids = {}  # Clear stale cache
        
        # Delete existing agents if requested
        if delete_existing and os.path.exists(AGENT_IDS_FILE):
            await cleanup_foundry_agents()
        
        # Create each agent
        for name, config in agent_configs.items():
            print(f"Creating agent: {name}...")
            
            yaml_file = config["yaml"]
            instructions = load_agent_instructions(yaml_file)
            if not instructions:
                instructions = f"You are the {name} compliance agent."
            
            model = config.get("model", AZURE_AI_MODEL_DEPLOYMENT_NAME)
            
            # Create the persistent agent in Foundry using Azure AI Projects 2.x API
            # Uses create_version() with PromptAgentDefinition including tools
            agent_definition = PromptAgentDefinition(
                model=model,
                instructions=instructions,
            )
            
            # Load tools from YAML file (generated by setup-azure.sh with connection IDs)
            tools = load_agent_tools(yaml_file)
            if tools:
                agent_definition["tools"] = tools
                tool_names = []
                for tool in tools:
                    if hasattr(tool, 'azure_ai_search') and tool.azure_ai_search:
                        for idx in tool.azure_ai_search.indexes:
                            tool_names.append(f"AI Search: {idx.index_name}")
                            print(f"    Tool: Azure AI Search index '{idx.index_name}'")
                    if hasattr(tool, 'bing_grounding') and tool.bing_grounding:
                        tool_names.append("Bing Web Search")
                        print(f"    Tool: Bing Grounding web search")
                print(f"    Total tools: {len(tools)}")
            else:
                print(f"    No tools configured (using LLM reasoning only)")
            
            created_agent = await project_client.agents.create_version(
                agent_name=name,
                definition=agent_definition,
            )
            
            agent_ids[name] = f"{created_agent.name}:{created_agent.version}"
            print(f"  ✓ Created: {name} (ID: {created_agent.id}, Version: {created_agent.version})")
        
        # Save agent IDs for future use
        with open(AGENT_IDS_FILE, 'w') as f:
            json.dump(agent_ids, f, indent=2)
        
        print()
        print(f"✓ Created {len(agent_ids)} agents in Azure AI Foundry")
        print(f"  Agent IDs saved to: {AGENT_IDS_FILE}")
        print()
        print("You can now view these agents in the Azure AI Foundry portal!")
        
        return agent_ids


async def cleanup_foundry_agents() -> None:
    """
    Delete all persistent agents from Azure AI Foundry.
    """
    if not os.path.exists(AGENT_IDS_FILE):
        print("No agent IDs file found. Nothing to clean up.")
        return
    
    with open(AGENT_IDS_FILE, 'r') as f:
        agent_ids = json.load(f)
    
    if not agent_ids:
        print("No agents to delete.")
        return
    
    print("=" * 70)
    print("Cleaning Up Agents from Azure AI Foundry")
    print("=" * 70)
    
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=AZURE_AI_PROJECT_ENDPOINT, credential=credential) as project_client,
    ):
        for name, agent_id in agent_ids.items():
            try:
                # agent_id format is "name:version" - delete by name (deletes all versions)
                agent_name = agent_id.split(":")[0] if ":" in agent_id else name
                await project_client.agents.delete(agent_name)
                print(f"  ✓ Deleted: {name} (ID: {agent_id})")
            except Exception as e:
                print(f"  ✗ Failed to delete {name}: {e}")
    
    # Remove the IDs file
    os.remove(AGENT_IDS_FILE)
    print()
    print("✓ Cleanup complete")


async def list_foundry_agents() -> list[dict]:
    """
    List all agents in the Azure AI Foundry project.
    """
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=AZURE_AI_PROJECT_ENDPOINT, credential=credential) as project_client,
    ):
        agents = []
        async for agent in project_client.agents.list():
            agents.append({
                "name": agent.name,
                "id": getattr(agent, 'id', 'N/A'),
                "model": getattr(agent, 'model', 'N/A'),
            })
        return agents


# =============================================================================
# Workflow Executors
# =============================================================================

class DeclarationDispatcher(Executor):
    """Dispatcher that fans out the declaration to all compliance agents."""

    @handler
    async def handle(self, declaration: dict[str, Any], ctx: WorkflowContext[dict[str, Any]]) -> None:
        if not declaration:
            raise RuntimeError("Declaration data is required")
        await ctx.send_message(declaration)


class ComplianceResultAggregator(Executor):
    """Aggregator that collects results from all agents (fan-in)."""

    @handler
    async def handle(
        self, 
        results: list[AgentResult], 
        ctx: WorkflowContext[Never, ComplianceReport]
    ) -> None:
        all_findings: list[Finding] = []
        total_time = 0
        
        for result in results:
            all_findings.extend(result.findings)
            total_time += result.processing_time_ms
        
        # Count by severity
        critical = sum(1 for f in all_findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in all_findings if f.severity == Severity.HIGH)
        medium = sum(1 for f in all_findings if f.severity == Severity.MEDIUM)
        low = sum(1 for f in all_findings if f.severity == Severity.LOW)
        info = sum(1 for f in all_findings if f.severity == Severity.INFO)
        
        # Determine risk level
        if critical > 0:
            overall_risk = "critical"
            requires_review = True
        elif high > 0:
            overall_risk = "high"
            requires_review = True
        elif medium > 1:
            overall_risk = "medium"
            requires_review = True
        elif medium > 0 or low > 0:
            overall_risk = "low"
            requires_review = False
        else:
            overall_risk = "clear"
            requires_review = False
        
        recommendations = self._generate_recommendations(all_findings, overall_risk)
        
        report = ComplianceReport(
            declaration_id=f"decl-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.utcnow().isoformat() + "Z",
            agent_results=results,
            total_findings=len(all_findings),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            info_count=info,
            overall_risk=overall_risk,
            requires_manual_review=requires_review,
            processing_time_ms=total_time,
            recommendations=recommendations,
        )
        
        await ctx.yield_output(report)
    
    def _generate_recommendations(self, findings: list[Finding], risk: str) -> list[str]:
        recommendations = []
        agents_with_issues = set(f.agent for f in findings if f.severity in [Severity.CRITICAL, Severity.HIGH])
        
        if "CountryRestrictionsAgent" in agents_with_issues:
            recommendations.append("Escalate to sanctions compliance officer for review")
        if "HSCodeValidationAgent" in agents_with_issues:
            recommendations.append("Verify HS code classification with tariff specialist")
        if "ControlledGoodsAgent" in agents_with_issues:
            recommendations.append("Check export license requirements before clearance")
        if "CountryOfOriginAgent" in agents_with_issues:
            recommendations.append("Request additional origin documentation from shipper")
        if "ValueReasonablenessAgent" in agents_with_issues:
            recommendations.append("Verify declared value against commercial invoices")
        
        if risk == "critical":
            recommendations.insert(0, "HOLD: Do not release shipment pending investigation")
        elif risk == "high":
            recommendations.insert(0, "Requires supervisor approval before clearance")
        
        return recommendations


class FoundryAgentExecutor(Executor):
    """
    Executor that wraps an Azure AI Foundry persistent agent.
    
    This executor uses an existing agent by name from Azure AI Foundry.
    """
    
    def __init__(
        self,
        agent_name: str,
        agent_id: str,
        provider: AzureAIProjectAgentProvider,
        tools: list | None = None,
        id: str | None = None,
    ):
        super().__init__(id=id or agent_name.lower().replace("agent", "").replace(" ", "_"))
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.provider = provider
        self.tools = tools or []
        self._agent = None
    
    @handler
    async def handle(self, declaration: dict[str, Any], ctx: WorkflowContext[AgentResult]) -> None:
        import time
        start = time.time()
        
        try:
            # Get the agent from Foundry by name using the provider
            agent = await self.provider.get_agent(name=self.agent_name)
            
            # Format and run
            prompt = self._format_declaration(declaration)
            result = await agent.run(prompt)
            
            # Parse findings
            findings = self._parse_findings(result.text if hasattr(result, 'text') else str(result))
            
            agent_result = AgentResult(
                agent_name=self.agent_name,
                findings=findings,
                processing_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            agent_result = AgentResult(
                agent_name=self.agent_name,
                findings=[],
                processing_time_ms=int((time.time() - start) * 1000),
                error=str(e),
            )
        
        await ctx.send_message(agent_result)
    
    def _format_declaration(self, declaration: dict[str, Any]) -> str:
        parts = ["Analyze this customs declaration for compliance issues:\n"]
        
        if "shipper" in declaration:
            shipper = declaration["shipper"]
            if isinstance(shipper, dict):
                parts.append(f"Shipper: {shipper.get('name', 'N/A')} ({shipper.get('country', 'N/A')})")
                parts.append(f"Shipper Address: {shipper.get('address', 'N/A')}")
            else:
                parts.append(f"Shipper: {shipper}")
        
        if "consignee" in declaration or "receiver" in declaration:
            consignee = declaration.get("consignee") or declaration.get("receiver")
            if isinstance(consignee, dict):
                parts.append(f"Consignee: {consignee.get('name', 'N/A')} ({consignee.get('country', 'N/A')})")
            else:
                parts.append(f"Consignee: {consignee}")
        
        if "goods" in declaration:
            parts.append("\nGoods:")
            for i, good in enumerate(declaration["goods"], 1):
                parts.append(f"  {i}. {good.get('description', 'N/A')}")
                parts.append(f"     HS Code: {good.get('hs_code', 'N/A')}")
                parts.append(f"     Value: {good.get('unit_value', 'N/A')} x {good.get('quantity', 'N/A')} = {good.get('total_value', 'N/A')} {good.get('currency', '')}")
                parts.append(f"     Origin: {good.get('country_of_origin', 'N/A')}")
        elif "goods_description" in declaration:
            parts.append(f"Goods: {declaration['goods_description']}")
            parts.append(f"HS Code: {declaration.get('hs_code', 'N/A')}")
            parts.append(f"Value: {declaration.get('declared_value', 'N/A')}")
            parts.append(f"Origin: {declaration.get('country_of_origin', 'N/A')}")
        
        parts.append(f"\nCountry of Dispatch: {declaration.get('country_of_dispatch', 'N/A')}")
        parts.append(f"Destination: {declaration.get('destination_country', declaration.get('port_of_entry', 'N/A'))}")
        parts.append(f"Total Value: {declaration.get('total_value', 'N/A')} {declaration.get('currency', '')}")
        parts.append(f"Transport Mode: {declaration.get('transport_mode', 'N/A')}")
        
        parts.append("\n\nProvide your analysis as JSON:")
        parts.append('{"findings": [{"code": "...", "title": "...", "description": "...", "severity": "low|medium|high|critical", "confidence": "low|medium|high", "evidence": [...]}]}')
        
        return "\n".join(parts)
    
    def _parse_findings(self, response_text: str) -> list[Finding]:
        findings = []
        
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
                
                for f in data.get("findings", []):
                    try:
                        findings.append(Finding(
                            code=f.get("code", "UNKNOWN"),
                            title=f.get("title", "Finding"),
                            description=f.get("description", ""),
                            severity=Severity(f.get("severity", "medium").lower()),
                            confidence=Confidence(f.get("confidence", "medium").lower()),
                            evidence=f.get("evidence", []),
                            metadata=f.get("metadata", {}),
                            agent=self.agent_name,
                        ))
                    except ValueError:
                        findings.append(Finding(
                            code=f.get("code", "UNKNOWN"),
                            title=f.get("title", "Finding"),
                            description=f.get("description", ""),
                            severity=Severity.MEDIUM,
                            confidence=Confidence.MEDIUM,
                            evidence=f.get("evidence", []),
                            metadata=f.get("metadata", {}),
                            agent=self.agent_name,
                        ))
        except (json.JSONDecodeError, ValueError):
            if response_text.strip():
                findings.append(Finding(
                    code="ANALYSIS_COMPLETE",
                    title=f"{self.agent_name} Analysis",
                    description=response_text[:500],
                    severity=Severity.INFO,
                    confidence=Confidence.LOW,
                    agent=self.agent_name,
                ))
        
        return findings


# =============================================================================
# Main Workflow
# =============================================================================

async def run_compliance_check(
    declaration_data: dict[str, Any],
    agent_ids: dict[str, str] | None = None,
) -> ComplianceReport:
    """
    Run a compliance check using Azure AI Foundry persistent agents.
    
    Args:
        declaration_data: The customs declaration to analyze
        agent_ids: Optional dict mapping agent names to Foundry agent IDs.
                   If not provided, will load from saved file or create new agents.
    
    Returns:
        ComplianceReport with aggregated findings from all agents
    """
    # Initialize reference services for tools
    try:
        from app.services.hs_code_reference import HSCodeReferenceService
        from app.services.sanctions_reference import SanctionsReferenceService
        
        hs_service = HSCodeReferenceService()
        sanctions_service = SanctionsReferenceService()
        initialize_services(hs_service, sanctions_service)
    except Exception as e:
        print(f"Warning: Could not initialize reference services: {e}")
    
    # Get or create agent IDs
    if agent_ids is None:
        if os.path.exists(AGENT_IDS_FILE):
            with open(AGENT_IDS_FILE, 'r') as f:
                agent_ids = json.load(f)
        else:
            agent_ids = await create_foundry_agents()
    
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=AZURE_AI_PROJECT_ENDPOINT, credential=credential) as project_client,
    ):
        # Create provider for getting agents
        provider = AzureAIProjectAgentProvider(project_client=project_client)
        
        # Create executors
        dispatcher = DeclarationDispatcher(id="dispatcher")
        aggregator = ComplianceResultAggregator(id="aggregator")
        
        # Create executor for each Foundry agent
        agent_configs = get_agent_configs()
        agent_executors = []
        for name, config in agent_configs.items():
            if name not in agent_ids:
                print(f"Warning: No agent ID for {name}, skipping")
                continue
            
            executor = FoundryAgentExecutor(
                agent_name=name,
                agent_id=agent_ids[name],
                provider=provider,
                tools=config.get("tools", []),
            )
            agent_executors.append(executor)
        
        # Build workflow with fan-out/fan-in pattern
        workflow = (
            WorkflowBuilder()
            .set_start_executor(dispatcher)
            .add_fan_out_edges(dispatcher, agent_executors)
            .add_fan_in_edges(agent_executors, aggregator)
            .build()
        )
        
        # Run workflow with progress tracking
        report: ComplianceReport | None = None
        completed_agents = set()
        total_agents = len(agent_executors)
        
        print(f"Running {total_agents} agents concurrently...")
        async for event in workflow.run_stream(declaration_data):
            if isinstance(event, ExecutorInvokedEvent):
                if event.executor_id not in ["dispatcher", "aggregator"]:
                    print(f"  ⏳ {event.executor_id} started...")
            elif isinstance(event, ExecutorCompletedEvent):
                if event.executor_id not in ["dispatcher", "aggregator"]:
                    completed_agents.add(event.executor_id)
                    print(f"  ✓ {event.executor_id} completed ({len(completed_agents)}/{total_agents})")
            elif isinstance(event, WorkflowOutputEvent):
                report = event.data
        
        if report is None:
            raise RuntimeError("Workflow completed without producing a report")
        
        return report


async def run_declarative_workflow(declaration: dict[str, Any], trace: bool = False) -> dict[str, Any]:
    """
    Run the compliance workflow using the declarative YAML format.
    
    This approach uses the agent_framework.declarative module to load and
    execute a YAML-defined workflow that references Foundry agents.
    """
    from pathlib import Path
    try:
        from agent_framework.declarative import WorkflowFactory
    except ImportError:
        print("Installing agent-framework-declarative...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "agent-framework-declarative", "--pre"])
        from agent_framework.declarative import WorkflowFactory
    
    # Setup tracing if enabled
    if trace:
        setup_tracing(enable=True)
    
    # Load the declarative workflow
    workflow_path = Path(__file__).parent / "foundry-workflow.yaml"
    
    async with (
        AzureCliCredential() as credential,
    ):
        # Create provider for Foundry agents  
        provider = AzureAIProjectAgentProvider(
            endpoint=AZURE_AI_PROJECT_ENDPOINT,
            credential=credential,
            model=AZURE_AI_MODEL_DEPLOYMENT_NAME,
        )
        
        # Load agent IDs if available
        agent_ids = {}
        if os.path.exists(AGENT_IDS_FILE):
            with open(AGENT_IDS_FILE) as f:
                agent_ids = json.load(f)
        
        # Create agents dict for the workflow factory
        # These will be fetched from Foundry when invoked
        agents = {}
        for name in agent_ids.keys():
            try:
                agent = await provider.get_agent(name=name)
                agents[name] = agent
            except Exception as e:
                print(f"  ⚠ Could not load agent {name}: {e}")
        
        # Create workflow factory with pre-loaded agents
        factory = WorkflowFactory(agents=agents)
        
        # Load and run workflow
        workflow = factory.create_workflow_from_yaml_path(workflow_path)
        
        print(f"✓ Loaded declarative workflow: {workflow.name}")
        print(f"  Agents registered: {list(agents.keys())}")
        print()
        
        # Run the workflow
        result = await workflow.run({"declaration": declaration})
        
        return result.get_outputs()


async def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Customs Compliance Workflow with Azure AI Foundry Agents")
    parser.add_argument("--create", action="store_true", help="Create agents in Azure AI Foundry")
    parser.add_argument("--cleanup", action="store_true", help="Delete agents from Azure AI Foundry")
    parser.add_argument("--list", action="store_true", help="List agents in Azure AI Foundry")
    parser.add_argument("--run", action="store_true", help="Run compliance check with sample data")
    parser.add_argument("--declarative", action="store_true", help="Run using declarative YAML workflow")
    parser.add_argument("--recreate", action="store_true", help="Delete existing agents and create new ones")
    parser.add_argument("--trace", action="store_true", help="Enable OpenTelemetry tracing for visualization")
    
    args = parser.parse_args()
    
    # Enable tracing if requested
    if args.trace:
        setup_tracing(enable=True)
    
    if args.cleanup:
        await cleanup_foundry_agents()
        return
    
    if args.list:
        print("Agents in Azure AI Foundry:")
        agents = await list_foundry_agents()
        for agent in agents:
            print(f"  - {agent['name']} (ID: {agent['id']}, Model: {agent['model']})")
        return
    
    if args.create or args.recreate:
        await create_foundry_agents(delete_existing=args.recreate)
        if not args.run and not args.declarative:
            return
    
    # Sample declaration for testing
    declaration = {
        "declaration_id": "DEMO-001",
        "shipper": {
            "name": "Shenzhen Electronics Co., Ltd.",
            "address": "123 Factory Road, Shenzhen",
            "country": "CN"
        },
        "consignee": {
            "name": "UK Import Ltd.",
            "address": "45 Commerce Street, London",
            "country": "GB"
        },
        "goods": [
            {
                "description": "LED Computer Monitors, 27 inch, 4K resolution",
                "hs_code": "852852",
                "quantity": 50,
                "unit_value": 300.00,
                "total_value": 15000.00,
                "currency": "USD",
                "country_of_origin": "CN"
            }
        ],
        "country_of_dispatch": "CN",
        "destination_country": "GB",
        "port_of_entry": "Felixstowe",
        "total_value": 15000.00,
        "currency": "USD",
        "transport_mode": "Sea",
    }
    
    if args.declarative:
        # Run using declarative YAML workflow
        print("=" * 70)
        print("Customs Compliance Workflow (DECLARATIVE MODE)")
        print("=" * 70)
        print()
        print("Using YAML-defined workflow from: foundry-workflow.yaml")
        print("This workflow uses InvokeAzureAgent actions to call Foundry agents.")
        print()
        
        print("Analyzing declaration...")
        print(json.dumps(declaration, indent=2))
        print()
        
        result = await run_declarative_workflow(declaration, trace=args.trace)
        
        print()
        print("=" * 70)
        print("WORKFLOW OUTPUT")
        print("=" * 70)
        print(json.dumps(result, indent=2, default=str))
        return
    
    if args.run or (not args.create and not args.cleanup and not args.list and not args.declarative):
        print("=" * 70)
        print("Customs Compliance Workflow (Azure AI Foundry Agents)")
        print("=" * 70)
        print()
        print("WORKFLOW ARCHITECTURE:")
        print("  This workflow uses a fan-out/fan-in pattern for concurrent execution:")
        print()
        print("      ┌─────────────┐")
        print("      │  Dispatcher │")
        print("      └──────┬──────┘")
        print("             │ fan-out")
        print("  ┌──────────┼──────────┬──────────┬──────────┐")
        print("  ▼          ▼          ▼          ▼          ▼")
        print(" Doc       HS Code    Country    Shipper    Value")
        print(" Consist   Validate   Restrict   Verify     Check")
        print("  │          │          │          │          │")
        print("  └──────────┴──────────┴──────────┴──────────┘")
        print("             │ fan-in")
        print("      ┌──────┴──────┐")
        print("      │  Aggregator │ → ComplianceReport")
        print("      └─────────────┘")
        print()
        print("AGENTS: Created in Azure AI Foundry (visible in portal)")
        if args.trace:
            print("TRACING: Enabled - view in VS Code AI Toolkit → Tracing")
        print()
        
        print("Analyzing declaration...")
        print(json.dumps(declaration, indent=2))
        print()
        
        report = await run_compliance_check(declaration)
        
        print()
        print("=" * 70)
        print("COMPLIANCE REPORT")
        print("=" * 70)
        print(f"Declaration ID: {report.declaration_id}")
        print(f"Timestamp: {report.timestamp}")
        print(f"Overall Risk: {report.overall_risk.upper()}")
        print(f"Requires Manual Review: {report.requires_manual_review}")
        print(f"Processing Time: {report.processing_time_ms}ms")
        print()
        print("Findings Summary:")
        print(f"  Critical: {report.critical_count}")
        print(f"  High: {report.high_count}")
        print(f"  Medium: {report.medium_count}")
        print(f"  Low: {report.low_count}")
        print(f"  Info: {report.info_count}")
        
        if report.recommendations:
            print()
            print("Recommendations:")
            for i, rec in enumerate(report.recommendations, 1):
                print(f"  {i}. {rec}")
        
        print()
        for agent_result in report.agent_results:
            print(f"--- {agent_result.agent_name} ---")
            if agent_result.error:
                print(f"  ERROR: {agent_result.error}")
            else:
                for finding in agent_result.findings:
                    severity = finding.severity.value if hasattr(finding.severity, 'value') else str(finding.severity)
                    print(f"  [{severity.upper()}] {finding.code}: {finding.title}")
        
        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
