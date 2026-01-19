"""
Data Transformation Routes
Handles LLM-based transformation of raw OCR data to structured format
"""
from flask import Blueprint, request, jsonify
from app.services.llm_client import get_llm_service
from app.config import config

bp = Blueprint('transform', __name__, url_prefix='/api/transform')

@bp.route('/structure', methods=['POST'])
def transform_data():
    """
    Transform raw OCR data into structured customs declaration
    
    Expects JSON body:
    {
        "document_id": "uuid",
        "raw_data": {
            "FIELD_NAME": {"value": "...", "confidence": 0.95},
            ...
        }
    }
    
    Returns:
        JSON with structured_data and structure_confidence
    """
    if not config.is_openai_configured():
        return jsonify({
            'error': 'OpenAI not configured',
            'mock_mode': True
        }), 503
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    raw_data = data.get('raw_data')
    document_id = data.get('document_id')
    
    if not raw_data:
        return jsonify({'error': 'raw_data required'}), 400
    
    try:
        llm_service = get_llm_service()
        
        if not llm_service:
            return jsonify({'error': 'Could not initialize LLM service'}), 500
        
        result = llm_service.transform_to_structured_data(raw_data)
        
        return jsonify({
            'document_id': document_id,
            'structured_data': result['structured_data'],
            'structure_confidence': result['structure_confidence'],
            'status': 'transformed'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
