# Rummy Backend — API Flow

End-to-end reference for the frontend integration: sign up/login, create a room, join it, start the game, and play a round.

All requests use `Content-Type: application/json`. Replace `<host>` with the API base URL.

---

## 1. Auth (`/api/users`)

### Sign up
```bash
curl -X POST https://<host>/api/users/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Rahul", "email": "rahul@example.com", "password": "secret123"}'
```
```json
{
  "user": { "id": 3, "name": "Rahul", "email": "rahul@example.com" },
  "token": "<jwt>"
}
```
409 with `{"error_msg": "User already exists"}` if the email is taken.

### Login
```bash
curl -X POST https://<host>/api/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "rahul@example.com", "password": "secret123"}'
```
```json
{
  "user": { "id": 3, "name": "Rahul", "email": "rahul@example.com" },
  "token": "<jwt>"
}
```
401 on invalid credentials.

### Reset password
```bash
curl -X POST https://<host>/api/users/reset-password \
  -H "Content-Type: application/json" \
  -d '{"email": "rahul@example.com", "password": "newpassword123"}'
```
404 if no user has that email.

---

## 2. Room creation (`/api/rooms`)

```bash
curl -X POST https://<host>/api/rooms/userid/3
```
`3` is the creator's `user_id` (host). Response:
```json
{ "room_id": 12, "room_code": "482913" }
```
`room_code` is a random 6-digit numeric code, unique among currently-active rooms. The creator is automatically added as a host in `room_players`.

---

## 3. Join room

Players only need the `room_code` — not the `room_id`.

```bash
curl -X POST https://<host>/api/rooms/join \
  -H "Content-Type: application/json" \
  -d '{"room_code": "482913", "user_id": 7}'
```
```json
{
  "message": "Joined room successfully",
  "room": {
    "id": 12,
    "room_code": "482913",
    "status": "waiting",
    "max_players": 6,
    "created_by": 3
  }
}
```
If the user is already in the room, same shape but `message: "User already exists in the room"` plus a `room_player` object. If `user_id == created_by`, they're marked `is_host: true` automatically.

Navigate the frontend to the lobby using `room.room_code` after this call.

### Leave room
```bash
curl -X POST https://<host>/api/rooms/leave \
  -H "Content-Type: application/json" \
  -d '{"room_id": 12, "user_id": 7}'
```

### Get a user's current rooms (waiting or active)
```bash
curl "https://<host>/api/rooms/user/7/"
```
```json
{
  "rooms": [
    { "id": 12, "room_code": "482913", "status": "waiting", "max_players": 6, "created_by": 3, "member_count": 2, "is_host": false }
  ]
}
```
Use this to resume a user into their lobby/game after a reconnect.

---

## 4. Start game (`/api/games`)

Only the host should call this once enough players (≥2) have joined.

```bash
curl -X POST https://<host>/api/games/start \
  -H "Content-Type: application/json" \
  -d '{"room_id": 12}'
```
```json
{
  "message": "Game started successfully",
  "room": {
    "id": 12,
    "room_code": "482913",
    "status": "active",
    "max_players": 6,
    "created_by": 3,
    "current_round": 1,
    "game_started": true
  }
}
```
This deals 13 cards to each player plus a secret wildcard joker, writes the round state to `games/12.json` (keyed by `room_id`) on the server, and flips `rooms.status` to `active` / `rooms.game_started` to `true`. If the room is already active, this returns `200` with `message: "Game already started for this room"` and the current `room` details instead of an error.

---

## 5. Playing a round

### Get game state (each player polls/fetches their own view)
```bash
curl "https://<host>/api/games/12?user_id=3"
```
```json
{
  "round_number": 1,
  "status": "in_progress",
  "current_turn_user_id": 3,
  "discard_pile": [{"rank": "7", "suit": "clubs"}],
  "draw_pile_count": 26,
  "winner": null,
  "losers": [],
  "pending_declarations": [],
  "player": {
    "user_id": 3,
    "hand": [ ...13 cards... ],
    "laid_sets": [[], [], [], [], []],
    "must_draw": true,
    "has_drawn": false,
    "has_discarded": false,
    "has_declared": false,
    "has_seen_joker": false,
    "this_round_lost": 0
  }
}
```
Only returns the caller's own hand/state (never other players' hands) plus `current_turn_user_id` so the frontend knows whose turn it is. 403 if `user_id` isn't in this game.

