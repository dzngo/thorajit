# Thorajit

Thorajit is a social game about how well friends know one another. Its Streamlit interface follows the [saved design direction and screen references](design/thorajit/README.md).

## Run locally

Use Python 3.12 or later and install the dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Open the local URL printed by Streamlit. For multiple players, each player opens the app in a separate browser session. The room store is a local JSON file; it is intended for a single app process, not multiple independent servers. The app reads environment settings from `.env` when present. See **Question bank and statistics** below for database and optional assisted-selection configuration.

Player resumption currently selects an existing identity without authentication, including the host identity. Use it with trusted players until host and player authentication are implemented.

The welcome screen and English curated-question flow do not require an assistant key. Answer suggestions and translations require the configured provider credentials; if suggestions are unavailable, players can still enter an answer themselves.

Run the gameplay tests with:

```sh
.venv/bin/python -m unittest discover -s tests/gameplay -q
```

## 1. Core Game Rules

### 1.1 Objective
Celebrate how well friends “get” one another.

### 1.2 Setup
1. Each person enters a display name and selects a distinct emoji for the room.
2. One player becomes the Host, creates a room, and sets:
   - **Language**
   - **Public or private room**
   - **Target score** (default 10 for two players and 100 for standard mode, editable in lobby)
3. Other players select the room by its name, or by its code for a private room.
4. Minimum players to start: **2**. Exactly two players use two-player mode; three or more use standard mode.
5. Storyteller order is randomized once at game start, then rotates every round.
6. During a game, players can leave permanently from the **Game settings** button. If their departure would leave fewer than two players, or reduce a standard game to two, they must confirm that the game will end for everyone. Otherwise the remaining players continue; if the host leaves, another player becomes host.

### 1.3 Turn Structure
In standard mode, each round follows this flow:
1. **Theme and level selection** — Storyteller picks a theme and depth: **Shallow** or **Deep**.
2. **Question proposal** — A curated question is sampled; the Storyteller can edit, change, then confirm. Listeners can save questions for later turns.
3. **Answer entry** —
   - Storyteller submits the Storyteller answer.
   - Each listener submits one plausible answer.
   - Duplicate answers are blocked using exact-match checks.
4. **Guessing** — Listeners guess the Storyteller's answer from the other players' answers; their own answer is hidden.
5. **Reveal & scoring** — Storyteller answer is revealed, listener guesses are shown, points are applied.
6. **Rotation** — If no winner yet, next Storyteller starts the next round.

Question styles:
- **Shallow**: lightweight, realistic, low-pressure prompts about an everyday preference, habit, routine, simple choice, or plausible situation. A generic poll is allowed and humor is optional.
- **Deep**: reflective, emotionally safe prompts that invite a personally true answer.
- **Random 🎲**: wildcard theme for surprising questions.

The approved visual and interaction decisions, including loading states and the round recap, are recorded in [the Thorajit design notes](design/thorajit/README.md). Update those notes when a design decision changes; written decisions supersede older mockups.

### 1.4 Scoring Details

In two-player mode, both players submit answers privately. The Storyteller judges the Listener's answer; a correct Shallow answer earns the Listener 1 point and a correct Deep answer earns 3. Matching answers are allowed. The target is checked after both players have had an equal number of Listener turns. The highest score wins, or equal scores tie. Incomplete rounds award no points.

Standard mode depth multiplier:
- **Shallow = x1**
- **Deep = x2**

Base scoring by listener correctness:
1. **Exactly one listener is correct**:
   - Correct listener: `+3 × Mult`
   - Storyteller: `+3 × Mult`
2. **More than one but not all listeners are correct**:
   - Each correct listener: `+2 × Mult`
   - Storyteller: `+2 × Mult`
3. **Everyone or nobody is correct**:
   - Every listener: `+1 × Mult`
   - Storyteller: `0`

When everyone or nobody is correct, every listener receives the base points, even if they guessed incorrectly or the host reveals before they submit a guess.

Decoy bonus (stacks with base scoring):
- If a listener’s submitted answer is selected by `N` other listeners, that listener gets:
  - `+N × Mult`

### 1.5 End Conditions
- Standard mode: any player reaches/exceeds the target score. Two-player mode: the target is reached and both players have had equal Listener turns.
- Host clicks **End game** (current top score wins).

---

## 2. Streamlit Flow Overview

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


## Question bank and statistics

In development, gameplay reads `storage/curated_question_bank/questions.json`; in production (`WGY_ENV=production`), it reads the `question_bank` table from Neon. Selection starts uniformly among eligible questions. After five consecutive skips in a turn, Gemini proposes an internal search question and OpenAI embeddings rank eligible bank questions; the five closest are shown one at a time. Failures fall back to random sampling. Aggregate statistics do not yet affect sampling. Each game keeps per-player seen and saved questions and a game-wide list of confirmed questions. Saved questions retain the displayed text and can be played again.

Question events persist separately from room state. Development (the default `WGY_ENV=development`) writes to `storage/question_events_dev.sqlite3`. For production, set `WGY_ENV=production` and `QUESTION_DB_NEO_URL` to a Neon PostgreSQL connection string with permission to create and insert into `question_events`; install the dependencies in `requirements.txt`. Never use the production URL for development. The `question_events` table stores anonymous action events, question IDs, timestamps, and unique event IDs, not names, answers, or edited text. The `question_counters` database view provides per-question counts, including zero-count entries for the current bank, and `question_text` contains the original bank `text`, not `display_template`, translated text, or a player-edited version. It is calculated from the events, so existing events are included and retries cannot inflate counts. The catalog is synchronized at app startup and when bank IDs or original question texts change. Assisted sampling requires GOOGLE_API_KEY and OPENAI_API_KEY. Development reads the local `storage/curated_question_bank/embeddings.sqlite3` cache; production reads the `question_embeddings` table in Neon using pgvector. After changing original question texts or adding questions, rebuild the local vectors with `.venv/bin/python skills/curate-game-questions/scripts/neighbours.py --sync`, upload the updated bank using the command below, and then run `.venv/bin/python -m scripts.sync_question_embeddings_neon`. The embedding sync verifies the bank and existing vectors and does not regenerate embeddings. If assisted selection fails, the app uses random sampling and retries after five more skips; server logs record the error type without question text or credentials. Pending events are written in one transaction per batch; events awaiting a temporary database recovery are retained in the room state and retried. The room JSON file itself must also be placed on persistent storage; it is not a multi-instance database.


To upload or update the curated bank in Neon, set `QUESTION_DB_NEO_URL` and run `.venv/bin/python -m scripts.sync_question_bank_neon`. The command upserts the full bank and verifies it in one transaction, and also initializes counter records using each question's original `text`. It does not delete questions already in Neon that are absent from the local bank. The upload always reads the local JSON file, including when `WGY_ENV=production`.
