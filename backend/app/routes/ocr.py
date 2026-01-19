"""
OCR Processing Routes
Handles document analysis with Azure AI Content Understanding
Extracts structured customs declaration fields directly from documents
"""
import logging
from flask import Blueprint, request, jsonify
from app.services.azure_content_understanding import get_content_understanding_service
from app.config import config

logger = logging.getLogger('autonomousflow.ocr')

bp = Blueprint('ocr', __name__, url_prefix='/api/ocr')

@bp.route('/analyze', methods=['POST'])
def analyze_document():
    """
    Analyze a document using Azure AI Document Intelligence
    Extracts structured customs declaration fields directly
    
    Expects JSON body:
    {
        "document_id": "uuid",
        "blob_url": "https://..."
    }
    
    Returns:
        JSON with structured_data (customs fields with confidence), raw_data, and ocr_confidence
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    blob_url = data.get('blob_url')
    document_id = data.get('document_id')
    
    if not blob_url:
        return jsonify({'error': 'blob_url required'}), 400
    
    try:
        # Use Content Understanding service (which uses Document Intelligence under the hood)
        ocr_service = get_content_understanding_service()
        service_name = "Azure Document Intelligence"
        
        if not ocr_service:
            logger.error("No OCR service available")
            return jsonify({'error': 'No OCR service available'}), 500
        
        logger.info("=" * 60)
        logger.info("🔍 STAGE 2: OCR + TRANSFORMATION")
        logger.info("   Content Understanding")
        logger.info("=" * 60)
        
        result = ocr_service.analyze_document(blob_url)
        
        structured_data = result.get('structured_data', {})
        raw_data = result.get('raw_data', {})
        fields_found = len([f for f in structured_data.values() if f.get('value')])
        
        logger.info(f"✅ Extracted {fields_found}/7 fields (confidence: {result['ocr_confidence']:.0%})")
        logger.info("=" * 60)
        
        return jsonify({
            'document_id': document_id,
            'structured_data': structured_data,
            'raw_data': raw_data,
            'ocr_confidence': result['ocr_confidence'],
            'status': 'analyzed'
        }), 200
    
    except Exception as e:
        logger.error(f"OCR analysis failed: {e}")
        return jsonify({'error': str(e)}), 500
