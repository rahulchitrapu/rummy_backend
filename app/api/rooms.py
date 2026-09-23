from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from datetime import datetime
import secrets
import string
from app.config import Config
import logging

from app.database.supabase_connection import delete_record, get_rooms_table, get_table, insert_record, update_record

logger = logging.getLogger(__name__)
rooms_bp = Blueprint('rooms', __name__)

# In-memory storage for active games
active_games = {}


def is_duplicate_room_player_error(error):
    error_message = str(error)
    return (
        "room_players_room_id_user_id_key" in error_message
        or "duplicate key value violates unique constraint" in error_message
    )

def generate_room_code():
    """Generate random 6-digit room code, unique among active rooms"""
    while True:
        code = ''.join(secrets.choice(string.digits) for _ in range(6))

        existing = get_table(
            "rooms",
            columns="id",
            filters={"room_code": code, "status": "active"}
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
        delete_record("rooms", filters={"id": room_id})
        
        return jsonify({'message': 'Room deleted'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to delete room'}), 500

# POST /api/rooms/join - Join room
@rooms_bp.route('/join', methods=['POST'])
def join_room():
    try:
        joining_code = request.json.get('room_code')
        user_id = request.json.get('user_id')

        if not joining_code or not user_id:
            return jsonify({'error': 'room_code and user_id required'}), 400

        rooms = get_rooms_table(
            columns="id, room_code, status, max_players, created_by",
            filters={"room_code": joining_code}
        )

        if not rooms:
            return jsonify({'error': 'Invalid room code'}), 400

        room = rooms[0]

        # Check if user is already in the room
        existing_player = get_table(
            "room_players",
            columns="id, room_id, user_id, is_host, is_ready, score, joined_at",
            filters={"room_id": room["id"], "user_id": user_id}
        )

        if existing_player:
            return jsonify({
                'message': 'User already exists in the room',
                'room': room,
                'room_player': existing_player[0]
            }), 200

        try:
            insert_record("room_players",{
                "room_id": room["id"],
                "user_id": user_id,
                "is_host": user_id == room["created_by"]
            })
        except Exception as insert_error:
            if is_duplicate_room_player_error(insert_error):
                existing_player = get_table(
                    "room_players",
                    columns="id, room_id, user_id, is_host, is_ready, score, joined_at",
                    filters={"room_id": room["id"], "user_id": user_id}
                )
                return jsonify({
                    'message': 'User already exists in the room',
                    'room': room,
                    'room_player': existing_player[0] if existing_player else None
                }), 200
            raise insert_error

        return jsonify({'message': 'Joined room successfully', 'room': room})
        
    except Exception as e:
        logger.error(f'Join room error: {e}')
        return jsonify({'error': 'Failed to join room'}), 500

# GET /api/rooms/user/<user_id>/ - Get active games for a user
@rooms_bp.route('/user/<int:user_id>/', methods=['GET'])
def get_active_rooms_for_user(user_id):
    try:
        player_rooms = get_table(
            "room_players",
            columns="is_host, room:rooms(id, room_code, status, max_players, created_by, member_count)",
            filters={"user_id": user_id}
        )

        active_rooms = []
        for pr in player_rooms:
            room = pr.get("room")
            if not room or room.get("status") not in ("active", "waiting"):
                continue

            room["is_host"] = pr.get("is_host", False)
            active_rooms.append(room)

        return jsonify({"rooms": active_rooms})

    except Exception as e:
        logger.error(f'Get active rooms error: {e}')
        return jsonify({'error': 'Failed to get active rooms'}), 500

# POST /api/rooms/leave - Leave room
@rooms_bp.route('/leave', methods=['POST'])
def leave_room():
    try:
        data = request.get_json()

        room_id = data.get('room_id')
        user_id = data.get('user_id')

        if not room_id or not user_id:
            return jsonify({'error': 'room_id and user_id required'}), 400
          
        delete_record("room_players",filters={
            "room_id": room_id,
            "user_id": user_id
        })

        return jsonify({'message': 'Left room successfully'})
        
    except Exception as e:
        logger.error(f'Leave room error: {e}')
        return jsonify({'error': 'Failed to leave room'}), 500
