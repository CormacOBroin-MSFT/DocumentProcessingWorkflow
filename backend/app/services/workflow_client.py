"""
Azure AI Foundry Workflow Client
Invokes the customs compliance workflow deployed in Azure AI Foundry.

This uses the OpenAI-compatible client to call the workflow directly,
letting Foundry handle the orchestration of all agents server-side.

TRACING: OpenTelemetry tracing is configured in run.py at application startup.
"""
import os
import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger('autonomousflow.workflow_client')

# Configuration from environment
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")

# Workflow configuration
WORKFLOW_NAME = "customs-compliance-workflow"
WORKFLOW_VERSION = "2"


def is_tracing_enabled() -> bool:
    """Check if OpenTelemetry tracing is configured."""
    try:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        return provider is not None and type(provider).__name__ != 'NoOpTracerProvider'
    except ImportError:
        return False


class WorkflowClient:
    """
    Client for executing Azure AI Foundry workflows.
    
    Uses the OpenAI-compatible client to invoke workflows directly,
    allowing Foundry to orchestrate the agent execution server-side.
    """
    
    def __init__(self):
        if not AZURE_AI_PROJECT_ENDPOINT:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT environment variable required")
        
        self.endpoint = AZURE_AI_PROJECT_ENDPOINT
        self._tracing_enabled = is_tracing_enabled()
        
        if self._tracing_enabled:
            logger.info("✓ Tracing enabled - spans will appear in AI Toolkit")
    
    def run_compliance_workflow(self, declaration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the customs compliance workflow via Azure AI Foundry.
        
        The workflow is executed server-side in Foundry, which handles:
        - Fan-out to specialist agents
        - Agent tool invocations (Azure AI Search, etc.)
        - Fan-in aggregation
        - Response streaming
        
        Args:
            declaration_data: The customs declaration to analyze
            
        Returns:
            ComplianceReport JSON from the workflow
        """
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import ResponseStreamEventType
        
        logger.info("=" * 60)
        logger.info("🚀 INVOKING FOUNDRY WORKFLOW: %s (v%s)", WORKFLOW_NAME, WORKFLOW_VERSION)
        logger.info("   Declaration ID: %s", declaration_data.get('declaration_id', 'N/A'))
        logger.info("   Endpoint: %s", self.endpoint)
        logger.info("=" * 60)
        
        # Format input message
        input_message = f"""Analyze this customs declaration for compliance:

```json
{json.dumps(declaration_data, indent=2)}
```

Run all compliance checks and return a ComplianceReport JSON."""
        
        credential = DefaultAzureCredential()
        project_client = AIProjectClient(
            endpoint=self.endpoint,
            credential=credential,
        )
        
        workflow_config = {
            "name": WORKFLOW_NAME,
            "version": WORKFLOW_VERSION,
        }
        
        final_response = ""
        workflow_actions = []
        
        with project_client:
            openai_client = project_client.get_openai_client()
            
            # Create conversation
            conversation = openai_client.conversations.create()
            logger.info("📝 Created conversation: %s", conversation.id)
            
            try:
                # Invoke workflow with streaming
                logger.info("\n📤 Invoking workflow...")
                stream = openai_client.responses.create(
                    conversation=conversation.id,
                    extra_body={
                        "agent": {
                            "name": workflow_config["name"],
                            "type": "agent_reference"
                        }
                    },
                    input=input_message,
                    stream=True,
                    metadata={"x-ms-debug-mode-enabled": "1"},
                )
                
                current_action = None
                
                for event in stream:
                    if event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DELTA:
                        # Accumulate response text
                        final_response += event.delta
                        
                    elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DONE:
                        logger.debug("Response text complete")
                        
                    elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED:
                        if hasattr(event, 'item') and event.item.type == "workflow_action":
                            action_id = getattr(event.item, 'action_id', 'unknown')
                            status = getattr(event.item, 'status', 'unknown')
                            logger.info("   🔄 Action started: %s", action_id)
                            current_action = action_id
                            workflow_actions.append({
                                "action_id": action_id,
                                "status": "started"
                            })
                            
                    elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_DONE:
                        if hasattr(event, 'item') and event.item.type == "workflow_action":
                            action_id = getattr(event.item, 'action_id', 'unknown')
                            status = getattr(event.item, 'status', 'completed')
                            prev_action = getattr(event.item, 'previous_action_id', None)
                            logger.info("   ✅ Action complete: %s (status: %s)", action_id, status)
                            # Update action in list
                            for action in workflow_actions:
                                if action["action_id"] == action_id:
                                    action["status"] = status
                                    action["previous_action_id"] = prev_action
                                    
                    elif event.type == ResponseStreamEventType.RESPONSE_COMPLETED:
                        logger.info("📥 Workflow response complete")
                        
                    else:
                        # Log other event types for debugging
                        logger.debug("Event: %s", event.type)
                
            finally:
                # Clean up conversation
                try:
                    openai_client.conversations.delete(conversation_id=conversation.id)
                    logger.debug("Conversation deleted")
                except Exception as e:
                    logger.warning("Could not delete conversation: %s", e)
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ WORKFLOW COMPLETE")
        logger.info("   Actions executed: %d", len(workflow_actions))
        logger.info("=" * 60)
        
        # Parse the response
        result = self._parse_json_response(final_response)
        
        # Add workflow metadata
        result["_workflow_metadata"] = {
            "workflow_name": WORKFLOW_NAME,
            "workflow_version": WORKFLOW_VERSION,
            "actions_executed": workflow_actions,
        }
        
        return result
    
    def _parse_json_response(self, response: str) -> Dict:
        """Extract and parse JSON from workflow response"""
        if not response:
            return {"error": "Empty response from workflow"}
        
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON in markdown code block
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
        
        # Return raw response
        return {"raw_response": response}


# Singleton instance
_workflow_client: Optional[WorkflowClient] = None


def get_workflow_client() -> WorkflowClient:
    """Get or create workflow client instance"""
    global _workflow_client
    if _workflow_client is None:
        _workflow_client = WorkflowClient()
        logger.info("✓ Workflow client initialized")
    return _workflow_client


def run_compliance_workflow_sync(declaration_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronous function to run the compliance workflow.
    Use this from Flask routes.
    """
    client = get_workflow_client()
    return client.run_compliance_workflow(declaration_data)
