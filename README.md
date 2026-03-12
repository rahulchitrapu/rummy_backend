# Rummy Backend

A real-time multiplayer Rummy card game backend built with Flask and Socket.IO.

## Features

- Real-time multiplayer gameplay using WebSockets
- User authentication and registration
- Room-based game management
- Complete Rummy game engine
- RESTful API for user and room management
- MongoDB database integration
- Leaderboard and statistics tracking

## Project Structure

```
rummy_backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration settings
│   ├── api/
│   │   ├── users.py         # User management API
│   │   └── rooms.py         # Room management API
│   ├── database/
│   │   └── mongo.py         # MongoDB connection and utilities
│   ├── game/
│   │   ├── game_engine.py   # Core game logic
│   │   └── deck.py          # Card and deck implementation
│   └── sockets/
│       ├── __init__.py
│       └── events.py        # Socket.IO event handlers
├── venv/                    # Virtual environment
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables
├── environment.sh           # Environment setup script
└── README.md
```

## Setup

1. **Activate virtual environment:**

   ```bash
   source environment.sh
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up MongoDB:**

   - Install and start MongoDB
   - Update MONGO_URI in .env file if needed

4. **Configure environment variables:**
   - Copy .env file and update values as needed
   - Set SECRET_KEY and JWT_SECRET_KEY for production

## Running the Application

```bash
# Using Flask development server
flask run

# Or run directly with Python
python -m app.main

# Or with Socket.IO support
python app/main.py
```

The application will start on `http://localhost:5000`

## API Endpoints

### Users

- `POST /api/users/register` - Register new user
- `POST /api/users/login` - User login
- `GET /api/users/profile/<user_id>` - Get user profile
- `PUT /api/users/profile/<user_id>` - Update user profile
- `GET /api/users/leaderboard` - Get leaderboard

### Rooms

- `POST /api/rooms/create` - Create new room
- `POST /api/rooms/join` - Join existing room
- `POST /api/rooms/leave` - Leave room
- `POST /api/rooms/<room_id>/start` - Start game
- `GET /api/rooms/<room_id>/status` - Get room status
- `GET /api/rooms/active` - Get active rooms
- `POST /api/rooms/<room_id>/action` - Execute game action

## Socket.IO Events

### Client to Server

- `connect` - Client connection
- `join_game_room` - Join game room
- `leave_game_room` - Leave game room
- `game_action` - Perform game action
- `send_message` - Send chat message

### Server to Client

- `connected` - Connection confirmation
- `joined_room` - Room join confirmation
- `left_room` - Room leave confirmation
- `player_joined` - Another player joined
- `player_left` - Player left room
- `game_update` - Game state update
- `new_message` - New chat message

## Game Rules

This implementation follows standard Rummy rules:

- 13 cards per player
- Form sets (same rank) and runs (consecutive cards of same suit)
- Draw from deck or discard pile
- Discard one card per turn
- Declare when you have valid melds

## Development

- The application uses Flask-SocketIO for real-time communication
- MongoDB is used for data persistence
- JWT tokens for authentication
- Game state is managed in-memory (consider Redis for production)

## Production Considerations

- Use Redis for session storage and game state
- Set up proper MongoDB cluster
- Use environment variables for all sensitive data
- Set up proper logging
- Use a production WSGI server like Gunicorn
- Implement rate limiting and security measures
