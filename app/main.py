import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_socketio import SocketIO
from app.config import Config
from app.database.mongo import init_db
from app.database.supabase import init_db as init_supabase_db
from app.sockets import events
from app.api.users import users_bp
from app.api.rooms import rooms_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize Socket.IO
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # Initialize database
    init_db(app)
    init_supabase_db(app)
    
    # Register blueprints
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(rooms_bp, url_prefix='/api/rooms')
    
    
    # Register socket events
    events.register_socket_events(socketio)
    
    return app, socketio

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)