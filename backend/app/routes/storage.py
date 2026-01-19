"""
Azure Storage Routes
Handles document storage in Azure Blob Storage
"""
from flask import Blueprint, request, jsonify
from app.services.azure_blob import get_blob_service
from app.config import config

bp = Blueprint('storage', __name__, url_prefix='/api/storage')

@bp.route('/upload', methods=['POST'])
def upload_to_storage():
    """
    Upload document to Azure Blob Storage
    
    Expects multipart/form-data with:
    - file: The document file
    - document_id: UUID of the document (optional)
    
    Returns:
        JSON with blob_url and status
    """
    if not config.is_azure_configured():
        return jsonify({
            'error': 'Azure Storage not configured',
            'mock_mode': True
        }), 503
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    document_id = request.form.get('document_id', '')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        blob_service = get_blob_service()
        
        if not blob_service:
            return jsonify({'error': 'Could not initialize blob service'}), 500
        
        blob_url = blob_service.upload_file(
            file.stream,
            file.filename,
            file.content_type or 'application/octet-stream'
        )
        
        return jsonify({
            'document_id': document_id,
            'blob_url': blob_url,
            'status': 'stored'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
