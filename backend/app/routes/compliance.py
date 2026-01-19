"""
Compliance Validation Routes
Handles LLM-based compliance checking
"""
import logging
from flask import Blueprint, request, jsonify
from app.services.llm_client import get_llm_service
from app.config import config

logger = logging.getLogger('autonomousflow.compliance')

bp = Blueprint('compliance', __name__, url_prefix='/api/compliance')

@bp.route('/validate', methods=['POST'])
def validate_compliance():
    """
    Validate customs declaration against compliance requirements
    
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
        JSON with checks (array of booleans), compliance_confidence, and issues
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    structured_data = data.get('structured_data')
    document_id = data.get('document_id')
    
    if not structured_data:
        return jsonify({'error': 'structured_data required'}), 400
    
    try:
        llm_service = get_llm_service()
        
        if not llm_service:
            logger.error("Could not initialize LLM service")
            return jsonify({'error': 'Could not initialize LLM service'}), 500
        
        logger.info("=" * 60)
        logger.info("✓ STAGE 4: COMPLIANCE VALIDATION")
        logger.info("=" * 60)
        
        result = llm_service.perform_compliance_check(structured_data)
        
        passed = sum(result['checks'])
        total = len(result['checks'])
        check_names = ['HS Code', 'Country', 'Value', 'Shipper', 'Completeness']
        
        logger.info(f"✅ {passed}/{total} checks passed (confidence: {result['compliance_confidence']:.0%})")
        for i, (name, check) in enumerate(zip(check_names, result['checks'])):
            status = "✓" if check else "✗"
            logger.info(f"   {status} {name}")
        logger.info("=" * 60)
        
        return jsonify({
            'document_id': document_id,
            'checks': result['checks'],
            'compliance_confidence': result['compliance_confidence'],
            'issues': result['issues'],
            'issue_descriptions': result.get('issue_descriptions', []),
            'reasoning': result.get('reasoning'),
            'status': 'validated'
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Compliance check failed: {e}")
        return jsonify({'error': str(e)}), 500
