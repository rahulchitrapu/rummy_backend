from pymongo import MongoClient
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    client = None
    db = None

def init_db(app):
    """Initialize MongoDB connection"""
    try:
        MongoDB.client = MongoClient(app.config['MONGO_URI'])

        
        # Extract database name from URI or use default
        uri = app.config['MONGO_URI']
        if '/' in uri and uri.split('/')[-1] and '?' not in uri.split('/')[-1]:
            db_name = uri.split('/')[-1].split('?')[0]
        else:
            db_name = 'game_db'
        
        MongoDB.db = MongoDB.client[db_name]
        
        # Test connection
        MongoDB.client.admin.command('ping')
        logger.info(f'Successfully connected to MongoDB Atlas: {db_name}')
        print(f'Successfully connected to MongoDB Atlas: {db_name}')
        
        # Create indexes for existing collections
        create_indexes()
        
    except Exception as e:
        logger.error(f'Failed to connect to MongoDB: {e}')
        raise

def create_indexes():
    """Create necessary database indexes"""
    try:
        # Users collection indexes
        MongoDB.db.users.create_index('username', unique=True)
        MongoDB.db.users.create_index('email', unique=True)
        
        # Rooms collection indexes
        MongoDB.db.rooms.create_index('room_code', unique=True)
        MongoDB.db.rooms.create_index('created_at')
        
        # Games collection indexes
        MongoDB.db.games.create_index('room_id')
        MongoDB.db.games.create_index('players')
        MongoDB.db.games.create_index('status')
        
        logger.info('Database indexes created successfully')
        
    except Exception as e:
        logger.error(f'Error creating database indexes: {e}')

def get_db():
    """Get database instance"""
    return MongoDB.db

def get_collection(collection_name):
    """Get specific collection"""
    return MongoDB.db[collection_name]

# Collection helper functions
def get_users_collection():
    """Get users collection from game_db"""
    return get_collection('users')

def get_rooms_collection():
    """Get rooms collection from game_db"""
    return get_collection('rooms')

def get_games_collection():
    """Get games collection from game_db"""
    return get_collection('games')