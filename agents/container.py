"""
Container Entry Point for Hosted Agent Deployment

This module provides the entry point for deploying the compliance workflow
as a hosted agent on Microsoft Foundry.

Usage:
    python container.py
"""

import asyncio
import os
import sys
from typing import Any

from agent_framework import ChatMessage, Role
from agent_framework.azure import AzureAIClient
from agent_framework.observability import setup_observability
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from workflow import (
    create_compliance_workflow,
    Declaration,
    ComplianceReport,
    run_compliance_check,
)
from tools import initialize_services

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

# Configuration
ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
MODEL_DEPLOYMENT = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-41")

# Setup observability
setup_observability(vs_code_extension_port=4319)


async def run_container_agent():
    """
    Run the compliance workflow as a container agent.
    
    This is the entry point for hosted deployment on Microsoft Foundry.
    """
    print("=" * 70)
    print("Customs Compliance Agent (Container Mode)")
    print("=" * 70)
    print(f"Endpoint: {ENDPOINT}")
    print(f"Model: {MODEL_DEPLOYMENT}")
    print()
    
    # Initialize services
    from app.services.hs_code_reference import HSCodeReferenceService
    from app.services.sanctions_reference import SanctionsReferenceService
    
    hs_service = HSCodeReferenceService()
    sanctions_service = SanctionsReferenceService()
    initialize_services(hs_service, sanctions_service)
    
    # Create the Azure AI client
    async with DefaultAzureCredential() as credential:
        async with AzureAIClient(
            project_endpoint=ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT,
            credential=credential,
        ) as ai_client:
            # Create the workflow as an agent
            from agent_framework.azure import AzureOpenAIChatClient
            chat_client = AzureOpenAIChatClient(credential=credential)
            
            workflow = create_compliance_workflow(chat_client)
            
            # Expose workflow as an agent
            workflow_agent = workflow.as_agent(
                name="CustomsComplianceAgent",
                description="Comprehensive customs compliance analysis for declarations",
            )
            
            print("Agent ready. Waiting for requests...")
            print()
            
            # In container mode, the agent handles incoming requests
            # This is managed by the Foundry hosting infrastructure
            # For local testing, we can run an interactive loop
            
            while True:
                try:
                    user_input = input("\nEnter declaration JSON (or 'quit' to exit): ").strip()
                    
                    if user_input.lower() in ['quit', 'exit', 'q']:
                        break
                    
                    if not user_input:
                        continue
                    
                    # Parse declaration
                    import json
                    declaration_data = json.loads(user_input)
                    
                    # Run compliance check
                    report = await run_compliance_check(declaration_data)
                    
                    # Output report
                    print("\n" + "=" * 50)
                    print(f"Risk Level: {report.overall_risk.upper()}")
                    print(f"Findings: {report.total_findings}")
                    print(f"Manual Review Required: {report.requires_manual_review}")
                    print("=" * 50)
                    
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")
    
    print("\nAgent shutdown complete.")


if __name__ == "__main__":
    asyncio.run(run_container_agent())
