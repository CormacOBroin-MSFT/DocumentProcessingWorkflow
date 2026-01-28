"""
Compliance Validation Routes
Handles compliance checking using Azure AI Foundry Workflow
"""
import logging
from flask import Blueprint, request, jsonify
from app.services.workflow_client import run_compliance_workflow_sync
from app.config import config

logger = logging.getLogger('autonomousflow.compliance')

bp = Blueprint('compliance', __name__, url_prefix='/api/compliance')

@bp.route('/validate', methods=['POST'])
def validate_compliance():
    """
    Validate customs declaration against compliance requirements using Azure AI Foundry Workflow.
    
    This endpoint uses the multi-agent workflow with 7 specialist agents + aggregator:
    - DocumentConsistencyAgent
    - HSCodeValidationAgent
    - CountryRestrictionsAgent
    - CountryOfOriginAgent
    - ControlledGoodsAgent
    - ValueReasonablenessAgent
    - ShipperVerificationAgent
    - ComplianceAggregatorAgent
    
    Expects JSON body:
    {
        "document_id": "uuid",
        "structured_data": {
            "shipper": "...",
            "receiver": "...",
            ...
        }
    }
    
    Returns:
        ComplianceReport JSON with findings, risk level, and recommendations
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    structured_data = data.get('structured_data')
    document_id = data.get('document_id')
    
    if not structured_data:
        return jsonify({'error': 'structured_data required'}), 400
    
    try:
        logger.info("=" * 60)
        logger.info("✓ STAGE 4: COMPLIANCE VALIDATION (Azure AI Foundry Workflow)")
        logger.info("=" * 60)
        
        # Add document_id to structured data for workflow
        structured_data['declaration_id'] = document_id
        
        # Run the workflow - NO FALLBACK
        report = run_compliance_workflow_sync(structured_data)
        
        # Map workflow output to expected response format
        checks = _map_findings_to_checks(report)
        
        logger.info(f"✅ Workflow complete: {report.get('overall_risk', 'UNKNOWN').upper()} risk")
        logger.info(f"   Findings: {report.get('counts', {}).get('total', 0)}")
        logger.info("=" * 60)
        
        return jsonify({
            'document_id': document_id,
            'checks': checks,
            'compliance_confidence': _calculate_confidence(report),
            'issues': _extract_issues(report),
            'issue_descriptions': _extract_issue_descriptions(report),
            'reasoning': report.get('summary', 'Compliance analysis completed'),
            'risk_level': report.get('overall_risk', 'medium').upper(),
            'requires_manual_review': report.get('requires_manual_review', False),
            'findings': report.get('findings', []),
            'recommendations': report.get('recommendations', []),
            'agents_reporting': report.get('agents_reporting', {}),
            'status': 'validated'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _map_findings_to_checks(report: dict) -> list:
    """Map workflow findings to the 5 boolean checks expected by frontend"""
    # Check names: HS Code, Country, Value, Shipper, Completeness
    checks = [True, True, True, True, True]
    
    findings = report.get('findings', [])
    agents_reporting = report.get('agents_reporting', {})
    
    # Map agent results to check indices
    agent_to_check = {
        'HSCodeValidationAgent': 0,
        'CountryRestrictionsAgent': 1,
        'CountryOfOriginAgent': 1,  # Also affects country check
        'ValueReasonablenessAgent': 2,
        'ShipperVerificationAgent': 3,
        'DocumentConsistencyAgent': 4,
    }
    
    # Check for high/critical findings by agent
    for finding in findings:
        source = finding.get('source_agent', '')
        severity = finding.get('severity', 'info')
        
        if severity in ['high', 'critical']:
            check_idx = agent_to_check.get(source)
            if check_idx is not None:
                checks[check_idx] = False
    
    # Also check agent statuses
    for agent_name, status in agents_reporting.items():
        if status == 'error':
            check_idx = agent_to_check.get(agent_name)
            if check_idx is not None:
                checks[check_idx] = False
    
    return checks


def _calculate_confidence(report: dict) -> float:
    """Calculate overall confidence from workflow report"""
    overall_risk = report.get('overall_risk', 'medium')
    
    # Map risk to confidence
    risk_confidence = {
        'clear': 0.95,
        'low': 0.85,
        'medium': 0.70,
        'high': 0.50,
        'critical': 0.30,
    }
    
    return risk_confidence.get(overall_risk, 0.70)


def _extract_issues(report: dict) -> list:
    """Extract issue names from findings"""
    issues = []
    findings = report.get('findings', [])
    
    for finding in findings:
        severity = finding.get('severity', 'info')
        if severity in ['medium', 'high', 'critical']:
            issues.append(finding.get('title', finding.get('code', 'Unknown Issue')))
    
    return issues


def _extract_issue_descriptions(report: dict) -> list:
    """Extract issue descriptions from findings"""
    descriptions = []
    findings = report.get('findings', [])
    
    for finding in findings:
        severity = finding.get('severity', 'info')
        if severity in ['medium', 'high', 'critical']:
            descriptions.append(finding.get('description', finding.get('title', '')))
    
    return descriptions
