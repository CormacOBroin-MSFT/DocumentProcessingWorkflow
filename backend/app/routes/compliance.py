"""
Compliance Validation Routes
Handles LLM-based compliance checking
"""
from flask import Blueprint, request, jsonify
from app.services.llm_client import get_llm_service
from app.config import config

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
    if not config.is_openai_configured():
        return jsonify({
            'error': 'OpenAI not configured',
            'mock_mode': True
        }), 503
    
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
            return jsonify({'error': 'Could not initialize LLM service'}), 500
        
        result = llm_service.perform_compliance_check(structured_data)
        
        return jsonify({
            'document_id': document_id,
            'checks': result['checks'],
            'compliance_confidence': result['compliance_confidence'],
            'issues': result['issues'],
            'reasoning': result.get('reasoning'),
            'status': 'validated'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
