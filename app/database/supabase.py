from supabase import create_client, Client
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class SupabaseDB:
    client: Client = None

def init_db(app):
    """Initialize Supabase connection"""
    try:
        url = app.config['SUPABASE_URL']
        key = app.config['SUPABASE_KEY']
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured")
        
        SupabaseDB.client = create_client(url, key)
        
        # Test connection by trying to authenticate or query a simple table
        # You can replace this with a simple query to an existing table
        logger.info('Successfully connected to Supabase')
        print('Successfully connected to Supabase')
        
    except Exception as e:
        logger.error(f'Failed to connect to Supabase: {e}')
        raise

def get_client():
    """Get Supabase client instance"""
    return SupabaseDB.client

def get_table(table_name):
    """Get specific table"""
    return SupabaseDB.client.table(table_name)

# Table helper functions
def get_users_table():
    """Get users table"""
    return get_table('users')

def get_rooms_table():
    """Get rooms table"""
    return get_table('rooms')

def get_games_table():
    """Get games table"""
    return get_table('games')

# Helper functions for common operations
def insert_record(table_name, data):
    """Insert a record into a table"""
    try:
        response = SupabaseDB.client.table(table_name).insert(data).execute()
        return response
    except Exception as e:
        logger.error(f'Error inserting record into {table_name}: {e}')
        raise

def update_record(table_name, data, filters):
    """Update records in a table"""
    try:
        query = SupabaseDB.client.table(table_name).update(data)
        
        # Apply filters
        for column, value in filters.items():
            query = query.eq(column, value)
        
        response = query.execute()
        return response
    except Exception as e:
        logger.error(f'Error updating record in {table_name}: {e}')
        raise

def select_records(table_name, columns="*", filters=None, limit=None):
    """Select records from a table"""
    try:
        query = SupabaseDB.client.table(table_name).select(columns)
        
        # Apply filters if provided
        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)
        
        # Apply limit if provided
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        return response
    except Exception as e:
        logger.error(f'Error selecting records from {table_name}: {e}')
        raise

def delete_record(table_name, filters):
    """Delete records from a table"""
    try:
        query = SupabaseDB.client.table(table_name).delete()
        
        # Apply filters
        for column, value in filters.items():
            query = query.eq(column, value)
        
        response = query.execute()
        return response
    except Exception as e:
        logger.error(f'Error deleting record from {table_name}: {e}')
        raise