"""
Flask Application Factory
Creates and configures the Flask application with CORS and blueprints
Serves both API endpoints and static frontend files in production

NOTE: OpenTelemetry tracing is configured in run.py at startup (before any imports).
"""
import logging
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from dotenv import load_dotenv
import os

def create_app():
    load_dotenv()
    
    # Configure logging
    log_level = logging.DEBUG if os.environ.get('FLASK_DEBUG', '').lower() == 'true' else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger('autonomousflow')
    
    # Suppress noisy werkzeug access logs
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Check for static files (production build)
    static_folder = os.path.join(os.path.dirname(__file__), '..', 'static')
    has_static = os.path.exists(static_folder) and os.path.exists(os.path.join(static_folder, 'index.html'))
    
    if has_static:
        app = Flask(__name__, static_folder=static_folder, static_url_path='')
        logger.info("Running in production mode with static files")
    else:
        app = Flask(__name__)
        logger.info("Running in development mode (no static files)")
    
    # Log configuration status
    from app.config import config
    logger.info(f"Azure Storage configured: {bool(config.AZURE_STORAGE_CONNECTION_STRING)}")
    logger.info(f"Content Understanding configured: {bool(config.AZURE_CONTENT_UNDERSTANDING_ENDPOINT)}")
    logger.info(f"Document Intelligence configured: {bool(config.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT)}")
    logger.info(f"OCR Service: {config.get_ocr_service_type()}")
    logger.info(f"Azure OpenAI configured: {bool(config.AZURE_OPENAI_ENDPOINT)}")
    logger.info(f"Azure OpenAI deployment: {config.AZURE_OPENAI_DEPLOYMENT}")
    logger.info(f"Azure Cosmos DB configured: {bool(config.AZURE_COSMOS_ENDPOINT)}")
    
    # CORS only needed in development (when frontend runs separately)
    if os.environ.get('FLASK_ENV') == 'development' or not has_static:
        CORS(app, resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
        logger.info("CORS enabled for development")
    
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    # Request logging - only log errors and non-status endpoints at debug level
    @app.before_request
    def log_request():
        if request.path.startswith('/api') and request.path != '/api/status':
            logger.debug(f"→ {request.method} {request.path}")
    
    @app.after_request
    def log_response(response):
        if request.path.startswith('/api') and request.path != '/api/status':
            if response.status_code >= 400:
                logger.warning(f"← {request.method} {request.path} [{response.status_code}]")
            else:
                logger.debug(f"← {request.method} {request.path} [{response.status_code}]")
        return response
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'AI Document Processing API',
            'version': '1.0.0'
        })
    
    @app.route('/api/status', methods=['GET'])
    def api_status():
        """Return configuration status for frontend"""
        return jsonify({
            'azureConfigured': config.is_azure_configured(),
            'openaiConfigured': config.is_openai_configured(),
            'cosmosConfigured': config.is_cosmos_configured(),
            'services': {
                'storage': bool(config.AZURE_STORAGE_CONNECTION_STRING),
                'documentIntelligence': bool(config.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT),
                'openai': bool(config.AZURE_OPENAI_ENDPOINT),
                'cosmosdb': bool(config.AZURE_COSMOS_ENDPOINT)
            }
        })
    
    from app.routes import upload, storage, ocr, transform, compliance, customs, cosmosdb, agents
    
    app.register_blueprint(upload.bp)
    app.register_blueprint(storage.bp)
    app.register_blueprint(ocr.bp)
    app.register_blueprint(transform.bp)
    app.register_blueprint(compliance.bp)
    app.register_blueprint(customs.bp)
    app.register_blueprint(cosmosdb.bp)
    app.register_blueprint(agents.bp)
    
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
