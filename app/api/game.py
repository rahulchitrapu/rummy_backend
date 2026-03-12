from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import random
from app.database.mongo import get_games_collection, get_rooms_collection
import logging

logger = logging.getLogger(__name__)
game_bp = Blueprint('game', __name__)

class GameManager:
    """Manages game state and operations"""
    
    @staticmethod
    def create_deck():
        """Create a standard 52-card deck plus jokers"""
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        deck = []
        for suit in suits:
            for rank in ranks:
                deck.append({'rank': rank, 'suit': suit})
        
        # Add printed jokers (2 per deck)
        deck.append({'rank': 'JOKER', 'suit': None})
        deck.append({'rank': 'JOKER', 'suit': None})
        
        return deck
    
    @staticmethod
    def shuffle_deck(deck):
        """Shuffle the deck"""
        random.shuffle(deck)
        return deck
    
    @staticmethod
    def select_jokers(deck, joker_count):
        """Select wild cards for this game"""
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        return random.sample(ranks, min(joker_count, len(ranks)))
    
    @staticmethod
    def deal_cards(deck, num_players):
        """Deal 13 cards to each player"""
        hands = [[] for _ in range(num_players)]
        
        # Deal 13 cards to each player
        for i in range(13 * num_players):
            player_index = i % num_players
            hands[player_index].append(deck.pop())
        
        return hands, deck
    
    @staticmethod
    def calculate_hand_points(hand, jokers):
        """Calculate points in a hand"""
        points = 0
        for card in hand:
            if card['rank'] == 'JOKER' or card['rank'] in jokers:
                points += 0  # Jokers are worth 0 points
            elif card['rank'] in ['A', 'J', 'Q', 'K']:
                points += 10
            else:
                points += int(card['rank'])
        return points

# GET /api/games/<game_id> - Get game state
@game_bp.route('/<game_id>', methods=['GET'])
def get_game(game_id):
    try:
        player_id = request.args.get('player_id')
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        game = get_games_collection().find_one({'_id': ObjectId(game_id)})
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        
        # Find the requesting player
        requesting_player = None
        for player in game['players']:
            if player.get('user_id') and str(player['user_id']) == player_id:
                requesting_player = player
                break
        
        if not requesting_player:
            return jsonify({'error': 'Player not in game'}), 403
        
        # Prepare game state for this player
        game_state = {
            'id': str(game['_id']),
            'roomId': str(game['roomId']),
            'roundNumber': game['roundNumber'],
            'status': game['status'],
            'jokers': game['jokers'],
            'currentPlayerIndex': game['currentPlayerIndex'],
            'turnStartTime': game['turnStartTime'].isoformat() if game['turnStartTime'] else None,
            'lastAction': game['lastAction'],
            'discardPile': game['discardPile'],  # Show all discarded cards
            'drawPileCount': game['drawPileCount'],
            'winner': game.get('winner'),
            'losers': game.get('losers', [])
        }
        
        # Add player information
        players = []
        for i, player in enumerate(game['players']):
            player_info = {
                'username': player['username'],
                'laidSets': player['laidSets'],
                'mustDraw': player['mustDraw'],
                'hasDrawn': player['hasDrawn'],
                'hasDiscarded': player['hasDiscarded'],
                'hasDeclared': player['hasDeclared'],
                'thisRoundLost': player.get('thisRoundLost', 0),
                'handCount': len(player.get('hand', []))
            }
            
            # Only show hand to the requesting player
            if player['username'] == requesting_player['username']:
                player_info['hand'] = player.get('hand', [])
                player_info['isMe'] = True
            else:
                player_info['isMe'] = False
            
            players.append(player_info)
        
        game_state['players'] = players
        
        return jsonify({'game': game_state})
        
    except Exception as e:
        logger.error(f'Get game error: {e}')
        return jsonify({'error': 'Failed to get game'}), 500

