<p align="center">
  <img src="design/thorajit/assets/logo-transparent.webp" alt="Thorajit" width="280">
</p>

# Thorajit

Thorajit is a social game for two or more players about how well you know and understand each other.

## How to play

1. Create a room and invite your friends to join.
2. Each round, the Storyteller chooses a theme and answers a question. The other players write their own plausible answers.
3. The other players try to find the Storyteller’s answer among the choices. Reveal the answers, score points, and pass the Storyteller role to the next player.

With two players, the Storyteller judges the other player’s answer instead. Choose **Shallow** questions for everyday topics or **Deep** questions for more reflective conversations.

See the [full game rules](docs/rules.md) for scoring and other details.

## Play locally

You’ll need Python 3.12 or later. In a terminal, run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Open the address printed in the terminal. Each player needs a separate browser session; use the same running app to join a room. Play with people you trust: rejoining a player currently does not require authentication.

## More information

- [Game rules and scoring](docs/rules.md)
- [Development and local setup](docs/development.md)
- [Question bank and statistics](docs/question-bank.md)
