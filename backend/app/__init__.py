"""
Flask Application Factory
Creates and configures the Flask application with CORS and blueprints
Serves both API endpoints and static frontend files in production
"""
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os

def create_app():
    load_dotenv()
    
    # Check for static files (production build)
    static_folder = os.path.join(os.path.dirname(__file__), '..', 'static')
    has_static = os.path.exists(static_folder) and os.path.exists(os.path.join(static_folder, 'index.html'))
    
    if has_static:
        app = Flask(__name__, static_folder=static_folder, static_url_path='')
    else:
        app = Flask(__name__)
    
    # CORS only needed in development (when frontend runs separately)
    if os.environ.get('FLASK_ENV') == 'development' or not has_static:
        CORS(app, resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
    
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'AI Document Processing API',
            'version': '1.0.0'
        })
    
    from app.routes import upload, storage, ocr, transform, compliance, customs
    
    app.register_blueprint(upload.bp)
    app.register_blueprint(storage.bp)
    app.register_blueprint(ocr.bp)
    app.register_blueprint(transform.bp)
    app.register_blueprint(compliance.bp)
    app.register_blueprint(customs.bp)
    
    # Serve React app for non-API routes (production only)
    if has_static:
        @app.route('/')
        def serve_root():
            return send_from_directory(app.static_folder, 'index.html')
        
        @app.route('/<path:path>')
        def serve_static(path):
            # Serve static file if it exists, otherwise return index.html for SPA routing
            file_path = os.path.join(app.static_folder, path)
            if os.path.isfile(file_path):
                return send_from_directory(app.static_folder, path)
            return send_from_directory(app.static_folder, 'index.html')
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app
