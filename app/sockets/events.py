from flask_socketio import emit, join_room, leave_room, disconnect
from flask import request
import logging

logger = logging.getLogger(__name__)

def register_socket_events(socketio):
    @socketio.on('connect')
    def handle_connect():
        logger.info(f'Client connected: {request.sid}')
        emit('connected', {'message': 'Successfully connected to the server'})

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info(f'Client disconnected: {request.sid}')

    @socketio.on('join_game_room')
    def handle_join_game_room(data):
        room_id = data.get('room_id')
        player_id = data.get('player_id')
        
        if not room_id or not player_id:
            emit('error', {'message': 'Missing room_id or player_id'})
            return
        
        join_room(room_id)
        logger.info(f'Player {player_id} joined room {room_id}')
        
        emit('joined_room', {
            'room_id': room_id,
            'player_id': player_id,
            'message': f'Successfully joined room {room_id}'
        })
        
        # Notify other players in the room
        emit('player_joined', {
            'player_id': player_id,
            'message': f'Player {player_id} joined the game'
        }, room=room_id, include_self=False)

    @socketio.on('leave_game_room')
    def handle_leave_game_room(data):
        room_id = data.get('room_id')
        player_id = data.get('player_id')
        
        if not room_id or not player_id:
            emit('error', {'message': 'Missing room_id or player_id'})
            return
        
        leave_room(room_id)
        logger.info(f'Player {player_id} left room {room_id}')
        
        emit('left_room', {
            'room_id': room_id,
            'player_id': player_id,
            'message': f'Successfully left room {room_id}'
        })
        
        # Notify other players in the room
        emit('player_left', {
            'player_id': player_id,
            'message': f'Player {player_id} left the game'
        }, room=room_id)

    @socketio.on('game_action')
    def handle_game_action(data):
        room_id = data.get('room_id')
        player_id = data.get('player_id')
        action = data.get('action')
        action_data = data.get('data', {})
        
        if not all([room_id, player_id, action]):
            emit('error', {'message': 'Missing required game action data'})
            return
        
        logger.info(f'Game action: {action} by player {player_id} in room {room_id}')
        
        # TODO: Implement game logic integration
        # For now, just broadcast the action to all players in the room
        emit('game_update', {
            'player_id': player_id,
            'action': action,
            'data': action_data
        }, room=room_id)

    @socketio.on('send_message')
    def handle_send_message(data):
        room_id = data.get('room_id')
        player_id = data.get('player_id')
        message = data.get('message')
        
        if not all([room_id, player_id, message]):
            emit('error', {'message': 'Missing message data'})
            return
        
        # Broadcast message to all players in the room
        emit('new_message', {
            'player_id': player_id,
            'message': message,
            'timestamp': data.get('timestamp')
        }, room=room_id)