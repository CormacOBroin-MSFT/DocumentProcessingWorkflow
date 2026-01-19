"""
Data Transformation Routes
Handles LLM-based transformation of raw OCR data to structured format
"""
import logging
from flask import Blueprint, request, jsonify
from app.services.llm_client import get_llm_service
from app.config import config

logger = logging.getLogger('autonomousflow.transform')

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
            logger.error("Could not initialize LLM service")
            return jsonify({'error': 'Could not initialize LLM service'}), 500
        
        logger.info("=" * 60)
        logger.info("🔄 STAGE 3: DATA TRANSFORMATION")
        logger.info("=" * 60)
        
        result = llm_service.transform_to_structured_data(raw_data)
        
        logger.info(f"✅ Transformed {len(raw_data)} fields (confidence: {result['structure_confidence']:.0%})")
        logger.info("=" * 60)
        
        return jsonify({
            'document_id': document_id,
            'structured_data': result['structured_data'],
            'structure_confidence': result['structure_confidence'],
            'status': 'transformed'
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Transformation failed: {e}")
        return jsonify({'error': str(e)}), 500
