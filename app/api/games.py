from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.database.supabase_connection import get_rooms_table, get_table, update_record
from app.api.game import (
    deal_round,
    calculate_score_from_sets,
    is_valid_set,
    load_game,
    save_game,
    find_player,
    find_card_index
)

logger = logging.getLogger(__name__)
games_bp = Blueprint('games', __name__)


# POST /api/games/start - Start game for a room
@games_bp.route('/start', methods=['POST'])
def start_game():
    try:
        data = request.get_json()
        room_id = data.get('room_id')

        if not room_id:
            return jsonify({'error': 'room_id required'}), 400

        rooms = get_rooms_table(
            columns="id, room_code, status, max_players, created_by, current_round, game_started",
            filters={"id": room_id}
        )

        if not rooms:
            return jsonify({'error': 'Room not found'}), 404

        room = rooms[0]

        if room['status'] == 'active':
            return jsonify({'message': 'Game already started for this room', 'room': room}), 200

        room_players = get_table(
            "room_players",
            columns="user_id, joined_at",
            filters={"room_id": room_id}
        )

        if len(room_players) < 2:
            return jsonify({'error': 'At least 2 players are required to start the game'}), 400

        player_ids = [rp['user_id'] for rp in sorted(room_players, key=lambda rp: rp['joined_at'])]

        current_round = room.get('current_round') or 1
        round_data = deal_round(current_round, player_ids)

        save_game(room_id, {'rounds': [round_data]})

        update_record('rooms', {'status': 'active', 'game_started': True}, {'id': room_id})

        room['status'] = 'active'
        room['game_started'] = True

        return jsonify({'message': 'Game started successfully', 'room': room})

    except Exception as e:
        logger.error(f'Start game error: {e}')
        return jsonify({'error': 'Failed to start game'}), 500


# GET /api/games/<room_id> - Get game state for a player
@games_bp.route('/<int:room_id>', methods=['GET'])
def get_game(room_id):
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        requesting_player = find_player(round_data, user_id)

        if not requesting_player:
            return jsonify({'error': 'Player not in game'}), 403

        current_turn_user_id = round_data['turn_order'][round_data['current_player_index']]

        response = {
            'round_number': round_data['round_number'],
            'status': round_data['status'],
            'current_turn_user_id': current_turn_user_id,
            'discard_pile': round_data['discard_pile'],
            'draw_pile_count': len(round_data['draw_pile']),
            'winner': round_data.get('winner'),
            'losers': round_data.get('losers', []),
            'pending_declarations': round_data.get('pending_declarations', []),
            'player': {
                'user_id': requesting_player['user_id'],
                'hand': requesting_player['hand'],
                'laid_sets': requesting_player['laid_sets'],
                'must_draw': requesting_player['must_draw'],
                'has_drawn': requesting_player['has_drawn'],
                'has_discarded': requesting_player['has_discarded'],
                'has_declared': requesting_player['has_declared'],
                'has_seen_joker': requesting_player.get('has_seen_joker', False),
                'this_round_lost': requesting_player['this_round_lost']
            }
        }

        if requesting_player.get('has_seen_joker') or round_data['status'] in ('awaiting_scores', 'finished'):
            response['wildcard_joker'] = round_data['wildcard_joker']

        return jsonify(response)

    except Exception as e:
        logger.error(f'Get game error: {e}')
        return jsonify({'error': 'Failed to get game'}), 500


# GET /api/games/<room_id>/results - Cards + scores of everyone who has
# submitted for the current round (the winner, plus anyone who's declared)
@games_bp.route('/<int:room_id>/results', methods=['GET'])
def get_results(room_id):
    try:
        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]

        declared_players = [player for player in round_data['players'] if player['has_declared']]

        total_scores = {}
        if declared_players:
            room_players = get_table(
                "room_players",
                columns="user_id, score",
                filters={"room_id": room_id}
            )
            total_scores = {rp['user_id']: rp.get('score') or 0 for rp in room_players}

        players = [{
            'user_id': player['user_id'],
            'hand': player['hand'],
            'laid_sets': player['laid_sets'],
            'this_round_lost': player['this_round_lost'],
            'is_winner': player['user_id'] == round_data['winner'],
            'total_score': total_scores.get(player['user_id'], 0)
        } for player in declared_players]

        response = {
            'round_number': round_data['round_number'],
            'status': round_data['status'],
            'winner': round_data.get('winner'),
            'pending_declarations': round_data.get('pending_declarations', []),
            'players': players
        }

        # A winner having declared is what got us here at all - nothing left to hide
        if round_data.get('winner') is not None:
            response['wildcard_joker'] = round_data['wildcard_joker']

        return jsonify(response)

    except Exception as e:
        logger.error(f'Get results error: {e}')
        return jsonify({'error': 'Failed to get results'}), 500


