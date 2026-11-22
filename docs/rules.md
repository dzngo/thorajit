# Game rules


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

The approved visual and interaction decisions, including loading states and the round recap, are recorded in [the Thorajit design notes](../design/thorajit/README.md). Update those notes when a design decision changes; written decisions supersede older mockups.

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

