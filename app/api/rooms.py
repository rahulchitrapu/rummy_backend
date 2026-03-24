from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from datetime import datetime
import secrets
import string
from app.config import Config
import logging

from app.database.supabase_connection import get_rooms_table, get_table, insert_record

logger = logging.getLogger(__name__)
rooms_bp = Blueprint('rooms', __name__)

# In-memory storage for active games
active_games = {}

def generate_room_code():
    """Generate random room code"""
    characters = string.ascii_uppercase + string.digits

    while True:
        code = ''.join(secrets.choice(characters) for _ in range(8))

        existing = get_table(
            "rooms",
            columns="id",
            filters={"room_code": code}
        )

        if not existing:
            return code

# GET /api/rooms/ - Get all rooms
@rooms_bp.route('/', methods=['GET'])
def get_rooms():
    try:
        rooms = get_rooms_table(columns="*,users(*)")
        
        rooms_data=[]
        for room in rooms:
            
            onwer_data = room.get('users',{})
            rooms_data.append(
                {
                    "id":room.get("id"),
                    "room_code":room.get("room_code"),
                    "status":room.get("status"),
                    "max_players":room.get("max_players"),
                    "created_by":room.get("created_by"),
                    "owner_name":onwer_data.get('name')
                } 
            )
        
        return jsonify({"rooms": rooms_data})

    except Exception as e:
        logger.error(f'Get rooms error: {e}')
        return jsonify({'error': 'Failed to get rooms'}), 500

# POST /api/rooms/ - Create room
@rooms_bp.route('/userid/<int:user_id>', methods=['POST'])
def create_room(user_id):
    try:
        room_code = generate_room_code()

        room = insert_record("rooms",{
            "room_code": room_code,
            "created_by": user_id,
            "max_players": 6
        }).data[0]

        # add host player
        insert_record("room_players",{
            "room_id": room["id"],
            "user_id": user_id,
            "is_host": True
        })

        return {
            "room_id": room["id"],
            "room_code": room_code
        }
        
    except Exception as e:
        logger.error(f'Create room error: {e}')
        return jsonify({'error': 'Failed to create room'}), 500

# GET /api/rooms/<id> - Get single room
@rooms_bp.route('/<room_id>', methods=['GET'])
def get_room(room_id):
    try:
        SAFE_USER_FIELDS = "id, name, email,dp"
        SAFE_ROOM_PLAYER_FIELDS = "id, score, is_host, is_ready, joined_at"
        room = get_rooms_table(
            columns=f"""
            *,
            room_players(
                {SAFE_ROOM_PLAYER_FIELDS},
               player:users({SAFE_USER_FIELDS})
            )
            """,
            filters={"id": room_id}
        )[0]
        
        
        return jsonify(
             {
                    "id":room.get("id"),
                    "room_code":room.get("room_code"),
                    "status":room.get("status"),
                    "max_players":room.get("max_players"),
                    "created_by":room.get("created_by"),
                    "room_players":room.get("room_players",[])
                } 
        )

    except Exception as e:
        logger.error(f'Get room error: {e}')
        return jsonify({'error': 'Failed to get room'}), 500

# PUT /api/rooms/<id> - Update room
@rooms_bp.route('/<room_id>', methods=['PUT'])
def update_room(room_id):
    try:
       
        return jsonify({'message': 'Room updated'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to update room'}), 500

# DELETE /api/rooms/<id> - Delete room
@rooms_bp.route('/<room_id>', methods=['DELETE'])
def delete_room(room_id):
    try:
       
        
        return jsonify({'message': 'Room deleted'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to delete room'}), 500

# POST /api/rooms/join - Join room
@rooms_bp.route('/join/<int:room_id>', methods=['POST'])
def join_room(room_id):
    try:
        room = get_rooms_table(columns="room_code,id",filters={"id":room_id})[0]

        joining_code = request.json.get('room_code')
        player_id = request.json.get('player_id')
        if room['room_code'] != joining_code:
            return jsonify({'error': 'Invalid room code'}), 400
        

        insert_record("room_players",{
            "room_id": room["id"],
            "user_id": player_id,
            "is_host": False
        })

        
        
        return jsonify({'message': 'Joined room successfully'})
        
    except Exception as e:
        logger.error(f'Join room error: {e}')
        return jsonify({'error': 'Failed to join room'}), 500

# POST /api/rooms/leave - Leave room
@rooms_bp.route('/leave', methods=['POST'])
def leave_room():
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        player_id = data.get('player_id')
        
        if not room_id or not player_id:
            return jsonify({'error': 'room_id and player_id required'}), 400
        
        # Remove player from room
        get_rooms_collection().update_one(
            {'_id': ObjectId(room_id)},
            {'$pull': {'players': {'user_id': ObjectId(player_id)}}}
        )
        
        return jsonify({'message': 'Left room successfully'})
        
    except Exception as e:
        logger.error(f'Leave room error: {e}')
        return jsonify({'error': 'Failed to leave room'}), 500
