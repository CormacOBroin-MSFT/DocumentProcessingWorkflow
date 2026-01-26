"""
Agent Workflow Routes

This module provides Flask routes for the Microsoft Agent Framework-based
compliance workflow using PERSISTENT agents in Azure AI Foundry.

Routes:
    POST /api/agents/compliance - Run full compliance analysis
    POST /api/agents/create - Create agents in Azure AI Foundry
    DELETE /api/agents/cleanup - Delete agents from Azure AI Foundry
    GET /api/agents/list - List agents in Azure AI Foundry
    GET /api/agents/status - Check agent workflow status
"""

import asyncio
import logging
import os
import sys
from flask import Blueprint, request, jsonify

# Add agents module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'agents'))

logger = logging.getLogger('autonomousflow.agents')

bp = Blueprint('agents', __name__, url_prefix='/api/agents')

# Service instances (initialized once)
_hs_service = None
_sanctions_service = None
_services_initialized = False


def _run_async(coro):
    """Run an async coroutine in a sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _initialize_services():
    """Initialize reference data services for agents."""
    global _hs_service, _sanctions_service, _services_initialized
    
    if _services_initialized:
        return True
    
    try:
        from app.services.hs_code_reference import HSCodeReferenceService
        from app.services.sanctions_reference import SanctionsReferenceService
        from tools import initialize_services
        
        _hs_service = HSCodeReferenceService()
        _sanctions_service = SanctionsReferenceService()
        initialize_services(_hs_service, _sanctions_service)
        _services_initialized = True
        logger.info("✓ Agent services initialized")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize agent services: {e}")
        return False


@bp.route('/create', methods=['POST'])
def create_agents():
    """
    Create persistent agents in Azure AI Foundry.
    
    Query params:
        recreate: If true, delete existing agents first
    
    Returns:
        Dictionary mapping agent names to their Foundry IDs
    """
    try:
        from workflow import create_foundry_agents
        
        recreate = request.args.get('recreate', 'false').lower() == 'true'
        
        logger.info("=" * 60)
        logger.info("✓ CREATING AGENTS IN AZURE AI FOUNDRY")
        logger.info("=" * 60)
        
        agent_ids = _run_async(create_foundry_agents(delete_existing=recreate))
        
        logger.info(f"✓ Created {len(agent_ids)} agents")
        
        return jsonify({
            'status': 'created',
            'agent_count': len(agent_ids),
            'agents': agent_ids,
            'message': 'Agents are now visible in Azure AI Foundry portal'
        }), 201
    
    except ImportError as e:
        logger.error(f"Agent framework not installed: {e}")
        return jsonify({
            'error': 'Agent framework not installed. Install with: pip install agent-framework-azure-ai --pre',
            'details': str(e)
        }), 500
    
    except Exception as e:
        logger.error(f"❌ Failed to create agents: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/cleanup', methods=['DELETE'])
def cleanup_agents():
    """
    Delete all persistent agents from Azure AI Foundry.
    """
    try:
        from workflow import cleanup_foundry_agents
        
        logger.info("=" * 60)
        logger.info("✓ DELETING AGENTS FROM AZURE AI FOUNDRY")
        logger.info("=" * 60)
        
        _run_async(cleanup_foundry_agents())
        
        return jsonify({
            'status': 'deleted',
            'message': 'All agents have been removed from Azure AI Foundry'
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Failed to cleanup agents: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/list', methods=['GET'])
def list_agents():
    """
    List all agents in the Azure AI Foundry project.
    """
    try:
        from workflow import list_foundry_agents
        
        agents = _run_async(list_foundry_agents())
        
        return jsonify({
            'agents': agents,
            'count': len(agents)
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Failed to list agents: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/compliance', methods=['POST'])
def run_compliance_workflow():
    """
    Run full compliance analysis using persistent Azure AI Foundry agents.
    
    Expects JSON body:
    {
        "declaration_id": "uuid",
        "shipper": {...} or "...",
        "consignee": {...} or "...",
        "goods": [...] or "goods_description": "...",
        "hs_code": "...",
        "declared_value": "...",
        "country_of_origin": "...",
        "destination_country": "...",
        ...
    }
    
    Returns:
        ComplianceReport with all findings from Azure AI Foundry agents
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    # Initialize services if needed
    _initialize_services()
    
    try:
        # Import workflow (lazy import to avoid import errors if agent-framework not installed)
        from workflow import run_compliance_check
        
        logger.info("=" * 60)
        logger.info("✓ AGENT WORKFLOW: COMPLIANCE ANALYSIS (Azure AI Foundry)")
        logger.info("=" * 60)
        logger.info(f"Declaration ID: {data.get('declaration_id', 'N/A')}")
        
        # Run the async workflow
        report = _run_async(run_compliance_check(data))
        
        logger.info(f"✓ Analysis complete: {report.overall_risk.upper()} risk")
        logger.info(f"  Findings: {report.total_findings}")
        logger.info(f"  Manual Review: {report.requires_manual_review}")
        logger.info("=" * 60)
        
        # Convert report to dict for JSON serialization
        return jsonify({
            'declaration_id': report.declaration_id,
            'timestamp': report.timestamp,
            'overall_risk': report.overall_risk,
            'requires_manual_review': report.requires_manual_review,
            'total_findings': report.total_findings,
            'findings_by_severity': {
                'critical': report.critical_count,
                'high': report.high_count,
                'medium': report.medium_count,
                'low': report.low_count,
                'info': report.info_count,
            },
            'agent_results': [
                {
                    'agent_name': ar.agent_name,
                    'findings': [
                        {
                            'code': f.code,
                            'title': f.title,
                            'description': f.description,
                            'severity': f.severity.value if hasattr(f.severity, 'value') else str(f.severity),
                            'confidence': f.confidence.value if hasattr(f.confidence, 'value') else str(f.confidence),
                            'evidence': f.evidence,
                            'metadata': f.metadata,
                        }
                        for f in ar.findings
                    ],
                    'processing_time_ms': ar.processing_time_ms,
                    'error': ar.error,
                }
                for ar in report.agent_results
            ],
            'processing_time_ms': report.processing_time_ms,
            'status': 'completed'
        }), 200
    
    except ImportError as e:
        logger.error(f"Agent framework not installed: {e}")
        return jsonify({
            'error': 'Agent framework not installed. Install with: pip install agent-framework-azure-ai --pre',
            'details': str(e)
        }), 500
    
    except Exception as e:
        logger.error(f"❌ Agent workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/status', methods=['GET'])
def get_agent_status():
    """
    Check agent workflow status and capabilities.
    
    Returns:
        Status of agent services and available agents
    """
    status = {
        'services': {
            'hs_code_service': _hs_service is not None,
            'sanctions_service': _sanctions_service is not None,
            'initialized': _services_initialized,
        },
        'agents': [
            'DocumentConsistencyAgent',
            'HSCodeValidationAgent',
            'CountryRestrictionsAgent',
            'CountryOfOriginAgent',
            'ControlledGoodsAgent',
            'ValueReasonablenessAgent',
            'ShipperVerificationAgent',
        ],
        'workflow_pattern': 'fan-out/fan-in',
        'framework': 'Microsoft Agent Framework (azure-ai-agentserver-agentframework)',
    }
    
    # Check if agent framework is installed
    try:
        import agent_framework
        status['agent_framework_installed'] = True
        status['agent_framework_version'] = getattr(agent_framework, '__version__', 'unknown')
    except ImportError:
        status['agent_framework_installed'] = False
    
    return jsonify(status), 200


@bp.route('/tools', methods=['GET'])
def list_tools():
    """
    List available tools for agents.
    
    Returns:
        List of tools with descriptions
    """
    try:
        from tools import HS_CODE_TOOLS, SANCTIONS_TOOLS
        
        tools = []
        
        for tool in HS_CODE_TOOLS:
            tools.append({
                'name': tool.__name__,
                'category': 'hs_code',
                'description': tool.__doc__.strip().split('\n')[0] if tool.__doc__ else '',
            })
        
        for tool in SANCTIONS_TOOLS:
            tools.append({
                'name': tool.__name__,
                'category': 'sanctions',
                'description': tool.__doc__.strip().split('\n')[0] if tool.__doc__ else '',
            })
        
        return jsonify({
            'tools': tools,
            'total': len(tools)
        }), 200
    
    except ImportError as e:
        return jsonify({'error': f'Could not load tools: {e}'}), 500
