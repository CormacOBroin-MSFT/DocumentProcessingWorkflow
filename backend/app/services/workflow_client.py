"""
Azure AI Foundry Workflow Client
Orchestrates the customs compliance workflow by calling Foundry agents

Uses agent_framework with AzureAIProjectAgentProvider to call persistent agents
created in Azure AI Foundry.
"""
import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger('autonomousflow.workflow_client')

# Configuration from environment
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
AZURE_AI_MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-41")


def setup_tracing():
    """Configure OpenTelemetry tracing for workflow visualization."""
    try:
        from agent_framework.observability import configure_otel_providers
        
        configure_otel_providers(
            vs_code_extension_port=4317,  # AI Toolkit gRPC port
            enable_sensitive_data=True,   # Capture prompts and completions
        )
        logger.info("OpenTelemetry tracing enabled (AI Toolkit port 4317)")
        return True
    except ImportError as e:
        logger.warning(f"agent_framework tracing not available: {e}")
        return False
    except Exception as e:
        logger.warning(f"Could not enable tracing: {e}")
        return False


class WorkflowClient:
    """Client for executing Azure AI Foundry agent workflows using agent_framework"""
    
    def __init__(self, enable_tracing: bool = True):
        if not AZURE_AI_PROJECT_ENDPOINT:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT environment variable required")
        
        self.endpoint = AZURE_AI_PROJECT_ENDPOINT
        self._tracing_enabled = False
        
        if enable_tracing:
            self._tracing_enabled = setup_tracing()
        
        # Agent IDs file
        self.agent_ids_file = Path(__file__).parent.parent.parent.parent / "agents" / ".foundry_agent_ids.json"
    
    async def run_compliance_workflow(self, declaration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the customs compliance workflow by calling Foundry agents.
        
        Uses agent_framework.azure.AzureAIProjectAgentProvider to get agents
        from Foundry by name, then runs them concurrently.
        
        Fan-out pattern: 7 specialist agents run concurrently
        Fan-in pattern: Aggregator combines all results
        
        Args:
            declaration_data: The customs declaration to analyze
            
        Returns:
            ComplianceReport JSON from the aggregator agent
        """
        from azure.identity.aio import AzureCliCredential
        from azure.ai.projects.aio import AIProjectClient
        from agent_framework.azure import AzureAIProjectAgentProvider
        
        logger.info("=" * 60)
        logger.info("🚀 STARTING COMPLIANCE WORKFLOW (Azure AI Foundry Agents)")
        logger.info(f"   Declaration ID: {declaration_data.get('declaration_id', 'N/A')}")
        logger.info(f"   Endpoint: {self.endpoint}")
        logger.info("=" * 60)
        
        # Specialist agents (will run in parallel)
        specialist_agents = [
            "DocumentConsistencyAgent",
            "HSCodeValidationAgent",
            "CountryRestrictionsAgent",
            "CountryOfOriginAgent",
            "ControlledGoodsAgent",
            "ValueReasonablenessAgent",
            "ShipperVerificationAgent",
        ]
        
        # Format input for agents
        input_message = json.dumps(declaration_data, indent=2)
        
        async with AzureCliCredential() as credential:
            async with AIProjectClient(
                endpoint=self.endpoint,
                credential=credential,
            ) as project_client:
                
                # Create provider for getting agents from Foundry
                provider = AzureAIProjectAgentProvider(project_client=project_client)
                
                # Phase 1: Fan-out - Call all specialist agents concurrently
                logger.info("\n📤 PHASE 1: FAN-OUT (7 specialist agents)")
                
                tasks = []
                for agent_name in specialist_agents:
                    task = self._call_agent_via_provider(
                        provider,
                        agent_name,
                        input_message,
                    )
                    tasks.append(task)
                
                # Execute all agents concurrently
                agent_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Collect outputs
                specialist_outputs = {}
                for agent_name, result in zip(specialist_agents, agent_results):
                    if isinstance(result, Exception):
                        logger.error(f"   ❌ {agent_name}: {result}")
                        specialist_outputs[agent_name] = {"error": str(result)}
                    else:
                        logger.info(f"   ✅ {agent_name}: Response received")
                        specialist_outputs[agent_name] = result
                
                # Phase 2: Fan-in - Build handoff packet and call aggregator
                logger.info("\n📥 PHASE 2: FAN-IN (aggregator)")
                
                # Build handoff packet with all specialist outputs
                handoff_packet = "# Customs Declaration\n"
                handoff_packet += input_message + "\n\n"
                handoff_packet += "# Agent Analysis Results\n\n"
                
                for agent_name, output in specialist_outputs.items():
                    handoff_packet += f"## {agent_name}\n"
                    if isinstance(output, dict):
                        handoff_packet += json.dumps(output, indent=2)
                    else:
                        handoff_packet += str(output)
                    handoff_packet += "\n\n"
                
                # Call aggregator
                aggregator_name = "ComplianceAggregatorAgent"
                try:
                    final_result = await self._call_agent_via_provider(
                        provider,
                        aggregator_name,
                        handoff_packet,
                    )
                    logger.info(f"   ✅ {aggregator_name}: Aggregation complete")
                except Exception as e:
                    logger.error(f"   ❌ Aggregator failed: {e}")
                    final_result = self._create_fallback_report(specialist_outputs)
                
                logger.info("\n" + "=" * 60)
                logger.info("✅ WORKFLOW COMPLETE")
                logger.info("=" * 60)
                
                return final_result
    
    async def _call_agent_via_provider(
        self,
        provider,
        agent_name: str,
        message: str,
    ) -> Dict[str, Any]:
        """Call a Foundry agent using AzureAIProjectAgentProvider"""
        
        logger.debug(f"Getting agent: {agent_name}")
        
        try:
            # Get the agent from Foundry by name
            agent = await provider.get_agent(name=agent_name)
            
            logger.debug(f"Running agent: {agent_name}")
            
            # Run the agent with the message
            result = await agent.run(message)
            
            # Extract response text
            if hasattr(result, 'text'):
                response_text = result.text
            elif hasattr(result, 'value'):
                response_text = result.value
            else:
                response_text = str(result)
            
            logger.debug(f"Agent {agent_name} response: {response_text[:200]}...")
            
            return self._parse_json_response(response_text)
            
        except Exception as e:
            logger.error(f"Error calling agent {agent_name}: {e}")
            raise
    
    def _parse_json_response(self, response: str) -> Dict:
        """Extract and parse JSON from agent response"""
        if not response:
            return {}
        
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON in the response (between ```json and ```)
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Return as raw text wrapped in dict
        return {"raw_response": response}
    
    def _create_fallback_report(self, specialist_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a basic compliance report if aggregator fails"""
        findings = []
        for agent_name, output in specialist_outputs.items():
            if isinstance(output, dict):
                if "findings" in output:
                    findings.extend(output["findings"])
                elif "error" in output:
                    findings.append({
                        "source_agent": agent_name,
                        "severity": "high",
                        "code": "AGENT_ERROR",
                        "title": f"{agent_name} Error",
                        "description": output["error"]
                    })
        
        return {
            "overall_risk": "medium",
            "summary": "Compliance analysis completed (aggregator unavailable)",
            "findings": findings,
            "agents_reporting": {
                name: "error" if isinstance(out, dict) and "error" in out else "success"
                for name, out in specialist_outputs.items()
            },
            "requires_manual_review": True,
            "recommendations": ["Manual review recommended - aggregation incomplete"]
        }


# Singleton instance
_workflow_client: Optional[WorkflowClient] = None


def get_workflow_client() -> Optional[WorkflowClient]:
    """Get or create workflow client instance"""
    global _workflow_client
    if _workflow_client is None:
        try:
            _workflow_client = WorkflowClient(enable_tracing=True)
            logger.info("✓ Workflow client initialized")
        except Exception as e:
            logger.error(f"Could not initialize workflow client: {e}")
            raise  # Don't return None, raise the error
    return _workflow_client


def run_compliance_workflow_sync(declaration_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronous wrapper for running the compliance workflow.
    Use this from Flask routes.
    """
    client = get_workflow_client()
    if not client:
        raise RuntimeError("Workflow client not available")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(client.run_compliance_workflow(declaration_data))
    finally:
        loop.close()
