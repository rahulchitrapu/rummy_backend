from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import jwt
import re
from app.config import Config
from app.database.supabase_connection import get_users_table as get_supabase_users_table, insert_record, update_record, select_records, delete_record
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
        # users = list(get_users_collection().find({}).limit(20))

        users = list(get_supabase_users_table())

        print("Fetched users:", users)
        
        return jsonify({
            'users': [{
                'id': str(u['id']),
                'name': u.get('name', ''),
                'email': u.get('email', ''),
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
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Check if all required fields are present
        if not name or not email or not password:
            return jsonify({'error': 'Name, email, and password are required'}), 400
        
        # Simple validation
        if len(name) < 2:
            return jsonify({'error': 'Name too short'}), 400
        if not validate_email(email):
            return jsonify({'error': 'Invalid email'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password too short'}), 400
        
        # Check if user already exists
        existing_users = select_records('users', '*', {'email': email})
        if existing_users.data:
            return jsonify({'error': 'User already exists'}), 409
        
        # Create user
        user_data = {
            'name': name,
            'email': email,
            'password': generate_password_hash(password),
            
        }
        
        result = insert_record('users', user_data)
        new_user = result.data[0] if result.data else None
        
        if not new_user:
            return jsonify({'error': 'Failed to create user'}), 500
        
        token = generate_token(new_user['id'])
        
        return jsonify({
            'user': {
                'id': new_user['id'],
                'name': new_user['name'],
                'email': new_user['email']
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
        # Get user by ID
        users = select_records('users', 'id,name,email,created_at', {'id': user_id})
        
        if not users.data:
            return jsonify({'error': 'User not found'}), 404
        
        user = users.data[0]
        
        return jsonify({
            'user': {
                'id': user['id'],
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'created_at': user.get('created_at', '')
            }
        })
        
    except Exception as e:
        return jsonify({'error': 'Failed to get user'}), 500

# PUT /api/users/<id> - Update user
@users_bp.route('/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        # Check if user exists
        existing_users = select_records('users', '*', {'id': user_id})
        if not existing_users.data:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        update_fields = {}
        
        if 'name' in data and data['name'].strip():
            update_fields['name'] = data['name'].strip()
        if 'email' in data and data['email'].strip():
            email = data['email'].strip().lower()
            if not validate_email(email):
                return jsonify({'error': 'Invalid email'}), 400
            update_fields['email'] = email
        if 'password' in data and data['password']:
            if len(data['password']) < 6:
                return jsonify({'error': 'Password too short'}), 400
            update_fields['password'] = generate_password_hash(data['password'])

        if update_fields:
            update_record('users', update_fields, {'id': user_id})

        updated_user = select_records('users', 'id,name,email,created_at', {'id': user_id})
        updated_record = updated_user.data[0] if updated_user.data else None
        
        return jsonify({'message': 'User updated', 'user': updated_record})
        
    except Exception as e:
        return jsonify({'error': 'Failed to update user'}), 500

# DELETE /api/users/<id> - Delete user
@users_bp.route('/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # Check if user exists
        existing_users = select_records('users', '*', {'id': user_id})
        if not existing_users.data:
            return jsonify({'error': 'User not found'}), 404
        
        # Delete the user
        delete_record('users', {'id': user_id})
        
        return jsonify({'message': 'User deleted'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to delete user'}), 500

# POST /api/users/login - Login
@users_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user by email
        users = select_records('users', '*', {'email': email})
        
        if not users.data:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        user = users.data[0]
        
        if not check_password_hash(user.get('password', ''), password):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = generate_token(user['id'])
        
        return jsonify({
            'user': {
                'id': user['id'],
                'name': user.get('name', ''),
                'email': user.get('email', '')
            },
            'token': token
        })
        
    except Exception as e:
        return jsonify({'message': 'Login failed'}), 500

