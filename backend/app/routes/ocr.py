"""
OCR Processing Routes
Handles document analysis with Azure AI Document Intelligence
"""
from flask import Blueprint, request, jsonify
from app.services.azure_doc_intelligence import get_document_intelligence_service
from app.config import config

bp = Blueprint('ocr', __name__, url_prefix='/api/ocr')

@bp.route('/analyze', methods=['POST'])
def analyze_document():
    """
    Analyze a document using Azure AI Document Intelligence
    
    Expects JSON body:
    {
        "document_id": "uuid",
        "blob_url": "https://..."
    }
    
    Returns:
        JSON with raw_data (key-value pairs) and ocr_confidence
    """
    if not config.is_azure_configured():
        return jsonify({
            'error': 'Azure Document Intelligence not configured',
            'mock_mode': True
        }), 503
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    blob_url = data.get('blob_url')
    document_id = data.get('document_id')
    
    if not blob_url:
        return jsonify({'error': 'blob_url required'}), 400
    
    try:
        doc_intelligence_service = get_document_intelligence_service()
        
        if not doc_intelligence_service:
            return jsonify({'error': 'Could not initialize document intelligence service'}), 500
        
        result = doc_intelligence_service.analyze_document(blob_url)
        
        return jsonify({
            'document_id': document_id,
            'raw_data': result['raw_data'],
            'ocr_confidence': result['ocr_confidence'],
            'status': 'analyzed'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
