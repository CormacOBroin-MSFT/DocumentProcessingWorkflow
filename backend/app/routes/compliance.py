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
        confidence = _calculate_confidence(report, checks)
        
        # Flag for manual review if confidence < 85%
        requires_manual_review = confidence < 0.85 or report.get('requires_manual_review', False)
        
        # Add guidance for manual review cases
        recommendations = report.get('recommendations', [])
        if requires_manual_review and confidence < 0.85:
            recommendations = [
                f"⚠️ Compliance confidence ({confidence*100:.0f}%) is below 85% threshold - manual review required.",
                *recommendations
            ]
        
        logger.info(f"✅ Workflow complete: {report.get('overall_risk', 'UNKNOWN').upper()} risk")
        logger.info(f"   Findings: {report.get('counts', {}).get('total', 0)}")
        logger.info(f"   Checks passed: {sum(checks)}/5")
        logger.info(f"   Confidence: {confidence*100:.0f}%")
        logger.info(f"   Manual review: {'YES' if requires_manual_review else 'NO'}")
        logger.info("=" * 60)

        return jsonify({
            'document_id': document_id,
            'checks': checks,
            'compliance_confidence': confidence,
            'issues': _extract_issues(report),
            'issue_descriptions': _extract_issue_descriptions(report),
            'reasoning': report.get('summary', 'Compliance analysis completed'),
            'risk_level': report.get('overall_risk', 'medium').upper(),
            'requires_manual_review': requires_manual_review,
            'findings': report.get('findings', []),
            'recommendations': recommendations,
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


def _calculate_confidence(report: dict, checks: list = None) -> float:
    """Calculate overall confidence from workflow report.
    
    If all checks pass, give high confidence regardless of risk level.
    Otherwise, base confidence on the severity of findings.
    """
    # If checks provided and all pass, return high confidence
    if checks and all(checks):
        return 0.95
    
    # Count findings by severity
    findings = report.get('findings', [])
    counts = report.get('counts', {})
    
    critical = counts.get('critical', 0)
    high = counts.get('high', 0)
    medium = counts.get('medium', 0)
    low = counts.get('low', 0)
    
    # Calculate confidence based on finding severity
    # Start at 100% and deduct based on severity
    confidence = 1.0
    confidence -= critical * 0.20  # Each critical finding deducts 20%
    confidence -= high * 0.10      # Each high finding deducts 10%
    confidence -= medium * 0.05   # Each medium finding deducts 5%
    confidence -= low * 0.02      # Each low finding deducts 2%
    
    # Ensure confidence is in valid range
    return max(0.30, min(0.98, confidence))


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
