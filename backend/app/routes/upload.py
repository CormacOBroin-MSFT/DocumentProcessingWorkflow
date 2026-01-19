"""
Document Upload Routes
Handles initial document upload from frontend
"""
import uuid
import logging
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.services.azure_blob import get_blob_service
from app.config import config

logger = logging.getLogger('autonomousflow.upload')

bp = Blueprint('upload', __name__, url_prefix='/api')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif', 'bmp', 'tiff', 'svg'}

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/upload', methods=['POST'])
def upload_document():
    """
    Upload a document file to Azure Blob Storage
    
    Returns:
        JSON response with document_id, blob_url, and status
    """
    if 'file' not in request.files:
        logger.warning("Upload request missing file")
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        logger.warning("Upload request with empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        logger.warning(f"Invalid file type: {file.filename}")
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        filename = secure_filename(file.filename)
        document_id = str(uuid.uuid4())
        
        # Try to upload to Azure Blob Storage
        blob_service = get_blob_service()
        if blob_service:
            logger.info("=" * 60)
            logger.info("📤 STAGE 1: UPLOAD TO AZURE STORAGE")
            logger.info("=" * 60)
            
            blob_url = blob_service.upload_file(
                file.stream,
                filename,
                file.content_type or 'application/octet-stream'
            )
            
            logger.info(f"✅ Uploaded: {filename}")
            logger.info("=" * 60)
            
            return jsonify({
                'document_id': document_id,
                'file_name': filename,
                'blob_url': blob_url,
                'url': blob_url,
                'status': 'uploaded'
            }), 200
        else:
            # Mock mode - return fake URL
            logger.info("⚠️  Azure not configured, using MOCK mode")
            mock_url = f"https://mock-storage.blob.core.windows.net/documents/{document_id}/{filename}"
            return jsonify({
                'document_id': document_id,
                'file_name': filename,
                'blob_url': mock_url,
                'url': mock_url,
                'status': 'uploaded',
                'mock': True
            }), 200
    
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/documents/upload', methods=['POST'])
def upload_document_legacy():
    """Legacy endpoint - redirects to main upload"""
    return upload_document()