`wildcard_joker` is only added to this response in two cases: either this player has personally called `show-joker` (`player.has_seen_joker: true`), or `status` is `"awaiting_scores"` or `"finished"` — once the winner has declared (so everyone else needs to know the wildcard rank to arrange their final `sets` correctly), **any** player can see it, no `show-joker` required.

### See everyone's cards + score once they've submitted
```bash
curl "https://<host>/api/games/12/results"
```
```json
{
  "round_number": 1,
  "status": "awaiting_scores",
  "winner": 3,
  "pending_declarations": [9],
  "wildcard_joker": { "rank": "J", "suit": "clubs" },
  "players": [
    {
      "user_id": 3,
      "hand": [],
      "laid_sets": [[{"rank":"10","suit":"clubs"},{"rank":"10","suit":"diamonds"},{"rank":"10","suit":"hearts"},{"rank":"10","suit":"spades"}]],
      "this_round_lost": 0,
      "is_winner": true,
      "total_score": 40
    },
    {
      "user_id": 7,
      "hand": [],
      "laid_sets": [[{"rank":"8","suit":"hearts"},{"rank":"8","suit":"clubs"}],[{"rank":"Q","suit":"spades"}]],
      "this_round_lost": 30,
      "is_winner": false,
      "total_score": 70
    }
  ]
}
```
Only includes players who have actually submitted (`has_declared: true` — the winner plus anyone who's already called `declare` in phase 2), so this fills in progressively as each player submits; anyone still in `pending_declarations` just isn't in the `players` list yet. `total_score` is that player's cumulative `room_players.score` across the whole game, not just this round's points (`this_round_lost`). `wildcard_joker` is included as soon as there's a `winner` — same "nothing left to hide" rule as everywhere else.

### Draw a card (current-turn player only)
```bash
curl -X POST https://<host>/api/games/12/draw \
  -H "Content-Type: application/json" \
  -d '{"user_id": 3, "source": "deck"}'
```
`source` is `"deck"` or `"discard"`. 400 if it's not their turn or they've already drawn this turn.

### Discard a card
```bash
curl -X POST https://<host>/api/games/12/discard \
  -H "Content-Type: application/json" \
  -d '{"user_id": 3, "card": {"rank": "7", "suit": "hearts"}}'
```
Advances the turn to the next player in `turn_order`.

### Store groupings (optional, any time)
```bash
curl -X POST https://<host>/api/games/12/lay-set \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 3,
    "sets": [
      [{"rank":"5","suit":"hearts"},{"rank":"5","suit":"clubs"}],
      [{"rank":"K","suit":"spades"}],
      []
    ]
  }'
```
Sends the player's *entire* set of groupings in one call — an array of arrays of cards. This just stores whatever is sent as `player.laid_sets` as-is; it's not a validated rummy meld (no suit/sequence/minimum-size rules), so groups can have 1+ cards, and any number of groups.

### Show joker (reveal the round's wildcard to a player with a genuine 4-of-a-kind)
```bash
curl -X POST https://<host>/api/games/12/show-joker \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 3,
    "set": [
      { "rank": "10", "suit": "clubs" },
      { "rank": "10", "suit": "diamonds" },
      { "rank": "10", "suit": "hearts" },
      { "rank": "10", "suit": "spades" }
    ]
  }'
```
```json
{ "message": "Joker revealed", "wildcard_joker": { "rank": "J", "suit": "clubs" } }
```
Requires exactly 4 cards, all the same rank, all actually held by that player (in `hand` or an existing `laid_sets` group). On success, the 4 cards are pulled into a new `laid_sets` group, that player is marked `has_seen_joker: true` for the rest of the round, and the round's secret `wildcard_joker` card is returned **only to that player** — nobody else's response ever includes it.

Once the round's `status` is `"awaiting_scores"` or `"finished"`, `set` is no longer required — call it with just `{"user_id": 5}` and it returns `wildcard_joker` directly, since there's nothing left to hide once a winner has declared.

From then on, that same player's `GET /api/games/<room_id>?user_id=3` response also includes `wildcard_joker` (and `player.has_seen_joker: true`) automatically — they don't need to call `show-joker` again to keep seeing it for the rest of the round.

### Declare (two-phase — winner, then everyone else submits their cards)

**Phase 1 — the first player to declare claims the win.** `card` is always required — it's the closing card, the one extra card they're discarding to finish (it does **not** need to be part of any set; it's just removed from wherever it currently is, in `hand` or a `laid_sets` group):
```bash
curl -X POST https://<host>/api/games/12/declare \
  -H "Content-Type: application/json" \
  -d '{"user_id": 3, "card": {"rank": "10", "suit": "hearts"}}'
```
```json
{ "message": "Declared as winner. Other players must submit their cards to calculate scores.", "winner": 3 }
```
After `card` is pulled out and pushed onto the discard pile (so other players can see what they closed with), everything the player has left must resolve cleanly:
- `hand` must now be empty — nothing ungrouped is allowed.
- Every remaining `laid_sets` group must independently pass the same validity rule used for scoring (3–4 same-rank cards, wildcard-completion only if `has_seen_joker`). If pulling `card` out of a group breaks it (e.g. it was one of only 3 cards in an otherwise-valid set), that group becomes invalid and the whole declare is rejected with `400` and an `invalid_sets` list — the frontend must pick a genuinely spare card to close with, not one needed to complete a set.

Round status moves to `awaiting_scores`, and `round_data.pending_declarations` is set to every other player's `user_id` — use this to notify each of them that they still need to submit their cards (also returned in the response, and visible to everyone via `GET /api/games/<room_id>`).

**Phase 2 — every other player then submits their full final hand** (all of their cards, partitioned into groups — including any leftover singles as their own 1-card group) to the same endpoint:
```bash
curl -X POST https://<host>/api/games/12/declare \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 7,
    "sets": [
      [{"rank":"8","suit":"hearts"},{"rank":"8","suit":"clubs"},{"rank":"J","suit":"diamonds"}],
      [{"rank":"K","suit":"hearts"},{"rank":"K","suit":"clubs"}],
      [{"rank":"Q","suit":"spades"}]
    ]
  }'
```
```json
{ "message": "Score submitted", "user_id": 7, "points": 30, "round_finished": false }
```

**Scoring rules:**
- A **valid set** is a group of 3–4 cards that all share one rank once wildcards are set aside — scores `0`.
- A **wildcard** is any printed `JOKER`, or any card whose rank matches the round's `wildcard_joker` rank (e.g. if the dealt wildcard was "J of clubs", *every* `J` — any suit — is wild). A wildcard never scores points itself.
- **Using a wildcard to complete a set requires having shown the joker first.** `8, 8, <wildcard>` only counts as a valid 3-set if that player has `has_seen_joker: true` (i.e. they already revealed a genuine 4-of-a-kind via `show-joker` this round). Without that, `8, 8, <wildcard>` is *not* a valid set — the two 8s score at face value (16 total), the wildcard itself still scores 0. A pure natural set (e.g. `10, 10, 10, 10`, no wildcards involved) is always valid regardless of `has_seen_joker`.
- Anything not in a valid set scores at face value: `A/J/Q/K = 10`, number cards = their number.
- `sets` must account for **every** card the player is holding (their `hand` + whatever was already in `laid_sets`) — the API rejects the call if cards are missing, extra, or don't match what they actually hold.

Each submission immediately adds that player's points onto their `room_players.score` row in Supabase, and removes them from `pending_declarations`. Once every non-winner player has submitted (`pending_declarations` is empty), `round_finished` flips to `true` and the round's status becomes `finished`.

---

## Known gaps (not yet implemented)

- No endpoint starts a **new round** after declare, and `rooms.current_round` is never incremented — multi-round games need this next.
- No max-score/elimination logic (a player being knocked out of the game once their total score crosses a threshold).
- Game state (`games/<room_id>.json`) is stored on local disk — this only works correctly on a single server process/instance, not a horizontally-scaled deployment.
