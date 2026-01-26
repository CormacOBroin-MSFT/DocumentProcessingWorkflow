"""
Cosmos DB Storage Routes
Handles storing processed customs declarations in Azure Cosmos DB
"""
import logging
from flask import Blueprint, request, jsonify
from app.services.azure_cosmos import get_cosmos_service
from app.config import config

logger = logging.getLogger('autonomousflow.cosmosdb')

bp = Blueprint('cosmosdb', __name__, url_prefix='/api/cosmosdb')


@bp.route('/store', methods=['POST'])
def store_declaration():
    """
    Store a processed customs declaration in Cosmos DB
    
    Expects JSON body:
    {
        "documentId": "uuid",
        "fileName": "invoice.pdf",
        "blobUrl": "https://...",
        "structuredData": {...},
        "confidenceScores": {...},
        "complianceChecks": [...],
        "complianceDescriptions": [...],
        "approvalStatus": "approved",
        "reviewerNotes": "...",
        "submissionId": "CUSTOMS-..."
    }
    
    Returns:
        JSON with storage result
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    # Check if Cosmos DB is configured
    if not config.is_cosmos_configured():
        logger.error("Cosmos DB not configured - AZURE_COSMOS_ENDPOINT is not set")
        return jsonify({
            'error': 'Cosmos DB not configured. Please run setup-azure.sh to provision Azure resources and restart the backend.'
        }), 503
    
    try:
        cosmos_service = get_cosmos_service()
        
        if not cosmos_service:
            logger.error("Could not initialize Cosmos DB service")
            return jsonify({
                'error': 'Could not connect to Cosmos DB. Check your Azure credentials and ensure you are logged in with: az login'
            }), 500
        
        logger.info("=" * 60)
        logger.info("💾 STAGE 8: COSMOS DB STORAGE")
        logger.info("   Storing declaration in Azure Cosmos DB")
        logger.info("=" * 60)
        
        result = cosmos_service.store_declaration(data)
        
        logger.info(f"✅ Declaration stored: {result.get('documentId')}")
        logger.info("=" * 60)
        
        return jsonify({
            'documentId': result.get('documentId'),
            'id': result.get('id'),
            'status': result.get('status'),
            'createdAt': result.get('createdAt'),
            'message': 'Declaration successfully stored in Cosmos DB'
        }), 200
        
    except Exception as e:
        logger.error(f"Cosmos DB storage failed: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/declaration/<document_id>', methods=['GET'])
def get_declaration(document_id: str):
    """
    Retrieve a customs declaration from Cosmos DB
    
    Args:
        document_id: The document ID to retrieve
        
    Returns:
        JSON with the declaration data
    """
    if not config.is_cosmos_configured():
        return jsonify({'error': 'Cosmos DB not configured'}), 503
    
    try:
        cosmos_service = get_cosmos_service()
        
        if not cosmos_service:
            return jsonify({'error': 'Could not initialize Cosmos DB service'}), 500
        
        result = cosmos_service.get_declaration(document_id)
        
        if not result:
            return jsonify({'error': 'Declaration not found'}), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Failed to get declaration: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/declarations', methods=['GET'])
def list_declarations():
    """
    List recent customs declarations from Cosmos DB
    
    Query params:
        limit: Maximum number of declarations to return (default: 50)
        
    Returns:
        JSON array of declarations
    """
    if not config.is_cosmos_configured():
        return jsonify({'error': 'Cosmos DB not configured'}), 503
    
    try:
        limit = request.args.get('limit', 50, type=int)
        
        cosmos_service = get_cosmos_service()
        
        if not cosmos_service:
            return jsonify({'error': 'Could not initialize Cosmos DB service'}), 500
        
        results = cosmos_service.list_declarations(limit=limit)
        
        return jsonify({
            'declarations': results,
            'count': len(results)
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to list declarations: {e}")
        return jsonify({'error': str(e)}), 500