# POST /api/games/<game_id>/draw - Draw a card
@game_bp.route('/<game_id>/draw', methods=['POST'])
def draw_card(game_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        source = data.get('source', 'deck')  # 'deck' or 'discard'
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        game = get_games_collection().find_one({'_id': ObjectId(game_id)})
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        
        # Find player
        player_index = None
        for i, player in enumerate(game['players']):
            if player.get('user_id') and str(player['user_id']) == player_id:
                player_index = i
                break
        
        if player_index is None:
            return jsonify({'error': 'Player not in game'}), 403
        
        current_player = game['players'][player_index]
        
        # Validate turn
        if not current_player['mustDraw']:
            return jsonify({'error': 'Not your turn to draw'}), 400
        
        if current_player['hasDrawn']:
            return jsonify({'error': 'Already drawn this turn'}), 400
        
        # Draw card
        drawn_card = None
        update_ops = {}
        
        if source == 'discard' and game['discardPile']:
            # Take top card from discard pile (index 0)
            drawn_card = game['discardPile'][0]
            update_ops['$pop'] = {'discardPile': -1}  # Remove first element
        elif source == 'deck' and game['drawPileCount'] > 0:
            # Draw from deck (we'll generate a random card for now)
            # In a real implementation, you'd maintain the actual deck
            deck = GameManager.create_deck()
            GameManager.shuffle_deck(deck)
            drawn_card = deck[0]
            update_ops['$inc'] = {'drawPileCount': -1}
        else:
            return jsonify({'error': 'No cards available to draw'}), 400
        
        # Add card to player's hand
        update_ops['$push'] = {f'players.{player_index}.hand': drawn_card}
        update_ops['$set'] = {
            f'players.{player_index}.hasDrawn': True,
            f'players.{player_index}.mustDraw': False,
            'lastAction': 'draw',
            'turnStartTime': datetime.utcnow()
        }
        
        # Update game
        get_games_collection().update_one(
            {'_id': ObjectId(game_id)},
            update_ops
        )
        
        return jsonify({
            'message': 'Card drawn successfully',
            'card': drawn_card,
            'source': source
        })
        
    except Exception as e:
        logger.error(f'Draw card error: {e}')
        return jsonify({'error': 'Failed to draw card'}), 500

# POST /api/games/<game_id>/discard - Discard a card
@game_bp.route('/<game_id>/discard', methods=['POST'])
def discard_card(game_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        card = data.get('card')  # {'rank': 'A', 'suit': 'hearts'}
        
        if not player_id or not card:
            return jsonify({'error': 'player_id and card required'}), 400
        
        game = get_games_collection().find_one({'_id': ObjectId(game_id)})
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        
        # Find player
        player_index = None
        for i, player in enumerate(game['players']):
            if player.get('user_id') and str(player['user_id']) == player_id:
                player_index = i
                break
        
        if player_index is None:
            return jsonify({'error': 'Player not in game'}), 403
        
        current_player = game['players'][player_index]
        
        # Validate turn
        if not current_player['hasDrawn']:
            return jsonify({'error': 'Must draw before discarding'}), 400
        
        if current_player['hasDiscarded']:
            return jsonify({'error': 'Already discarded this turn'}), 400
        
        # Check if player has the card
        player_hand = current_player.get('hand', [])
        card_found = False
        for i, hand_card in enumerate(player_hand):
            if hand_card['rank'] == card['rank'] and hand_card['suit'] == card['suit']:
                card_found = True
                break
        
        if not card_found:
            return jsonify({'error': 'Card not in hand'}), 400
        
        # Find next player
        next_player_index = (player_index + 1) % len(game['players'])
        
        # Update game
        update_ops = {
            '$pull': {f'players.{player_index}.hand': card},
            '$push': {'discardPile': {'$each': [card], '$position': 0}},  # Add to front
            '$set': {
                f'players.{player_index}.hasDiscarded': True,
                f'players.{next_player_index}.mustDraw': True,
                f'players.{next_player_index}.hasDrawn': False,
                f'players.{next_player_index}.hasDiscarded': False,
                'currentPlayerIndex': next_player_index,
                'lastAction': 'discard',
                'turnStartTime': datetime.utcnow()
            }
        }
        
        get_games_collection().update_one(
            {'_id': ObjectId(game_id)},
            update_ops
        )
        
        return jsonify({'message': 'Card discarded successfully'})
        
    except Exception as e:
        logger.error(f'Discard card error: {e}')
        return jsonify({'error': 'Failed to discard card'}), 500

# POST /api/games/<game_id>/lay-set - Lay down a set
@game_bp.route('/<game_id>/lay-set', methods=['POST'])
def lay_set(game_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        cards = data.get('cards')  # Array of cards
        set_index = data.get('set_index')  # Which set slot (0-4)
        
        if not player_id or not cards or set_index is None:
            return jsonify({'error': 'player_id, cards, and set_index required'}), 400
        
        if set_index < 0 or set_index > 4:
            return jsonify({'error': 'set_index must be between 0 and 4'}), 400
        
        game = get_games_collection().find_one({'_id': ObjectId(game_id)})
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        
        # Find player
        player_index = None
        for i, player in enumerate(game['players']):
            if player.get('user_id') and str(player['user_id']) == player_id:
                player_index = i
                break
        
        if player_index is None:
            return jsonify({'error': 'Player not in game'}), 403
        
        current_player = game['players'][player_index]
        player_hand = current_player.get('hand', [])
        
        # Verify player has all cards
        for card in cards:
            card_found = False
            for hand_card in player_hand:
                if hand_card['rank'] == card['rank'] and hand_card['suit'] == card['suit']:
                    card_found = True
                    break
            if not card_found:
                return jsonify({'error': f'Card {card["rank"]} of {card["suit"]} not in hand'}), 400
        
        # Validate set (basic validation - you can add more complex rules)
        if len(cards) < 3:
            return jsonify({'error': 'Set must have at least 3 cards'}), 400
        
        # Remove cards from hand and add to laid sets
        update_ops = {
            '$set': {f'players.{player_index}.laidSets.{set_index}': cards},
            'lastAction': 'lay_set'
        }
        
        # Remove cards from hand
        for card in cards:
            update_ops.setdefault('$pull', {})
            update_ops['$pull'][f'players.{player_index}.hand'] = card
        
        get_games_collection().update_one(
            {'_id': ObjectId(game_id)},
            update_ops
        )
        
        return jsonify({'message': 'Set laid successfully'})
        
    except Exception as e:
        logger.error(f'Lay set error: {e}')
        return jsonify({'error': 'Failed to lay set'}), 500

# POST /api/games/<game_id>/declare - Declare (finish round)
@game_bp.route('/<game_id>/declare', methods=['POST'])
def declare(game_id):
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        
        if not player_id:
            return jsonify({'error': 'player_id required'}), 400
        
        game = get_games_collection().find_one({'_id': ObjectId(game_id)})
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        
        # Find player
        player_index = None
        for i, player in enumerate(game['players']):
            if player.get('user_id') and str(player['user_id']) == player_id:
                player_index = i
                break
        
        if player_index is None:
            return jsonify({'error': 'Player not in game'}), 403
        
        current_player = game['players'][player_index]
        
        # Validate declaration (player should have valid sets and minimal hand)
        remaining_cards = len(current_player.get('hand', []))
        if remaining_cards > 1:  # Should have at most 1 card left
            return jsonify({'error': 'Must have at most 1 card in hand to declare'}), 400
        
        # Calculate points for all players
        losers = []
        for player in game['players']:
            if player['username'] != current_player['username']:
                hand_points = GameManager.calculate_hand_points(
                    player.get('hand', []), 
                    game['jokers']
                )
                losers.append({
                    'username': player['username'],
                    'points': hand_points
                })
        
        # Update game status
        update_ops = {
            '$set': {
                f'players.{player_index}.hasDeclared': True,
                'status': 'finished',
                'winner': current_player['username'],
                'losers': losers,
                'finishedAt': datetime.utcnow(),
                'lastAction': 'declare'
            }
        }
        
        # Update each player's points
        for i, player in enumerate(game['players']):
            if player['username'] != current_player['username']:
                hand_points = GameManager.calculate_hand_points(
                    player.get('hand', []), 
                    game['jokers']
                )
                update_ops['$set'][f'players.{i}.thisRoundLost'] = hand_points
            else:
                update_ops['$set'][f'players.{i}.thisRoundLost'] = 0
        
        get_games_collection().update_one(
            {'_id': ObjectId(game_id)},
            update_ops
        )
        
        # Update room scores
        room = get_rooms_collection().find_one({'_id': ObjectId(game['roomId'])})
        if room:
            for loser in losers:
                # Find player in room and update scores
                for i, room_player in enumerate(room['players']):
                    if room_player['username'] == loser['username']:
                        new_total = room_player['totalLost'] + loser['points']
                        new_remaining = room['max_score'] - new_total
                        is_out = new_total >= room['max_score']
                        
                        get_rooms_collection().update_one(
                            {
                                '_id': ObjectId(game['roomId']),
                                'players.username': loser['username']
                            },
                            {
                                '$set': {
                                    'players.$.totalLost': new_total,
                                    'players.$.remaining': new_remaining,
                                    'players.$.thisRoundLost': loser['points'],
                                    'players.$.isOut': is_out
                                },
                                '$push': {
                                    'players.$.scoreHistory': {
                                        'round': room['currentRound'],
                                        'lost': loser['points']
                                    }
                                }
                            }
                        )
        
        return jsonify({
            'message': 'Round finished',
            'winner': current_player['username'],
            'losers': losers
        })
        
    except Exception as e:
        logger.error(f'Declare error: {e}')
        return jsonify({'error': 'Failed to declare'}), 500

# POST /api/games/ - Create new game
@game_bp.route('/', methods=['POST'])
def create_game(room_id):
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        
        if not room_id:
            return jsonify({'error': 'room_id required'}), 400
        
        # Get room details
        room = get_rooms_collection().find_one({'_id': ObjectId(room_id)})
        if not room:
            return jsonify({'error': 'Room not found'}), 404
        
        # Create deck and deal cards
        deck = GameManager.create_deck()
        GameManager.shuffle_deck(deck)
        
        # Select jokers
        jokers = GameManager.select_jokers(deck, room['jokerCount'])
        
        # Deal cards to players
        num_players = len(room['players'])
        hands, remaining_deck = GameManager.deal_cards(deck, num_players)
        
        # Create game players
        game_players = []
        for i, room_player in enumerate(room['players']):
            game_players.append({
                'username': room_player['username'],
                'user_id': room_player['user_id'],
                'hand': hands[i],
                'laidSets': [[], [], [], [], []],  # 5 empty sets
                'mustDraw': i == 0,  # First player starts
                'hasDrawn': False,
                'hasDiscarded': False,
                'hasDeclared': False,
                'thisRoundLost': 0
            })
        
        # Create first discard card
        discard_pile = [remaining_deck.pop()]
        
        game_doc = {
            'roomId': ObjectId(room_id),
            'roundNumber': room['currentRound'],
            'status': 'playing',
            'players': game_players,
            'discardPile': discard_pile,
            'drawPileCount': len(remaining_deck),
            'jokers': jokers,
            'currentPlayerIndex': 0,
            'turnStartTime': datetime.utcnow(),
            'lastAction': 'deal',
            'winner': None,
            'losers': [],
            'createdAt': datetime.utcnow(),
            'finishedAt': None
        }
        
        result = get_games_collection().insert_one(game_doc)
        
        # Update room with current game
        get_rooms_collection().update_one(
            {'_id': ObjectId(room_id)},
            {
                '$set': {'currentGameId': result.inserted_id},
                '$push': {'gameHistory': result.inserted_id}
            }
        )
        
        return jsonify({
            'game': {
                'id': str(result.inserted_id),
                'status': 'playing',
                'roundNumber': room['currentRound']
            }
        }), 201
        
    except Exception as e:
        logger.error(f'Create game error: {e}')
        return jsonify({'error': 'Failed to create game'}), 500
