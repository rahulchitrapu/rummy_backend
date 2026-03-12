import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    MONGO_URI = os.environ.get('MONGO_URI') or ''
    DEBUG = os.environ.get('FLASK_ENV') == 'development'

    SUPABASE_URL = os.environ.get('SUPABASE_URL') or ''
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY') or ''
    
    # Game settings
    MAX_PLAYERS_PER_ROOM = 4
    MIN_PLAYERS_PER_ROOM = 2
    ROOM_TIMEOUT = 300  # 5 minutes in seconds
    
    # JWT settings
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24 hours