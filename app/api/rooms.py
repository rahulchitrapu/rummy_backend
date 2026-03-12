from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import random
import string
from app.config import Config
from app.database.mongo import get_rooms_collection, get_users_collection
import logging

logger = logging.getLogger(__name__)
rooms_bp = Blueprint('rooms', __name__)

# In-memory storage for active games
active_games = {}

def generate_room_code():
    """Generate random room code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# GET /api/rooms/ - Get all rooms
@rooms_bp.route('/', methods=['GET'])
def get_rooms():
    try:
        rooms = list(get_rooms_collection().find({}).limit(20).sort('createdAt', -1))
        
        return jsonify({
            'rooms': [{
                'id': str(r['_id']),
                'roomCode': r['roomCode'],
                'roomName': r['roomName'],
                'host': r['host'],
                'status': r['status'],
                'currentPlayers': len(r['players']),
                'maxPlayers': r['maxPlayers'],
                'maxScore': r['max_score'],
                'jokerCount': r['jokerCount'],
                'currentRound': r.get('currentRound', 1)
            } for r in rooms]
        })
    except Exception as e:
        logger.error(f'Get rooms error: {e}')
        return jsonify({'error': 'Failed to get rooms'}), 500

# POST /api/rooms/ - Create room
@rooms_bp.route('/', methods=['POST'])
def create_room():
    try:
        data = request.get_json()
        created_by = data.get('created_by')
        room_name = data.get('room_name', 'Rummy Room')
        max_score = data.get('max_score', 200)
        joker_count = data.get('joker_count', 2)
        
        if not created_by:
            return jsonify({'error': 'created_by required'}), 400
        
        # Get creator username
        creator = get_users_collection().find_one({'_id': ObjectId(created_by)})
        if not creator:
            return jsonify({'error': 'User not found'}), 404
        
        # Generate unique room code
        room_code = generate_room_code()
        
        # Create initial player object for host
        host_player = {
            'username': creator['username'],
            'user_id': ObjectId(created_by),
            'isHost': True,
            'isReady': False,
            'joinedAt': datetime.utcnow(),
            'totalLost': 0,
            'remaining': max_score,
            'thisRoundLost': 0,
            'isOut': False,
            'scoreHistory': []
        }
        
        room_doc = {
            'roomCode': room_code,
            'roomName': room_name,
            'host': creator['username'],
            'max_score': max_score,
            'jokerCount': joker_count,
            'maxPlayers': 6,  # Fixed at 6 for now
            'status': 'waiting',
            'players': [host_player],
            'currentRound': 1,
            'currentGameId': None,
            'gameHistory': [],
            'createdAt': datetime.utcnow(),
            'startedAt': None,
            'finishedAt': None
        }
        
        result = get_rooms_collection().insert_one(room_doc)
        
        return jsonify({
            'room': {
                'id': str(result.inserted_id),
                'roomCode': room_code,
                'roomName': room_name,
                'status': 'waiting',
                'maxScore': max_score,
                'jokerCount': joker_count,
                'maxPlayers': 6
            }
        }), 201
        
    except Exception as e:
        logger.error(f'Create room error: {e}')
        return jsonify({'error': 'Failed to create room'}), 500

# GET /api/rooms/<id> - Get single room
@rooms_bp.route('/<room_id>', methods=['GET'])
def get_room(room_id):
    try:
        if not ObjectId.is_valid(room_id):
            return jsonify({'error': 'Invalid room ID'}), 400
        
        room = get_rooms_collection().find_one({'_id': ObjectId(room_id)})
        
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Convert player ObjectIds to strings for JSON serialization
        players = []
        for player in room['players']:
            player_data = player.copy()
            player_data['user_id'] = str(player_data['user_id'])
            player_data['joinedAt'] = player_data['joinedAt'].isoformat()
            players.append(player_data)
        
        return jsonify({
            'room': {
                'id': str(room['_id']),
                'roomCode': room['roomCode'],
                'roomName': room['roomName'],
                'host': room['host'],
                'status': room['status'],
                'maxScore': room['max_score'],
                'jokerCount': room['jokerCount'],
                'maxPlayers': room['maxPlayers'],
                'currentPlayers': len(room['players']),
                'players': players,
                'currentRound': room['currentRound'],
                'createdAt': room['createdAt'].isoformat(),
                'startedAt': room['startedAt'].isoformat() if room['startedAt'] else None,
                'finishedAt': room['finishedAt'].isoformat() if room['finishedAt'] else None
            }
        })
        
    except Exception as e:
        logger.error(f'Get room error: {e}')
        return jsonify({'error': 'Failed to get room'}), 500

# PUT /api/rooms/<id> - Update room
@rooms_bp.route('/<room_id>', methods=['PUT'])
def update_room(room_id):
    try:
        if not ObjectId.is_valid(room_id):
            return jsonify({'error': 'Invalid room ID'}), 400
        
        data = request.get_json()
        update_fields = {}
        
        if 'max_players' in data:
            update_fields['max_players'] = data['max_players']
        if 'status' in data:
            update_fields['status'] = data['status']
        
        if update_fields:
            get_rooms_collection().update_one(
                {'_id': ObjectId(room_id)},
                {'$set': update_fields}
            )
        
        return jsonify({'message': 'Room updated'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to update room'}), 500

# DELETE /api/rooms/<id> - Delete room
@rooms_bp.route('/<room_id>', methods=['DELETE'])
def delete_room(room_id):
    try:
        if not ObjectId.is_valid(room_id):
            return jsonify({'error': 'Invalid room ID'}), 400
        
        # Remove from active games
        if room_id in active_games:
            del active_games[room_id]
        
        # Delete room
        get_rooms_collection().delete_one({'_id': ObjectId(room_id)})
        
        return jsonify({'message': 'Room deleted'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to delete room'}), 500

# POST /api/rooms/join - Join room
@rooms_bp.route('/join', methods=['POST'])
def join_room():
    try:
        data = request.get_json()
        room_code = data.get('room_code', '').upper()
        player_id = data.get('player_id')
        
        if not room_code or not player_id:
            return jsonify({'error': 'room_code and player_id required'}), 400
        
        # Find room
        room = get_rooms_collection().find_one({'roomCode': room_code})
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Check if room is full
        if len(room['players']) >= room['maxPlayers']:
            return jsonify({'error': 'Room is full'}), 409
        
        # Check if player is already in room
        for player in room['players']:
            if str(player['user_id']) == player_id:
                return jsonify({'error': 'Player already in room'}), 409
        
        # Get player info
        user = get_users_collection().find_one({'_id': ObjectId(player_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Create player object
        new_player = {
            'username': user['username'],
            'user_id': ObjectId(player_id),
            'isHost': False,
            'isReady': False,
            'joinedAt': datetime.utcnow(),
            'totalLost': 0,
            'remaining': room['max_score'],
            'thisRoundLost': 0,
            'isOut': False,
            'scoreHistory': []
        }
        
        # Add player to room
        get_rooms_collection().update_one(
            {'_id': room['_id']},
            {'$push': {'players': new_player}}
        )
        
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

# POST /api/rooms/<room_id>/start - Start game (only host can start)
@rooms_bp.route('/<room_id>/start', methods=['POST'])
def start_game(room_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        room = get_rooms_collection().find_one({'_id': ObjectId(room_id)})
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Check if player is host
        is_host = False
        for player in room['players']:
            if str(player['user_id']) == player_id and player['isHost']:
                is_host = True
                break
        
        if not is_host:
            return jsonify({'error': 'Only host can start the game'}), 403
        
        # Check if all players are ready
        all_ready = all(player['isReady'] for player in room['players'])
        if not all_ready:
            return jsonify({'error': 'All players must be ready'}), 400
        
        # Start the game
        update_result = get_rooms_collection().update_one(
            {'_id': ObjectId(room_id)},
            {
                '$set': {
                    'status': 'playing',
                    'startedAt': datetime.utcnow()
                }
            }
        )
        
        if update_result.modified_count:
            # Create game engine
            game_engine = GameEngine(room_id, len(room['players']))
            active_games[room_id] = game_engine
            
            return jsonify({'message': 'Game started successfully'})
        else:
            return jsonify({'error': 'Failed to start game'}), 500
        
    except Exception as e:
        logger.error(f'Start game error: {e}')
        return jsonify({'error': 'Failed to start game'}), 500

# POST /api/rooms/<room_id>/ready - Toggle player ready status
@rooms_bp.route('/<room_id>/ready', methods=['POST'])
def toggle_ready(room_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        is_ready = data.get('is_ready', True)
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        # Update player ready status
        get_rooms_collection().update_one(
            {
                '_id': ObjectId(room_id),
                'players.user_id': ObjectId(player_id)
            },
            {
                '$set': {'players.$.isReady': is_ready}
            }
        )
        
        return jsonify({'message': f'Player ready status updated to {is_ready}'})
        
    except Exception as e:
        logger.error(f'Toggle ready error: {e}')
        return jsonify({'error': 'Failed to update ready status'}), 500

# POST /api/rooms/<room_id>/score - Update player score for a round
@rooms_bp.route('/<room_id>/score', methods=['POST'])
def update_score(room_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        round_lost = data.get('round_lost', 0)
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        room = get_rooms_collection().find_one({'_id': ObjectId(room_id)})
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Find and update player
        for i, player in enumerate(room['players']):
            if str(player['user_id']) == player_id:
                # Update score
                new_total_lost = player['totalLost'] + round_lost
                new_remaining = room['max_score'] - new_total_lost
                is_out = new_total_lost >= room['max_score']
                
                # Add to score history
                score_entry = {
                    'round': room['currentRound'],
                    'lost': round_lost
                }
                
                # Update player in database
                get_rooms_collection().update_one(
                    {
                        '_id': ObjectId(room_id),
                        'players.user_id': ObjectId(player_id)
                    },
                    {
                        '$set': {
                            'players.$.totalLost': new_total_lost,
                            'players.$.remaining': new_remaining,
                            'players.$.thisRoundLost': round_lost,
                            'players.$.isOut': is_out
                        },
                        '$push': {
                            'players.$.scoreHistory': score_entry
                        }
                    }
                )
                
                return jsonify({
                    'message': 'Score updated successfully',
                    'player': {
                        'username': player['username'],
                        'totalLost': new_total_lost,
                        'remaining': new_remaining,
                        'isOut': is_out
                    }
                })
        
        return jsonify({'error': 'Player not found in room'}), 404
        
    except Exception as e:
        logger.error(f'Update score error: {e}')
        return jsonify({'error': 'Failed to update score'}), 500

# POST /api/rooms/<room_id>/next-round - Move to next round
@rooms_bp.route('/<room_id>/next-round', methods=['POST'])
def next_round(room_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        room = get_rooms_collection().find_one({'_id': ObjectId(room_id)})
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Check if player is host
        is_host = False
        for player in room['players']:
            if str(player['user_id']) == player_id and player['isHost']:
                is_host = True
                break
        
        if not is_host:
            return jsonify({'error': 'Only host can advance to next round'}), 403
        
        # Check if game should end (only 1 player not out)
        active_players = [p for p in room['players'] if not p['isOut']]
        if len(active_players) <= 1:
            # Game finished
            get_rooms_collection().update_one(
                {'_id': ObjectId(room_id)},
                {
                    '$set': {
                        'status': 'finished',
                        'finishedAt': datetime.utcnow()
                    }
                }
            )
            winner = active_players[0]['username'] if active_players else 'No winner'
            return jsonify({
                'message': 'Game finished',
                'winner': winner,
                'gameFinished': True
            })
        
        # Move to next round
        new_round = room['currentRound'] + 1
        get_rooms_collection().update_one(
            {'_id': ObjectId(room_id)},
            {
                '$set': {
                    'currentRound': new_round
                },
                '$unset': {
                    'players.$[].thisRoundLost': ''  # Reset thisRoundLost for all players
                }
            }
        )
        
        return jsonify({
            'message': f'Advanced to round {new_round}',
            'currentRound': new_round,
            'gameFinished': False
        })
        
    except Exception as e:
        logger.error(f'Next round error: {e}')
        return jsonify({'error': 'Failed to advance round'}), 500

# GET /api/rooms/active - Get active rooms
@rooms_bp.route('/active', methods=['GET'])
def get_active_rooms():
    """Get list of active rooms"""
    try:
        rooms_collection = get_rooms_collection()
        
        # Find active rooms that are waiting and not full
        rooms = list(rooms_collection.find({
            'status': 'waiting',
            '$expr': {'$lt': [{'$size': '$players'}, '$maxPlayers']}
        }).sort('createdAt', -1))
        
        active_rooms = []
        for room in rooms:
            active_rooms.append({
                'id': str(room['_id']),
                'roomCode': room['roomCode'],
                'roomName': room['roomName'],
                'host': room['host'],
                'currentPlayers': len(room['players']),
                'maxPlayers': room['maxPlayers'],
                'maxScore': room['max_score'],
                'jokerCount': room['jokerCount'],
                'createdAt': room['createdAt'].isoformat()
            })
        
        return jsonify({'rooms': active_rooms}), 200
        
    except Exception as e:
        logger.error(f'Active rooms error: {e}')
        return jsonify({'error': 'Internal server error'}), 500

@rooms_bp.route('/<room_id>/action', methods=['POST'])
def game_action(room_id):
    """Execute a game action"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['player_id', 'action']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        if room_id not in active_games:
            return jsonify({'error': 'Game not found'}), 404
        
        game_engine = active_games[room_id]
        
        # Execute the action
        from app.game.game_engine import GameAction
        try:
            action = GameAction(data['action'])
        except ValueError:
            return jsonify({'error': 'Invalid action'}), 400
        
        result = game_engine.execute_action(
            data['player_id'], 
            action, 
            data.get('data', {})
        )
        
        if result['success']:
            # Return updated game state
            return jsonify({
                'message': 'Action executed successfully',
                'result': result,
                'game_state': game_engine.get_game_state(data['player_id'])
            }), 200
        else:
            return jsonify({'error': result['error']}), 400
        
    except Exception as e:
        logger.error(f'Game action error: {e}')
        return jsonify({'error': 'Internal server error'}), 500