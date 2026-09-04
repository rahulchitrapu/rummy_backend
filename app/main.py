import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from app.config import Config
from app.database.mongo import init_db
from app.database.supabase_connection import init_db as init_supabase_db
from app.sockets import events
from app.api.users import users_bp
from app.api.rooms import rooms_bp
from app.api.ping import ping_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Enable CORS for all routes
    CORS(app, supports_credentials=True)
    
    # Initialize Socket.IO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")
    
    # Initialize database
    # init_db(app)
    init_supabase_db()
    
    # Register blueprints
    app.register_blueprint(ping_bp, url_prefix='/ping')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(rooms_bp, url_prefix='/api/rooms')
    
    
    # Register socket events
    events.register_socket_events(socketio)
    
    return app, socketio

# Module-level app/socketio so a production WSGI server (gunicorn) can import
# `app.main:app` directly instead of only running via `python app/main.py`.
app, socketio = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    socketio.run(app, debug=debug, host='0.0.0.0', port=port)