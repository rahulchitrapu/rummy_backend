from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime
import jwt
import re
from app.config import Config
from app.database.mongo import get_users_collection
import logging

logger = logging.getLogger(__name__)
users_bp = Blueprint('users', __name__)

def validate_email(email):
    """Simple email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_token(user_id):
    """Generate JWT token"""
    payload = {
        'user_id': str(user_id),
        'exp': datetime.utcnow().timestamp() + Config.JWT_ACCESS_TOKEN_EXPIRES
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')

# GET /api/users/ - Get all users
@users_bp.route('/', methods=['GET'])
def get_users():
    try:
        users = list(get_users_collection().find({}).limit(20))

        print("Fetched users:", users)
        
        return jsonify({
            'users': [{
                'id': str(u['_id']),
                'username': u.get('username', ''),
                'name': u.get('name', ''),
                'email': u.get('email', ''),
                'age': u.get('age', '')
            } for u in users]
        })
    except Exception as e:
        print("Error getting users:", e)
        return jsonify({'error': 'Failed to get users'}), 500

# POST /api/users/ - Create user
@users_bp.route('/', methods=['POST'])
def create_user():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        age = data.get('age')
        
        # Check if all required fields are present
        if not username or not name or not email or not password or not age:
            return jsonify({'error': 'All fields are required'}), 400
        
        # Simple validation
        if len(username) < 3:
            return jsonify({'error': 'Username too short'}), 400
        if email and not validate_email(email):
            return jsonify({'error': 'Invalid email'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password too short'}), 400
        
        # Check if exists
        users_collection = get_users_collection()
        if users_collection.find_one({'username': username}):
            return jsonify({'error': 'User already exists'}), 409
        
        # Create user
        user_doc = {
            'username': username,
            'password': generate_password_hash(password),
            'created_at': datetime.utcnow(),
            'is_active': True,
            'stats': {'games_played': 0, 'games_won': 0}
        }
        
        if name:
            user_doc['name'] = name
        if email:
            user_doc['email'] = email
        if age:
            user_doc['age'] = age
        
        result = users_collection.insert_one(user_doc)
        token = generate_token(result.inserted_id)
        
        return jsonify({
            'user': {
                'id': str(result.inserted_id),
                'username': username,
                'name': user_doc.get('name', ''),
                'email': user_doc.get('email', ''),
                'age': user_doc.get('age', '')
            },
            'token': token
        }), 201
        
    except Exception as e:
        print("Error creating user:", e)
        return jsonify({'error': 'Failed to create user'}), 500

# GET /api/users/<id> - Get single user
@users_bp.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        if not ObjectId.is_valid(user_id):
            return jsonify({'error': 'Invalid user ID'}), 400
        
        user = get_users_collection().find_one(
            {'_id': ObjectId(user_id)}, 
            {'password': 0}
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': {
                'id': str(user['_id']),
                'username': user.get('username', ''),
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'age': user.get('age', ''),
                'stats': user.get('stats', {})
            }
        })
        
    except Exception as e:
        return jsonify({'error': 'Failed to get user'}), 500

# PUT /api/users/<id> - Update user
@users_bp.route('/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        if not ObjectId.is_valid(user_id):
            return jsonify({'error': 'Invalid user ID'}), 400
        
        data = request.get_json()
        update_fields = {}
        
        if 'username' in data:
            update_fields['username'] = data['username'].strip()
        if 'name' in data:
            update_fields['name'] = data['name'].strip()
        if 'email' in data:
            update_fields['email'] = data['email'].strip().lower()
        if 'age' in data:
            update_fields['age'] = data['age']
        if 'password' in data:
            update_fields['password'] = generate_password_hash(data['password'])
        
        if update_fields:
            get_users_collection().update_one(
                {'_id': ObjectId(user_id)},
                {'$set': update_fields}
            )
        
        return jsonify({'message': 'User updated'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to update user'}), 500

# DELETE /api/users/<id> - Delete user
@users_bp.route('/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        if not ObjectId.is_valid(user_id):
            return jsonify({'error': 'Invalid user ID'}), 400
        
        result = get_users_collection().delete_one(
            {'_id': ObjectId(user_id)}
        )
        
        if result.deleted_count == 0:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'message': 'User deleted'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to delete user'}), 500

# POST /api/users/login - Login
@users_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        user = get_users_collection().find_one({
            '$or': [{'username': username}, {'email': username}]
        })
        
        if not user or not check_password_hash(user.get('password', ''), password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.get('is_active', True):
            return jsonify({'error': 'Account deactivated'}), 401
        
        token = generate_token(user['_id'])
        
        return jsonify({
            'user': {
                'id': str(user['_id']),
                'username': user.get('username', ''),
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'age': user.get('age', '')
            },
            'token': token
        })
        
    except Exception as e:
        return jsonify({'error': 'Login failed'}), 500

# GET /api/users/leaderboard - Get user leaderboard
@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get user leaderboard"""
    try:
        users_collection = get_users_collection()
        
        # Get top 10 users by games won
        users = list(users_collection.find(
            {'is_active': True},
            {'username': 1, 'name': 1, 'stats': 1}
        ).sort('stats.games_won', -1).limit(10))
        
        leaderboard = []
        for i, user in enumerate(users):
            stats = user.get('stats', {})
            leaderboard.append({
                'rank': i + 1,
                'username': user.get('username', ''),
                'name': user.get('name', ''),
                'games_played': stats.get('games_played', 0),
                'games_won': stats.get('games_won', 0),
                'win_rate': stats.get('games_won', 0) / max(stats.get('games_played', 1), 1) * 100
            })
        
        return jsonify({'leaderboard': leaderboard}), 200
        
    except Exception as e:
        logger.error(f'Leaderboard error: {e}')
        return jsonify({'error': 'Internal server error'}), 500