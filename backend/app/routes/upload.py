"""
Document Upload Routes
Handles initial document upload from frontend
"""
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

bp = Blueprint('upload', __name__, url_prefix='/api/documents')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif', 'bmp', 'tiff', 'svg'}

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/upload', methods=['POST'])
def upload_document():
    """
    Upload a document file
    
    Returns:
        JSON response with document_id, file_name, and status
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        filename = secure_filename(file.filename)
        document_id = str(uuid.uuid4())
        
        return jsonify({
            'document_id': document_id,
            'file_name': filename,
            'status': 'uploaded'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
