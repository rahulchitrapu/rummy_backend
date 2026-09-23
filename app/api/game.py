from datetime import datetime
import json
import os
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAMES_DIR = os.path.join(BASE_DIR, 'games')

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']


DECK_COUNT = 2


def create_deck():
    """Create 2 standard 52-card decks (104 cards) plus just 2 printed jokers total"""
    deck = [
        {'rank': rank, 'suit': suit}
        for _ in range(DECK_COUNT)
        for suit in SUITS
        for rank in RANKS
    ]
    deck.append({'rank': 'JOKER', 'suit': None})
    deck.append({'rank': 'JOKER', 'suit': None})
    return deck


MAX_SETS_PER_PLAYER = 5
MAX_CARDS_PER_SET = 4


def group_hand_by_rank(hand):
    """Group same-rank cards (any suit) into sets of up to 4 cards each.

    This is not standard rummy meld validation (no suit/sequence rules) -
    it just auto-clusters duplicate ranks dealt to a player, e.g. two 8s
    become a set of 8s, three 10s become a set of 10s, and so on. Cards
    without a matching duplicate stay in hand.
    """
    groups = {}
    for card in hand:
        groups.setdefault(card['rank'], []).append(card)

    laid_sets = [[] for _ in range(MAX_SETS_PER_PLAYER)]
    remaining_hand = []
    slot_index = 0

    for cards in groups.values():
        i = 0
        while i < len(cards):
            chunk = cards[i:i + MAX_CARDS_PER_SET]
            i += MAX_CARDS_PER_SET
            if len(chunk) >= 2 and slot_index < MAX_SETS_PER_PLAYER:
                laid_sets[slot_index] = chunk
                slot_index += 1
            else:
                remaining_hand.extend(chunk)

    return remaining_hand, laid_sets


def deal_round(round_number, player_ids):
    """Shuffle a fresh deck, pick a secret wildcard joker, and deal 13 cards to each player"""
    deck = create_deck()
    random.shuffle(deck)

    wildcard_joker = deck.pop()

    hands = {user_id: [] for user_id in player_ids}
    for i in range(13 * len(player_ids)):
        user_id = player_ids[i % len(player_ids)]
        hands[user_id].append(deck.pop())

    discard_pile = [deck.pop()]

    players = []
    for i, user_id in enumerate(player_ids):
        remaining_hand, laid_sets = group_hand_by_rank(hands[user_id])
        players.append({
            'user_id': user_id,
            'hand': remaining_hand,
            'laid_sets': laid_sets,
            'must_draw': i == 0,
            'has_drawn': False,
            'has_discarded': False,
            'has_declared': False,
            'has_seen_joker': False,
            'this_round_lost': 0
        })

    return {
        'round_number': round_number,
        'wildcard_joker': wildcard_joker,
        'players': players,
        'draw_pile': deck,
        'discard_pile': discard_pile,
        'turn_order': player_ids,
        'current_player_index': 0,
        'status': 'in_progress',
        'winner': None,
        'losers': [],
        'pending_declarations': [],
        'last_action': 'deal',
        'started_at': datetime.utcnow().isoformat(),
        'finished_at': None
    }


def is_wildcard_card(card, wildcard_rank):
    """A card is wild if it's a printed JOKER, or its rank matches the round's
    wildcard rank (e.g. wildcard_joker is 'J of clubs' -> every J is wild)."""
    return card['rank'] == 'JOKER' or card['rank'] == wildcard_rank


def card_value(rank):
    if rank in ('A', 'J', 'Q', 'K'):
        return 10
    return int(rank)


def is_valid_set(group, wildcard_rank, has_seen_joker=False):
    """A valid set is 3-4 cards where every non-wild card shares one rank.

    A wildcard can only fill in for a missing card (e.g. 8, 8, wildcard) if
    the player has already shown a genuine 4-of-a-kind this round
    (has_seen_joker) - otherwise a group that relies on a wildcard doesn't
    count as a made set, even if the ranks would otherwise line up.
    """
    if len(group) not in (3, 4):
        return False

    non_wild = [card for card in group if not is_wildcard_card(card, wildcard_rank)]
    has_wildcard = len(non_wild) != len(group)

    if has_wildcard and not has_seen_joker:
        return False

    non_wild_ranks = {card['rank'] for card in non_wild}
    return len(non_wild_ranks) <= 1


def calculate_score_from_sets(sets, wildcard_rank, has_seen_joker=False):
    """Score a player's final hand: cards inside a valid set score 0, wildcards
    always score 0, everything else scores at face value (A/J/Q/K = 10)."""
    points = 0
    for group in sets:
        if is_valid_set(group, wildcard_rank, has_seen_joker):
            continue
        for card in group:
            if not is_wildcard_card(card, wildcard_rank):
                points += card_value(card['rank'])
    return points


def room_game_file(room_id):
    return os.path.join(GAMES_DIR, f'{room_id}.json')


def load_game(room_id):
    path = room_game_file(room_id)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def save_game(room_id, game_state):
    os.makedirs(GAMES_DIR, exist_ok=True)
    with open(room_game_file(room_id), 'w') as f:
        json.dump(game_state, f, indent=2)


def find_player(round_data, user_id):
    for player in round_data['players']:
        if player['user_id'] == user_id:
            return player
    return None


def find_card_index(hand, card):
    for i, hand_card in enumerate(hand):
        if hand_card['rank'] == card['rank'] and hand_card['suit'] == card['suit']:
            return i
    return None
