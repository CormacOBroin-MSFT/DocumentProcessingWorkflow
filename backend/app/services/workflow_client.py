"""
Azure AI Foundry Workflow Client
Invokes the customs compliance workflow deployed in Azure AI Foundry.

This uses the OpenAI-compatible conversations API to call the workflow as
a single API call. Foundry handles the sequential orchestration of all
8 agents server-side — no fan-out, no individual agent calls from this client.

Always uses the latest deployed version of the workflow and agents.

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

# Workflow configuration — always uses latest version
WORKFLOW_NAME = "customs-compliance-workflow"


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
    
    Makes a single API call to the Foundry workflow endpoint.
    Foundry runs all agents sequentially server-side:
    7 specialist agents → 1 aggregator → ComplianceReport JSON.
    
    Always uses the latest version of the workflow and agents.
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
        logger.info("🚀 INVOKING FOUNDRY WORKFLOW: %s (latest)", WORKFLOW_NAME)
        logger.info("   Declaration ID: %s", declaration_data.get('declaration_id', 'N/A'))
        logger.info("   Endpoint: %s", self.endpoint)
        logger.info("=" * 60)
        
        # Separate OCR extraction context from declaration fields
        ocr_extraction = declaration_data.pop('ocr_extraction', None)
        
        # Format input message with full context
        message_parts = [
            "Analyze this customs declaration for compliance:",
            "",
            "## Declaration Fields",
            "```json",
            json.dumps(declaration_data, indent=2),
            "```",
        ]
        
        if ocr_extraction:
            message_parts.extend([
                "",
                "## Full OCR Extraction Context",
                "The fields above were extracted from the source document by Azure AI Content Understanding.",
                "Below is the complete extraction result including per-field confidence scores and raw document key-value pairs.",
                "Use this context for richer analysis — low-confidence fields may warrant closer scrutiny.",
                "```json",
                json.dumps(ocr_extraction, indent=2),
                "```",
            ])
        
        message_parts.append("")
        message_parts.append("Run all compliance checks and return a ComplianceReport JSON.")
        
        input_message = "\n".join(message_parts)
        
        credential = DefaultAzureCredential()
        project_client = AIProjectClient(
            endpoint=self.endpoint,
            credential=credential,
        )
        
        workflow_config = {
            "name": WORKFLOW_NAME,
        }
        
        final_response = ""
        workflow_actions = []
        conversation = None
        
        # Retry logic with new conversation on each attempt
        max_retries = 2
        last_error = None
        
        with project_client:
            openai_client = project_client.get_openai_client()
            
            for attempt in range(max_retries + 1):
                conversation = None
                try:
                    # Create a NEW conversation for each attempt
                    conversation = openai_client.conversations.create()
                    logger.info("📝 Created conversation: %s (attempt %d/%d)", 
                               conversation.id, attempt + 1, max_retries + 1)
                    
                    # Reset accumulators for this attempt
                    final_response = ""
                    workflow_actions = []
                    
                    # Invoke workflow with streaming
                    logger.info("\n📤 Invoking workflow...")
                    stream = openai_client.responses.create(
                        conversation=conversation.id,
                        extra_body={
                            "agent": {
                                "name": workflow_config["name"],
                                "type": "agent_reference",
                                "version": "18"
                            }
                        },
                        input=input_message,
                        stream=True,
                        metadata={"x-ms-debug-mode-enabled": "1"},
                        timeout=180.0,  # 3 minute timeout
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
                    
                    # Success - break out of retry loop
                    last_error = None
                    break
                    
                except Exception as e:
                    last_error = e
                    logger.warning("⚠️ Attempt %d failed: %s", attempt + 1, str(e)[:100])
                    
                    # Don't retry on 400 errors (bad request)
                    if "400" in str(e) or "bad_request" in str(e).lower():
                        logger.error("❌ Bad request error - not retrying")
                        break
                    
                    if attempt < max_retries:
                        import time
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s
                        logger.info("   Retrying in %ds...", wait_time)
                        time.sleep(wait_time)
                        
                finally:
                    # Clean up conversation for this attempt
                    if conversation:
                        try:
                            openai_client.conversations.delete(conversation_id=conversation.id)
                            logger.debug("Conversation deleted")
                        except Exception as e:
                            logger.debug("Could not delete conversation: %s", e)
            
            # After retry loop - check if we succeeded
            if last_error:
                raise last_error
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ WORKFLOW COMPLETE")
        logger.info("   Actions executed: %d", len(workflow_actions))
        logger.info("=" * 60)
        
        # Parse the response
        result = self._parse_json_response(final_response)
        if isinstance(result, list):
            result = {
                "summary": "Workflow returned a list of findings",
                "overall_risk": "medium",
                "findings": result,
                "counts": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "total": len(result),
                },
                "agents_reporting": {},
                "recommendations": [],
            }
        elif not isinstance(result, dict):
            result = {"raw_response": str(result)}
        
        # Add workflow metadata
        result["_workflow_metadata"] = {
            "workflow_name": WORKFLOW_NAME,
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
