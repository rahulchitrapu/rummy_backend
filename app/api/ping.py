from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)
ping_bp = Blueprint('ping', __name__)

# GET /api/ping/ - Health check endpoint
@ping_bp.route('/', methods=['GET'])
def ping():
    try:
        return jsonify({'message': 'pong'})
    except Exception as e:
        logger.error(f'Ping error: {e}')
        return jsonify({'error': 'Failed to ping'}), 500        
    