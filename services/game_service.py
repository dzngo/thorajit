"""Game lifecycle helpers and data management."""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List

from models import (
    Player,
    Room,
)
from services.room_service import RoomService


def _player_scores(players: List[Player]) -> Dict[str, int]:
    return {player.player_id: 0 for player in players}


class GameStateConflictError(Exception):
    """The game changed since this player loaded their current view."""


class GameService:
    """Keeps track of game state stored with the room."""

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    def start_game(self, room: Room) -> Room:
        def start(latest: Room) -> None:
            if latest.started:
                raise ValueError("This game has already started.")
            if len(latest.players) < 2:
                raise ValueError("At least two players are required to start the game.")
            if not latest.settings.max_score_customized:
                latest.settings.max_score = 10 if len(latest.players) == 2 else 100
            order = [player.player_id for player in latest.players]
            random.shuffle(order)
            pending_reveals = copy.deepcopy((latest.game_state or {}).get("pending_reveals") or {})
            latest.started = True
            latest.game_state = self._build_initial_state(latest, order)
            if pending_reveals:
                latest.game_state["pending_reveals"] = pending_reveals
            latest.update_timestamp()

        try:
            latest, _ = self.room_service.repository.update(room.room_code, start)
        except KeyError as exc:
            raise ValueError("This room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def set_state(self, room: Room, state: Dict[str, Any]) -> Room:
        expected = copy.deepcopy(room.game_state)

        def apply(latest: Room) -> None:
            if not latest.started or latest.game_state != expected:
                raise GameStateConflictError("The game changed while you were making that choice.")
            latest.game_state = copy.deepcopy(state)
            latest.update_timestamp()

        try:
            latest, _ = self.room_service.repository.update(room.room_code, apply)
        except KeyError as exc:
            raise GameStateConflictError("The room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def end_game(self, room: Room) -> Room:
        expected = copy.deepcopy(room.game_state)

        def end(latest: Room) -> None:
            if not latest.started or latest.game_state != expected:
                raise GameStateConflictError("The game changed before the lobby was reopened.")
            if (latest.game_state or {}).get("question_events_pending"):
                raise RuntimeError("Question statistics are still pending; retry before leaving the game.")
            pending_reveals = copy.deepcopy((latest.game_state or {}).get("pending_reveals") or {})
            latest.started = False
            latest.game_state = {"pending_reveals": pending_reveals} if pending_reveals else {}
            latest.update_timestamp()

        try:
            latest, _ = self.room_service.repository.update(room.room_code, end)
        except KeyError as exc:
            raise GameStateConflictError("The room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def _build_initial_state(self, room: Room, order: List[str]) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "round": 1,
            "turn_index": 0,
            "storyteller_order": order,
            "phase": "theme_selection",
            "game_mode": "two_player" if len(room.players) == 2 else "standard",
            "selected_theme": None,
            "selected_level": None,
            "question": None,
            "question_autogen_attempted": False,
            "question_candidates": [],
            "question_candidate_pools": {},
            "current_candidate_index": 0,
            "question_history": {},
            "angle_history": {},
            "question_seen_by_player": {},
            "question_preference_history": {},
            "consecutive_question_skips": 0,
            "assisted_candidate_ids": [],
            "assisted_retry_after_skip": 5,
            "confirmed_question_ids": [],
            "saved_questions_by_player": {},
            "question_events_pending": [],
            "answer_submissions": {},
            "multiple_choice": {"options": []},
            "listener_guesses": {},
            "scores": _player_scores(room.players),
            "max_score": room.settings.max_score,
            "round_summary": None,
            "completed_rounds": [],
            "winners": [],
        }
        return state

    def prepare_next_turn(self, room: Room, advance_round: bool = True) -> Room:
        state = copy.deepcopy(room.game_state or {})
        if not state:
            return room
        self._prepare_next_turn_state(state, advance_round)
        return self.set_state(room, state)

    def mark_reveal_ready(self, room: Room, player_id: str, reveal_state: Dict[str, Any] | None = None) -> Room:
        """Continue for one player; the host or Storyteller advances the shared game."""
        shown = reveal_state if reveal_state is not None else (room.game_state or {})
        expected_round = shown.get("round")
        expected_summary = copy.deepcopy(shown.get("round_summary"))

        def mark(latest: Room) -> None:
            state = latest.game_state or {}
            player_ids = {player.player_id for player in latest.players}
            if player_id not in player_ids:
                raise GameStateConflictError("Your player is no longer in this room.")
            pending = state.setdefault("pending_reveals", {})
            held = pending.get(player_id)
            if held and held.get("round") == expected_round and held.get("round_summary") == expected_summary:
                del pending[player_id]
                latest.update_timestamp()
                return
            if (not latest.started or state.get("phase") != "reveal" or state.get("round") != expected_round
                    or state.get("round_summary") != expected_summary):
                raise GameStateConflictError("The game has already moved on.")
            if not expected_summary:
                raise GameStateConflictError("The round results are still being prepared.")
            ready = set(state.get("reveal_ready") or []) & player_ids
            ready.add(player_id)
            state["reveal_ready"] = sorted(ready)
            order = state.get("storyteller_order") or []
            storyteller = order[state.get("turn_index", 0) % len(order)] if order else None
            if player_id in {latest.host_id, storyteller}:
                # Preserve a compact, immutable reveal for players who have not
                # continued yet, including those who have not loaded it at all.
                fields = ("round", "turn_index", "storyteller_order", "game_mode", "question",
                          "round_summary", "scores", "answer_submissions", "multiple_choice",
                          "selected_level", "selected_theme", "max_score")
                snapshot = {key: copy.deepcopy(state[key]) for key in fields if key in state}
                snapshot["phase"] = "reveal"
                for waiting_id in player_ids - ready:
                    pending.setdefault(waiting_id, copy.deepcopy(snapshot))
                winners = state["round_summary"].get("winners") or []
                if winners:
                    state["phase"] = "results"
                    state["winners"] = winners
                    if state.get("game_mode") == "two_player":
                        state["end_reason"] = f"Target score of {state['max_score']} reached after equal Listener turns."
                    else:
                        state["end_reason"] = (
                            "Game ended because at least one player reached the target score "
                            f"of {latest.settings.max_score}."
                        )
                else:
                    self._prepare_next_turn_state(state, True)
            latest.game_state = state
            latest.update_timestamp()

        try:
            latest, _ = self.room_service.repository.update(room.room_code, mark)
        except KeyError as exc:
            raise GameStateConflictError("The room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    @staticmethod
    def _prepare_next_turn_state(state: Dict[str, Any], advance_round: bool) -> None:
        if advance_round:
            state["round"] = state.get("round", 1) + 1
            order = state.get("storyteller_order", [])
            if order:
                state["turn_index"] = (state.get("turn_index", 0) + 1) % len(order)
        else:
            state["turn_index"] = state.get("turn_index", 0)

        state["selected_theme"] = None
        state["selected_level"] = None
        state["question"] = None
        state["question_autogen_attempted"] = False
        state["consecutive_question_skips"] = 0
        state["assisted_candidate_ids"] = []
        state["assisted_retry_after_skip"] = 5
        state["question_candidates"] = []
        state["current_candidate_index"] = 0
        state["answer_submissions"] = {}
        state["multiple_choice"] = {"options": []}
        state["listener_guesses"] = {}
        state["round_summary"] = None
        state["reveal_ready"] = []
        order = state.get("storyteller_order") or []
        storyteller_id = order[state["turn_index"] % len(order)] if order else None
        saved = (state.get("saved_questions_by_player") or {}).get(storyteller_id, [])
        state["phase"] = "saved_questions" if saved else "theme_selection"