# POST /api/games/<room_id>/draw - Draw a card
@games_bp.route('/<int:room_id>/draw', methods=['POST'])
def draw_card(room_id):
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        source = data.get('source', 'deck')  # 'deck' or 'discard'

        if not user_id:
            return jsonify({'error': 'user_id required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        player = find_player(round_data, user_id)

        if not player:
            return jsonify({'error': 'Player not in game'}), 403

        if not player['must_draw']:
            return jsonify({'error': 'Not your turn to draw'}), 400

        if player['has_drawn']:
            return jsonify({'error': 'Already drawn this turn'}), 400

        if source == 'discard':
            if not round_data['discard_pile']:
                return jsonify({'error': 'No cards available to draw'}), 400
            drawn_card = round_data['discard_pile'].pop(0)
        elif source == 'deck':
            if not round_data['draw_pile']:
                return jsonify({'error': 'No cards available to draw'}), 400
            drawn_card = round_data['draw_pile'].pop()
        else:
            return jsonify({'error': "source must be 'deck' or 'discard'"}), 400

        player['hand'].append(drawn_card)
        player['has_drawn'] = True
        player['must_draw'] = False
        round_data['last_action'] = 'draw'

        save_game(room_id, game_state)

        return jsonify({
            'message': 'Card drawn successfully',
            'card': drawn_card,
            'source': source
        })

    except Exception as e:
        logger.error(f'Draw card error: {e}')
        return jsonify({'error': 'Failed to draw card'}), 500


# POST /api/games/<room_id>/discard - Discard a card
@games_bp.route('/<int:room_id>/discard', methods=['POST'])
def discard_card(room_id):
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        card = data.get('card')  # {'rank': 'A', 'suit': 'hearts'}

        if not user_id or not card:
            return jsonify({'error': 'user_id and card required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        player = find_player(round_data, user_id)

        if not player:
            return jsonify({'error': 'Player not in game'}), 403

        if not player['has_drawn']:
            return jsonify({'error': 'Must draw before discarding'}), 400

        if player['has_discarded']:
            return jsonify({'error': 'Already discarded this turn'}), 400

        card_index = find_card_index(player['hand'], card)
        if card_index is not None:
            discarded_card = player['hand'].pop(card_index)
        else:
            discarded_card = None
            for group in player['laid_sets']:
                group_index = find_card_index(group, card)
                if group_index is not None:
                    discarded_card = group.pop(group_index)
                    break

            if discarded_card is None:
                return jsonify({'error': 'Card not in hand'}), 400

        round_data['discard_pile'].insert(0, discarded_card)
        player['has_discarded'] = True

        turn_order = round_data['turn_order']
        current_index = turn_order.index(user_id)
        next_index = (current_index + 1) % len(turn_order)
        next_player = find_player(round_data, turn_order[next_index])
        next_player['must_draw'] = True
        next_player['has_drawn'] = False
        next_player['has_discarded'] = False

        round_data['current_player_index'] = next_index
        round_data['last_action'] = 'discard'

        save_game(room_id, game_state)

        return jsonify({'message': 'Card discarded successfully'})

    except Exception as e:
        logger.error(f'Discard card error: {e}')
        return jsonify({'error': 'Failed to discard card'}), 500


# POST /api/games/<room_id>/lay-set - Lay down a set
@games_bp.route('/<int:room_id>/lay-set', methods=['POST'])
def lay_set(room_id):
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        sets = data.get('sets')  # Array of groups, e.g. [[card, card], [card], []]

        if not user_id or sets is None:
            return jsonify({'error': 'user_id and sets required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        player = find_player(round_data, user_id)

        if not player:
            return jsonify({'error': 'Player not in game'}), 403

        # Cards the player currently holds: their hand + whatever they'd already grouped
        available_cards = list(player['hand']) + [
            card for group in player['laid_sets'] for card in group
        ]

        for group in sets:
            for card in group:
                card_index = find_card_index(available_cards, card)
                if card_index is None:
                    return jsonify({'error': f'Card {card["rank"]} of {card.get("suit")} not in hand'}), 400
                available_cards.pop(card_index)

        # Whatever wasn't placed into a set stays in hand
        player['hand'] = available_cards
        player['laid_sets'] = sets
        round_data['last_action'] = 'lay_set'

        save_game(room_id, game_state)

        return jsonify({'message': 'Sets stored successfully', 'laid_sets': sets, 'hand': player['hand']})

    except Exception as e:
        logger.error(f'Lay set error: {e}')
        return jsonify({'error': 'Failed to lay set'}), 500


# POST /api/games/<room_id>/show-joker - Reveal the round's wildcard joker
# to a player who has a genuine 4-of-a-kind set
@games_bp.route('/<int:room_id>/show-joker', methods=['POST'])
def show_joker(room_id):
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'user_id required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        player = find_player(round_data, user_id)

        if not player:
            return jsonify({'error': 'Player not in game'}), 403

        # Once a winner has declared (or the round is fully over) there's
        # nothing left to protect - anyone can see it
        if round_data['status'] in ('awaiting_scores', 'finished'):
            return jsonify({
                'message': 'Joker revealed',
                'wildcard_joker': round_data['wildcard_joker']
            })

        card_set = data.get('set')

        if not card_set:
            return jsonify({'error': 'set required'}), 400

        if len(card_set) != 4:
            return jsonify({'error': 'set must have exactly 4 cards'}), 400

        ranks = {card['rank'] for card in card_set}
        if len(ranks) != 1:
            return jsonify({'error': 'All 4 cards in the set must share the same rank'}), 400

        # Pull each of the 4 cards out of wherever it's currently sitting -
        # the loose hand, or an existing laid_sets group
        pulled_cards = []
        for card in card_set:
            card_index = find_card_index(player['hand'], card)
            if card_index is not None:
                pulled_cards.append(player['hand'].pop(card_index))
                continue

            found = False
            for group in player['laid_sets']:
                group_index = find_card_index(group, card)
                if group_index is not None:
                    pulled_cards.append(group.pop(group_index))
                    found = True
                    break

            if not found:
                return jsonify({'error': f'Card {card["rank"]} of {card.get("suit")} not in your hand'}), 400

        player['laid_sets'].append(pulled_cards)
        player['has_seen_joker'] = True
        round_data['last_action'] = 'show_joker'

        save_game(room_id, game_state)

        return jsonify({
            'message': 'Joker revealed',
            'wildcard_joker': round_data['wildcard_joker']
        })

    except Exception as e:
        logger.error(f'Show joker error: {e}')
        return jsonify({'error': 'Failed to show joker'}), 500


# POST /api/games/<room_id>/declare - Declare as winner, or (once a winner
# exists) submit your own final cards so your score can be calculated
@games_bp.route('/<int:room_id>/declare', methods=['POST'])
def declare(room_id):
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'user_id required'}), 400

        game_state = load_game(room_id)
        if not game_state:
            return jsonify({'error': 'Game not found'}), 404

        round_data = game_state['rounds'][-1]
        player = find_player(round_data, user_id)

        if not player:
            return jsonify({'error': 'Player not in game'}), 403

        if round_data['status'] == 'finished':
            return jsonify({'error': 'Round already finished'}), 400

        # Phase 1: nobody has declared yet - this call claims the win.
        # `card` is the closing card - the one extra card they're discarding
        # to finish. It doesn't need to be part of any set; it's just removed
        # from wherever it is, and everything left over must fully resolve
        # into valid sets with nothing ungrouped.
        if round_data['winner'] is None:
            card = data.get('card')
            if not card:
                return jsonify({'error': 'card required to declare'}), 400

            card_index = find_card_index(player['hand'], card)
            if card_index is not None:
                declared_card = player['hand'].pop(card_index)
            else:
                declared_card = None
                for group in player['laid_sets']:
                    group_index = find_card_index(group, card)
                    if group_index is not None:
                        declared_card = group.pop(group_index)
                        break

                if declared_card is None:
                    return jsonify({'error': f'Card {card["rank"]} of {card.get("suit")} not in your hand'}), 400

            if player['hand']:
                return jsonify({'error': 'All remaining cards must be arranged into valid sets before declaring'}), 400

            wildcard_rank = round_data['wildcard_joker']['rank']
            has_seen_joker = player.get('has_seen_joker', False)
            invalid_groups = [
                group for group in player['laid_sets']
                if group and not is_valid_set(group, wildcard_rank, has_seen_joker)
            ]
            if invalid_groups:
                return jsonify({
                    'error': 'Invalid declaration: every remaining group must be a valid set (3-4 same-rank cards)',
                    'invalid_sets': invalid_groups
                }), 400

            round_data['discard_pile'].insert(0, declared_card)

            player['has_declared'] = True
            player['this_round_lost'] = 0
            round_data['winner'] = user_id
            round_data['status'] = 'awaiting_scores'
            round_data['last_action'] = 'declare'
            round_data['pending_declarations'] = [
                uid for uid in round_data['turn_order'] if uid != user_id
            ]

            save_game(room_id, game_state)

            return jsonify({
                'message': 'Declared as winner. Other players must submit their cards to calculate scores.',
                'winner': user_id,
                'pending_declarations': round_data['pending_declarations']
            })

        # Phase 2: a winner already exists - this player is submitting their
        # final cards (hand + laid_sets) so their score can be calculated
        if user_id == round_data['winner']:
            return jsonify({'error': 'Winner already declared for this round'}), 400

        if player['has_declared']:
            return jsonify({'error': 'You have already submitted your cards for this round'}), 400

        sets = data.get('sets')
        if sets is None:
            return jsonify({'error': 'sets required to submit your cards'}), 400

        pool = list(player['hand']) + [card for group in player['laid_sets'] for card in group]
        flat_sets = [card for group in sets for card in group]

        if len(flat_sets) != len(pool):
            return jsonify({'error': 'sets must include all of your cards, no more and no less'}), 400

        remaining_pool = list(pool)
        for card in flat_sets:
            card_index = find_card_index(remaining_pool, card)
            if card_index is None:
                return jsonify({'error': f'Card {card["rank"]} of {card.get("suit")} not in your hand'}), 400
            remaining_pool.pop(card_index)

        wildcard_rank = round_data['wildcard_joker']['rank']
        has_seen_joker = player.get('has_seen_joker', False)
        points = calculate_score_from_sets(sets, wildcard_rank, has_seen_joker)

        player['laid_sets'] = sets
        player['hand'] = []
        player['has_declared'] = True
        player['this_round_lost'] = points
        round_data['losers'].append({'user_id': user_id, 'points': points})
        round_data['last_action'] = 'declare'

        existing = get_table(
            "room_players",
            columns="id, score",
            filters={"room_id": room_id, "user_id": user_id}
        )
        if existing:
            new_score = (existing[0].get('score') or 0) + points
            update_record('room_players', {'score': new_score}, {'id': existing[0]['id']})

        round_data['pending_declarations'] = [
            p['user_id'] for p in round_data['players']
            if p['user_id'] != round_data['winner'] and not p['has_declared']
        ]
        if not round_data['pending_declarations']:
            round_data['status'] = 'finished'
            round_data['finished_at'] = datetime.utcnow().isoformat()

        save_game(room_id, game_state)

        return jsonify({
            'message': 'Score submitted',
            'user_id': user_id,
            'points': points,
            'round_finished': round_data['status'] == 'finished',
            'pending_declarations': round_data['pending_declarations']
        })

    except Exception as e:
        logger.error(f'Declare error: {e}')
        return jsonify({'error': 'Failed to declare'}), 500
