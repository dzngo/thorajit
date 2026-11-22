# Development and local setup


Use Python 3.12 or later and install the dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run asgi_app.py
```

Open the local URL printed by Streamlit. For multiple players, each player opens the app in a separate browser session. The room store is a local JSON file; it is intended for a single app process, not multiple independent servers. The app reads environment settings from `.env` when present. See [Question bank and statistics](question-bank.md) for database and optional assisted-selection configuration.

Player resumption currently selects an existing identity without authentication, including the host identity. Use it with trusted players until host and player authentication are implemented.

The welcome screen and English curated-question flow do not require an assistant key. Answer suggestions and translations require the configured provider credentials; if suggestions are unavailable, players can still enter an answer themselves.

Run the gameplay tests with:

```sh
.venv/bin/python -m unittest discover -s tests/gameplay -q
```


## Streamlit flow overview


### 2.1 Entry Screen
Landing screen with two actions:
- **Create room**
- **Join room**

### 2.2 Host Flow
1. **Create room** — host name, emoji, room name, language and privacy
   - If the name is already used, choose another name or follow the join/resume flow.
2. **Lobby**
   - Shows room summary and connected players
   - Allows max-score update and player removal
   - Allows the host to save or discard language and privacy changes without removing players
   - Start button enabled when at least 2 players are connected

### 2.3 Join Flow
1. **Find a room** by its public name or private code
2. If room not started: **Player name and emoji** -> join lobby
3. If room already started: **Resume player** (select an existing player in room)
4. **Lobby** (pre-game) or direct game resume (in-game)

### 2.4 In-Game Flow
Persistent board elements:
- Room summary
- Scoreboard
- Current Storyteller marker
- Current round/theme/level
- “You are playing as …” identity cue

Standard mode phases:
1. **Theme and level selection** — Storyteller only (Shallow/Deep)
2. **Question Proposal** — Storyteller can edit/change/confirm
3. **Answer Entry** — Every player submits one answer; no author names shown here
4. **Guessing** — Listeners guess the Storyteller answer from the other players' answers
5. **Reveal & Scoring** — Show Storyteller answer, listener guesses, and per-round point deltas
6. **Results** — Final scoreboard and winners, with a read-only round recap accessible to every player. Navigate completed rounds with the arrows or dropdown; each shows its question, answers, authors, and guesses. Older games may lack question or answer snapshots.

In two-player mode, both players submit answers, then the Storyteller judges the Listener's answer before reveal. The final results show each player's Listener accuracy and correct answers by level.



See the [design notes](../design/thorajit/README.md) for visual and interaction decisions.
