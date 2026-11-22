"""Streamlit implementation of the in-game flow."""

from __future__ import annotations

import copy
import html
import json
import logging
import random
import uuid
from fractions import Fraction
from typing import Dict, List, Optional

import streamlit as st

from models import DEFAULT_THEMES, Level, Player, Room
from services.game_service import GameService, GameStateConflictError, LeaveWouldEndGame
from services.two_player_game import judge_answer, player_statistics
from services.assisted_sampling import assisted_candidates
from services.llm_service import LLMService
from services.room_service import RoomService
from services.question_bank import (
    choose_listener,
    eligible_questions,
    load_questions,
    order_themes_by_distribution,
    prepare_saved_question,
    sample_question,
)
from storage.question_events import QuestionEvents
from storage.room_repository import RoomStorageError
from ui import common, visual


logger = logging.getLogger(__name__)


class GameFlow:
    REFRESH_INTERVAL_SECONDS = 3

    def __init__(
        self,
        room_service: RoomService,
        game_service: GameService,
        llm_service: LLMService,
    ) -> None:
        self.room_service = room_service
        self.game_service = game_service
        self.llm_service = llm_service

    def render(self) -> None:
        room_code = st.session_state.get("active_room_code")
        if not room_code:
            st.info("No active room selected. Start a game from the host lobby.")
            return
        room = self.room_service.get_room_by_code(room_code)
        if not room:
            st.warning("Room no longer exists.")
            return
        profile = st.session_state.get("player_profile", {})
        current_player_id = profile.get("player_id")
        if current_player_id and not any(p.player_id == current_player_id for p in room.players):
            st.session_state.pop("player_profile", None)
            st.session_state.pop("active_room_code", None)
            st.session_state["entry_notice"] = "You are no longer in that room."
            st.session_state["route"] = "entry"
            common.rerun()
            return
        held_reveal = (room.game_state or {}).get("pending_reveals", {}).get(current_player_id)
        if (not room.started or not room.game_state) and not held_reveal:
            visual.waiting_card("Waiting for the host to start…", "")
            if st.button("Back to entry"):
                st.session_state["route"] = "entry"
                common.rerun()
            return

        state = copy.deepcopy(room.game_state or {})
        if not state:
            visual.waiting_card("Getting the game ready…", "")
            return

        if room.started:
            self._flush_events(room, state)
        current_player_name = profile.get("name")
        if held_reveal:
            state = copy.deepcopy(held_reveal)
        departure = (room.game_state or {}).get("last_departure") or {}
        if departure:
            message = f"{departure.get('name', 'A player')} left the game."
            if departure.get("new_host"):
                message += f" {departure['new_host']} is now the host."
            st.info(message)
        is_host = current_player_id == room.host_id
        storyteller_id = self._current_storyteller_id(state)
        storyteller = self._player_lookup(room).get(storyteller_id)

        phase = state.get("phase")
        if phase != "results":
            st.session_state.pop(f"{room.room_code}_show_round_recap", None)
        is_storyteller = current_player_id == storyteller_id
        submissions = state.get("answer_submissions", {})
        listener_has_submitted = bool(current_player_id and current_player_id in submissions)
        waiting_phases = {
            "saved_questions",
            "theme_selection",
            "level_selection",
            "question_generation",
            "judgment",
        }
        should_watch_for_updates = (
            phase in {"guessing", "reveal"}
            or (not is_storyteller and phase in waiting_phases)
            or (phase == "answer_entry" and listener_has_submitted)
        )
        if should_watch_for_updates:
            self._watch_room_updates(room.room_code, room.updated_at.isoformat())
        else:
            self._watch_disruptive_updates(room.room_code, current_player_id, storyteller_id, phase)

        if phase != "results":
            self._render_board(
                room,
                state,
                storyteller,
                current_player_name,
                is_host and not held_reveal,
                is_storyteller,
            )

        phase = state.get("phase")
        if phase == "saved_questions":
            self._render_saved_questions_phase(room, state, storyteller_id, current_player_id)
        elif phase in {"theme_selection", "level_selection"}:
            # Older saved rooms may still be in the former separate level step.
            # Present the combined setup there as well, preserving their selection.
            self._render_theme_phase(room, state, storyteller_id, current_player_id)
        elif phase == "question_generation":
            self._render_question_phase(room, state, storyteller_id, current_player_id)
        elif phase == "answer_entry":
            self._render_answer_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "judgment":
            self._render_two_player_judgment(room, state, storyteller_id, current_player_id)
        elif phase == "guessing":
            self._render_guess_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "reveal":
            if state.get("game_mode") == "two_player":
                self._render_two_player_reveal(room, state, storyteller_id, current_player_id, is_host, held=bool(held_reveal))
            else:
                self._render_reveal_phase(room, state, storyteller_id, current_player_id, is_host, held=bool(held_reveal))
        elif phase == "results":
            self._render_results(room, state, is_host)
        else:
            st.warning("Unknown phase. Resetting to question generation.")
            state["phase"] = "question_generation"
            self._save_state(room, state)

    # ------------------------------------------------------------------ #
    # Board helpers
    # ------------------------------------------------------------------ #
    def _player_lookup(self, room: Room) -> Dict[str, Player]:
        archived = (getattr(room, "game_state", None) or {}).get("departed_players") or {}
        lookup = {pid: Player.from_dict(data) for pid, data in archived.items()}
        lookup.update({player.player_id: player for player in room.players})
        return lookup

    def _current_storyteller_id(self, state: Dict[str, object]) -> Optional[str]:
        order = state.get("storyteller_order") or []
        if not order:
            return None
        turn_index = state.get("turn_index", 0) % len(order)
        return order[turn_index]

    def _storyteller_can_act(
        self,
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> bool:
        if not storyteller_id or not current_player_id:
            return False
        return storyteller_id == current_player_id

    def _clear_question_draft(self, room: Room, state: Dict[str, object], *, clear_widgets: bool = True) -> None:
        """Discard an unconfirmed question before returning to round setup."""
        state["question"] = None
        state["question_autogen_attempted"] = False
        state["consecutive_question_skips"] = 0
        state["assisted_candidate_ids"] = []
        state["assisted_retry_after_skip"] = 5
        state["question_candidates"] = []
        state["current_candidate_index"] = 0
        if clear_widgets:
            for key in self._question_draft_keys(room):
                st.session_state.pop(key, None)

    @staticmethod
    def _question_draft_keys(room: Room) -> tuple[str, ...]:
        question_key = f"{room.room_code}_question_text"
        return question_key, f"{question_key}_prefill", f"{question_key}_editing"

    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_room_updates(self, room_code: str, known_updated_at: str) -> None:
        """Rerun a passive game view only after another player saves a change."""
        if common.room_has_changed(self.room_service, room_code, known_updated_at):
            st.rerun()

    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_disruptive_updates(self, room_code: str, player_id: Optional[str],
                                  storyteller_id: Optional[str], phase: str) -> None:
        """Update active editors only when their current turn has ended or changed."""
        if not player_id:
            return
        try:
            latest = self.room_service.get_room_by_code(room_code)
        except RoomStorageError:
            st.warning("Room connection interrupted. Trying again automatically…")
            return
        if not latest or not any(p.player_id == player_id for p in latest.players):
            st.rerun()
            return
        current = latest.game_state or {}
        if (not latest.started or (current.get("phase") == "results" and phase != "results")
                or (phase != "results" and self._current_storyteller_id(current) != storyteller_id)):
            st.rerun()

    @st.fragment
    def _render_board(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller: Optional[Player],
        current_player_name: Optional[str],
        is_host: bool,
        is_storyteller: bool,
    ) -> None:
        storyteller_name = storyteller.name if storyteller else "Unknown"
        round_number = html.escape(str(state.get("round", 1)))
        if is_storyteller:
            role = "You're the Storyteller"
        elif current_player_name:
            role = f"You're a Listener · Storyteller: {storyteller_name}"
        else:
            role = f"Storyteller: {storyteller_name}"
        panel_key = f"{room.room_code}_game_panel"
        def toggle_panel(name: str) -> None:
            st.session_state[panel_key] = None if st.session_state.get(panel_key) == name else name

        with st.container(key="game_panel_buttons"):
            score_button, settings_button = st.columns(2)
            score_button.button(":material/leaderboard:", key=f"{room.room_code}_open_scores",
                                on_click=toggle_panel, args=("scores",), width="stretch")
            settings_button.button(":material/settings:", key=f"{room.room_code}_open_settings",
                                   on_click=toggle_panel, args=("settings",), width="stretch")
        panel = st.session_state.get(panel_key)
        if panel:
            try:
                latest_room = self.room_service.get_room_by_code(room.room_code)
            except RoomStorageError:
                st.warning("Room connection interrupted. Try refreshing the game view.")
                return
            if latest_room is None:
                common.rerun()
                return
            if isinstance(latest_room, Room):
                room = latest_room
                player_id = (st.session_state.get("player_profile") or {}).get("player_id")
                if player_id and not any(player.player_id == player_id for player in room.players):
                    common.rerun()
                    return
                held = (room.game_state or {}).get("pending_reveals", {}).get(player_id)
                latest_state = held or room.game_state or {}
                if latest_state.get("phase") != state.get("phase"):
                    common.rerun()
                    return
                state = latest_state
                is_host = player_id == room.host_id and not held
        if panel == "scores":
            with st.container(border=True, key="card_game_scoreboard"):
                st.markdown("### Scoreboard")
                scores = state.get("scores") or {}
                ordered = sorted(room.players, key=lambda player: (-scores.get(player.player_id, 0), player.name.casefold()))
                common.show_player_scores(ordered, scores, storyteller_id=self._current_storyteller_id(state))
                if st.button("Refresh game view", key=f"{room.room_code}_refresh_view"):
                    common.rerun()
        elif panel == "settings":
            with st.container(border=True, key="card_game_settings"):
                common.show_room_summary(room, show_mode=False)
                if is_host:
                    with st.popover("End game", key="end_game_popover", width="stretch"):
                        st.caption("End the game and show the current scores? An unfinished round will not be scored.")
                        if st.button("End game now", key="host_end_game", width="stretch"):
                            self._finalize_results(room, state, manual=True)
                self._render_leave_game(room)
        st.html(f'<div class="round-context"><span class="round-pill">Round {round_number}</span>'
                f'<span class="role-pill">{html.escape(role)}</span></div>')
        if (state.get("phase") in {"answer_entry", "guessing", "judgment", "reveal"}
                and (state.get("question") or {}).get("translation_fallback")):
            st.info("This question is shown in English because translation was unavailable or could not preserve player names.")

    def _render_leave_game(self, room: Room) -> None:
        player_id = (st.session_state.get("player_profile") or {}).get("player_id")
        if not player_id or not room.started:
            return
        notice = st.session_state.pop("leave_game_notice", None)
        if notice:
            st.warning(notice)
        with st.popover("Leave game", key="leave_game_popover", on_change="rerun", width="stretch"):
            ends_game = self.game_service.leaving_ends_game(room)
            if ends_game:
                reason = ("fewer than two players would remain" if len(room.players) - 1 < 2
                          else "only two players would remain in this standard game")
                st.warning(f"Leaving will end the game for everyone because {reason}.")
            else:
                st.write("Leave permanently? You won't be able to resume this player.")
                if room.host_id == player_id:
                    st.caption("The host role will pass to another player.")
            if ends_game:
                st.caption("Your player will be removed and cannot be resumed.")
            if st.button("Leave and end game" if ends_game else "Leave game permanently",
                         key="confirm_leave_game", width="stretch"):
                try:
                    self.game_service.leave_game(room, player_id, confirm_end=ends_game)
                except (LeaveWouldEndGame, GameStateConflictError):
                    st.session_state["leave_game_notice"] = "The room changed. Review the updated warning before leaving."
                    common.rerun()
                    return
                st.session_state.pop("player_profile", None)
                st.session_state.pop("active_room_code", None)
                st.session_state.pop("host_flow", None)
                st.session_state.pop("join_flow", None)
                st.session_state["route"] = "entry"
                st.session_state["entry_notice"] = "You left the game."
                common.rerun()
            st.button("Back to game", key="cancel_leave_game", width="stretch",
                      on_click=lambda: st.session_state.update(leave_game_popover=False))

    # ------------------------------------------------------------------ #
    # Phase renderers
    # ------------------------------------------------------------------ #
    def _render_question_wait(self, room: Room, storyteller_id: Optional[str]) -> None:
        storyteller = self._player_lookup(room).get(storyteller_id)
        name = storyteller.name if storyteller else "The Storyteller"
        visual.waiting_card(f"{name} is choosing a question", "")

    def _render_saved_questions_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        if not self._storyteller_can_act(storyteller_id, current_player_id):
            self._render_question_wait(room, storyteller_id)
            return
        st.header("Saved for your turn")
        saved = (state.get("saved_questions_by_player") or {}).get(current_player_id, [])
        if saved:
            groups = [saved[i:i + 5] for i in range(0, len(saved), 5)]
            if len(groups) > 1:
                st.caption("Scroll sideways to see all saved questions →")
            with st.container(key="saved_question_grid"):
                columns = st.columns(len(groups), wrap=False) if len(groups) > 1 else [st.container()]
                for column, group in zip(columns, groups):
                    with column:
                        for item in list(group):
                            visual.question_card(item["question"])
                            metadata = " · ".join(str(part).title() for part in (item.get("theme"), item.get("level")) if part)
                            if metadata:
                                st.caption(metadata)
                            if st.button("Use question", key=f"{room.room_code}_saved_use_{item['save_id']}",
                                         type="primary", width="stretch"):
                                try:
                                    saved_question = prepare_saved_question(item, room.players, storyteller_id)
                                except ValueError as exc:
                                    st.error(str(exc))
                                    return
                                self._clear_question_draft(room, state)
                                state["selected_theme"] = item["theme"]
                                state["selected_level"] = item["level"]
                                state["question"] = saved_question
                                st.session_state[f"{room.room_code}_question_text_prefill"] = saved_question["question"]
                                state["question_autogen_attempted"] = True
                                state["phase"] = "question_generation"
                                self._save_state(room, state)
                            if st.button("Remove", key=f"{room.room_code}_saved_remove_{item['save_id']}", width="stretch"):
                                saved.remove(item)
                                self._queue_event(state, item.get("question_id"), "unsaved")
                                self._save_state(room, state)
        else:
            st.info("You have no saved questions.")
        if st.button("Choose a new question", key=f"{room.room_code}_skip_saved_questions", type="primary", width="stretch"):
            state["phase"] = "theme_selection"
            self._save_state(room, state)

    def _render_theme_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            self._render_question_wait(room, storyteller_id)
            return

        st.header("Set the vibe")
        st.write("You are the Storyteller. Choose a theme and level for this round.")
        theme_key = f"{room.room_code}_theme_select"
        saved = (state.get("saved_questions_by_player") or {}).get(current_player_id, [])
        if saved and st.button("Back to saved questions", key=f"{room.room_code}_back_to_saved_questions"):
            state["phase"] = "saved_questions"
            self._save_state(room, state)
        themes = order_themes_by_distribution(DEFAULT_THEMES, load_questions())
        saved_theme = str(state.get("selected_theme") or "")
        if theme_key not in st.session_state or st.session_state[theme_key] not in themes:
            st.session_state[theme_key] = saved_theme if saved_theme in themes else themes[0]
        selected = st.pills("Choose a theme", options=themes, key=theme_key, required=True, width="stretch", wrap=True)
        level_key = f"{room.room_code}_level_select"
        levels = [Level.SHALLOW.value, Level.DEEP.value]
        selected_level = str(state.get("selected_level") or Level.SHALLOW.value).lower()
        if level_key not in st.session_state or st.session_state[level_key] not in levels:
            st.session_state[level_key] = selected_level if selected_level in levels else levels[0]
        level = st.segmented_control("Choose a level", options=levels, format_func=str.title, key=level_key, required=True, width="stretch")
        if st.button("Continue", key=f"{room.room_code}_vibe_confirm", type="primary", width="stretch"):
            self._clear_question_draft(room, state)
            state["selected_theme"] = selected
            state["selected_level"] = level
            state["phase"] = "question_generation"
            self._save_state(room, state)

    def _render_question_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            self._render_question_wait(room, storyteller_id)
            return

        st.header("Your question")
        question_error = st.session_state.pop(f"{room.room_code}_question_action_error", None)
        if question_error:
            st.error(question_error)
        current_theme = self._current_theme(state)
        current_level = self._current_level_value(state)
        question_data = state.get("question") or {}
        with st.container(key="question_setup"):
            setup, change = st.columns([3, 1.35], gap="small", vertical_alignment="center")
            setup.html(
                '<div class="question-setup-text">'
                f'<span>{html.escape(current_theme)} · {html.escape(current_level.title())}</span></div>'
            )
            theme_slot = change.empty()
            change_theme_clicked = theme_slot.button(
                "Change", key=f"{room.room_code}_question_change_theme", width="stretch"
            )
        manual_key = f"{room.room_code}_question_text"
        prefill_key = f"{manual_key}_prefill"
        editing_key = f"{manual_key}_editing"
        if manual_key not in st.session_state:
            st.session_state[manual_key] = question_data.get("question", "")
        if prefill_key in st.session_state:
            st.session_state[manual_key] = st.session_state.pop(prefill_key)

        if question_data:
            if st.session_state.get(editing_key, False):
                with st.container(border=True, key=f"card_question_edit_{room.room_code}"):
                    manual_value = st.text_area("Edit your question", key=manual_key)
            else:
                visual.question_card(question_data.get("question") or "")
                manual_value = question_data.get("question", "")
            if question_data.get("translation_fallback"):
                st.warning("Translation is unavailable or could not preserve player names. This question is shown in English.")
            if question_data.get("assisted_sampling_unavailable"):
                st.caption("Personalized selection is temporarily unavailable; showing a random question.")

        if not question_data:
            if change_theme_clicked:
                theme_slot.button("Changing…", key=f"{room.room_code}_theme_loading", disabled=True, width="stretch")
                self._clear_question_draft(room, state, clear_widgets=False)
                state["phase"] = "theme_selection"
                self._save_state(room, state, clear_on_success=self._question_draft_keys(room)[1:])
            waiting_slot = st.empty()
            with waiting_slot.container():
                visual.waiting_card("Finding your question…", "")
            if self._prepare_question(room, state, prefill_key, notify=False):
                return
            waiting_slot.empty()

        if not state.get("question"):
            storyteller = self._current_storyteller_id(state)
            seen = (state.get("question_seen_by_player") or {}).get(storyteller, [])
            confirmed = state.get("confirmed_question_ids") or []
            if eligible_questions(load_questions(), current_theme, current_level, [], confirmed) and st.button(
                "Restart my question pool"
            ):
                matching = {
                    q["id"] for q in eligible_questions(load_questions(), current_theme, current_level, [], confirmed)
                }
                state.setdefault("question_seen_by_player", {})[storyteller] = [
                    qid for qid in seen if qid not in matching
                ]
                state["question_autogen_attempted"] = False
                self._save_state(room, state)
            return

        confirm_slot = st.empty()
        change_slot = st.empty()
        edit_slot = st.empty()
        confirm_clicked = confirm_slot.button("Confirm question", key=f"{room.room_code}_question_confirm", type="primary", icon=":material/check:", width="stretch")
        change_clicked = change_slot.button("Change question", key=f"{room.room_code}_question_change", icon=":material/shuffle:", width="stretch")
        def toggle_question_edit() -> None:
            editing = st.session_state.get(editing_key, False)
            st.session_state[editing_key] = not editing
            st.session_state[manual_key] = question_data.get("question", "")

        edit_label = "Cancel edit" if st.session_state.get(editing_key, False) else "Edit question"
        edit_slot.button(edit_label, key=f"{room.room_code}_question_edit", on_click=toggle_question_edit,
                  icon=":material/edit:", width="stretch")
        if change_theme_clicked:
            theme_slot.button("Changing…", key=f"{room.room_code}_theme_loading", disabled=True, width="stretch")
            confirm_slot.button("Confirm question", key=f"{room.room_code}_confirm_busy", disabled=True, width="stretch")
            change_slot.button("Change question", key=f"{room.room_code}_change_theme_busy", disabled=True, width="stretch")
            edit_slot.button(edit_label, key=f"{room.room_code}_edit_busy", disabled=True, width="stretch")
            self._clear_question_draft(room, state, clear_widgets=False)
            state["phase"] = "theme_selection"
            self._save_state(room, state, clear_on_success=self._question_draft_keys(room)[1:])
        if change_clicked:
            theme_slot.button("Change", key=f"{room.room_code}_theme_busy", disabled=True, width="stretch")
            confirm_slot.button("Confirm question", key=f"{room.room_code}_confirm_busy", disabled=True, width="stretch")
            change_slot.button("Finding a question…", key=f"{room.room_code}_question_loading", disabled=True,
                               icon=":material/progress_activity:", width="stretch")
            edit_slot.button(edit_label, key=f"{room.room_code}_edit_busy", disabled=True, width="stretch")
            if self._prepare_question(room, state, prefill_key, notify=True, force=True):
                return
            st.session_state[f"{room.room_code}_question_action_error"] = "Could not find another question. Please try again or choose a different theme."
            common.rerun()
        if confirm_clicked:
            final_question = manual_value.strip()
            if not final_question:
                st.error("Please enter a question.")
                return
            if room.settings.language.lower() == "en" or (
                question_data.get("translation_fallback") and final_question == question_data.get("question")
            ):
                final_question_en = final_question
            else:
                try:
                    theme_slot.button("Change", key=f"{room.room_code}_theme_during_confirmation_busy", disabled=True, width="stretch")
                    confirm_slot.button("Preparing your question…", key=f"{room.room_code}_confirm_loading", disabled=True,
                                        icon=":material/progress_activity:", width="stretch")
                    change_slot.button("Change question", key=f"{room.room_code}_change_during_confirmation_busy", disabled=True, width="stretch")
                    edit_slot.button(edit_label, key=f"{room.room_code}_edit_during_confirmation_busy", disabled=True, width="stretch")
                    translation_trace = self.llm_service.translate_text_with_trace(
                        final_question,
                        source_language=room.settings.language,
                        target_language="en",
                    )
                    if translation_trace["error"]:
                        raise RuntimeError(translation_trace["error"])
                    final_question_en = translation_trace["text"]
                except Exception as exc:
                    logger.warning("Edited question translation unavailable (%s)", type(exc).__name__)
                    st.session_state[f"{room.room_code}_question_action_error"] = "We couldn't translate your edited question. Try again or cancel the edit to use the original."
                    common.rerun()
                    return
            current_question_data = state.get("question") or {}
            question_id = current_question_data.get("question_id")
            source = current_question_data.get("source", "bank")
            edited = final_question != current_question_data.get("question", "")
            state["question"] = dict(current_question_data, question=final_question, question_en=final_question_en)
            if edited:
                state["question"]["translation_fallback"] = False
            if question_id:
                confirmed = state.setdefault("confirmed_question_ids", [])
                if question_id not in confirmed:
                    confirmed.append(question_id)
                action = (
                    ("saved_confirmed_edited" if edited else "saved_confirmed")
                    if source == "saved"
                    else ("confirmed_edited" if edited else "confirmed")
                )
                self._queue_event(state, question_id, action)
                state.setdefault("question_preference_history", {}).setdefault(storyteller_id, []).append(
                    {"question_id": question_id, "action": "confirmed"}
                )
            if source == "saved":
                player_saved = state.setdefault("saved_questions_by_player", {}).setdefault(storyteller_id, [])
                player_saved[:] = [
                    item for item in player_saved if item.get("save_id") != current_question_data.get("save_id")
                ]
            state["phase"] = "answer_entry"
            self._save_state(room, state)

    def _render_answer_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        question = (state.get("question") or {}).get("question")
        if not question:
            st.header("Your answer")
            st.warning("Question not set yet.")
            return

        submissions = dict(state.get("answer_submissions") or {})
        input_key = f"{room.room_code}_answer_input_{current_player_id}_{state.get('round', 1)}"
        prefill_key = f"{input_key}_prefill"
        editing_key = f"{input_key}_editing"
        submitted = submissions.get(current_player_id, "")
        if not submitted:
            st.session_state.pop(editing_key, None)
        is_editing = not submitted or bool(st.session_state.get(editing_key, False))
        st.header("Question")
        visual.question_context(self._current_theme(state), self._current_level_value(state))
        self._render_save_question(room, state, storyteller_id, current_player_id)

        if not current_player_id:
            st.info("Waiting for your player session...")
            return

        lookup = self._player_lookup(room)
        storyteller = lookup.get(storyteller_id)
        storyteller_name = storyteller.name if storyteller else "Storyteller"
        current_level = self._current_level_value(state)
        if input_key not in st.session_state:
            st.session_state[input_key] = submitted
        if prefill_key in st.session_state:
            st.session_state[input_key] = st.session_state.pop(prefill_key)

        if is_editing:
            if current_player_id == storyteller_id:
                st.write("You are the Storyteller. Submit your answer.")
            elif state.get("game_mode") == "two_player":
                st.write("Answer as you think the Storyteller would.")
            else:
                st.write("Submit one plausible answer. Do not reveal whether it is yours.")

        st.header("Your answer" if is_editing else "Answer submitted")
        if is_editing:
            with st.container(border=True, key=f"card_answer_{room.room_code}"):
                st.text_area("Your answer", key=input_key, placeholder="Type your answer", label_visibility="collapsed")
        else:
            visual.answer_card("Your answer", submitted)

        if not is_editing:
            if st.button("Modify", key=f"{room.room_code}_modify_answer_{current_player_id}",
                         type="primary", width="stretch"):
                st.session_state[editing_key] = True
                common.rerun()
        else:
            self._render_answer_actions(
                room=room,
                state=state,
                question=question,
                current_player_id=current_player_id,
                storyteller_name=storyteller_name,
                current_level=current_level,
                submissions=submissions,
                input_key=input_key,
                prefill_key=prefill_key,
                editing_key=editing_key,
                storyteller_id=storyteller_id,
            )

        pending_count = sum(player.player_id not in submissions for player in room.players)
        if pending_count > 0:
            label = "player" if pending_count == 1 else "players"
            message = f"Waiting for {pending_count} {label} to answer…"
            if is_editing:
                st.info(message)
            else:
                visual.waiting_card(message, "")
        else:
            message = ("All answers submitted. Moving to judgment..." if state.get("game_mode") == "two_player"
                       else "All answers submitted. Moving to guessing...")
            visual.waiting_card(message, "")

        if state.get("game_mode") != "two_player" and is_host:
            with st.popover("Host controls", key="answer_host_controls", width="stretch"):
                st.caption("Move on without the remaining answers. Players who haven't answered won't have a choice this round.")
                has_storyteller_answer = bool((submissions.get(storyteller_id) or "").strip())
                if not has_storyteller_answer:
                    st.caption("The Storyteller must answer before guessing can begin.")
                if st.button("Continue without all answers", key="host_force_guessing", width="stretch",
                             disabled=not has_storyteller_answer):
                    state["multiple_choice"] = {
                        "options": self._build_options_from_submissions(
                            room=room,
                            storyteller_id=storyteller_id,
                            submissions=submissions,
                        )
                    }
                    state["listener_guesses"] = {}
                    state["round_summary"] = None
                    state["phase"] = "guessing"
                    self._save_state(room, state)

    def _render_answer_actions(
        self,
        *,
        room: Room,
        state: Dict[str, object],
        question: str,
        current_player_id: str,
        storyteller_name: str,
        current_level: str,
        submissions: Dict[str, str],
        input_key: str,
        prefill_key: str,
        editing_key: str,
        storyteller_id: Optional[str],
    ) -> None:
        submit_label = "Save changes" if current_player_id in submissions else "Submit answer"
        suggestion_error_key = f"{room.room_code}_suggest_error_{current_player_id}"
        suggestion_error = st.session_state.pop(suggestion_error_key, None)
        if suggestion_error:
            st.error(suggestion_error)
        submit_slot = st.empty()
        suggestion_slot = st.empty()
        if submit_slot.button(submit_label, key=f"{room.room_code}_submit_answer_{current_player_id}",
                     type="primary", icon=":material/check:", width="stretch"):
            answer = st.session_state.get(input_key, "").strip()
            if not answer:
                st.error("Answer cannot be empty.")
                return
            other_answers = [text for pid, text in submissions.items() if pid != current_player_id and text.strip()]
            if state.get("game_mode") != "two_player" and self._is_duplicate_answer(
                candidate=answer,
                existing_answers=other_answers,
                question=question,
                language=room.settings.language,
            ):
                st.error("This answer is too similar to an existing submitted answer. Please submit a distinct one.")
                return

            submissions[current_player_id] = answer
            state["answer_submissions"] = submissions
            if len(submissions) >= len(room.players):
                state["round_summary"] = None
                if state.get("game_mode") == "two_player":
                    state["phase"] = "judgment"
                else:
                    state["multiple_choice"] = {
                        "options": self._build_options_from_submissions(
                            room=room, storyteller_id=storyteller_id, submissions=submissions,
                        )
                    }
                    state["listener_guesses"] = {}
                    state["phase"] = "guessing"
            self._save_state(room, state, clear_on_success=(editing_key,))

        if (state.get("game_mode") != "two_player"
                and suggestion_slot.button("Suggest answer", key=f"{room.room_code}_suggest_answer_{current_player_id}",
                              icon=":material/shuffle:", width="stretch")):
            try:
                submit_slot.button(submit_label, key=f"{room.room_code}_submit_suggest_busy_{current_player_id}",
                                   disabled=True, width="stretch")
                suggestion_slot.button("Thinking of an answer…", key=f"{room.room_code}_suggest_loading_{current_player_id}",
                                       icon=":material/progress_activity:", disabled=True, width="stretch")
                resp = self.llm_service.suggest_answer(
                    question=question,
                    storyteller_name=storyteller_name,
                    language=room.settings.language,
                    theme=self._current_theme(state),
                    level=current_level,
                    question_en=(state.get("question") or {}).get("question_en", question),
                )
                suggestion = (resp.answer or "").strip()
                if not suggestion:
                    st.session_state[suggestion_error_key] = "Could not generate an answer suggestion. Please try again."
                    common.rerun()
                    return
                st.session_state[prefill_key] = suggestion
                common.rerun()
            except Exception as exc:
                logger.warning("Answer suggestion unavailable (%s)", type(exc).__name__)
                st.session_state[suggestion_error_key] = "Answer suggestions are unavailable right now. Please write your own answer."
                common.rerun()

    def _render_two_player_judgment(
        self, room: Room, state: Dict[str, object], storyteller_id: Optional[str], current_player_id: Optional[str]
    ) -> None:
        st.header("Your decision" if self._storyteller_can_act(storyteller_id, current_player_id)
                  else "Your answer")
        question = (state.get("question") or {}).get("question", "")
        visual.question_context(self._current_theme(state), self._current_level_value(state))
        self._render_save_question(room, state, storyteller_id, current_player_id)
        if not self._storyteller_can_act(storyteller_id, current_player_id):
            answer = (state.get("answer_submissions") or {}).get(current_player_id)
            if answer:
                visual.answer_card("Your answer", answer)
            visual.waiting_card("Waiting for the Storyteller's decision…", "")
            return
        listeners = [player for player in room.players if player.player_id != storyteller_id]
        submissions = state.get("answer_submissions") or {}
        if len(listeners) != 1 or storyteller_id not in submissions or listeners[0].player_id not in submissions:
            st.warning("Both players must submit an answer before judgment.")
            return
        listener = listeners[0]
        for label, answer, is_storyteller in (
            ("Your answer", submissions[storyteller_id], True),
            (f"{listener.name}'s answer", submissions[listener.player_id], False),
        ):
            card_class = "judgment-card storyteller" if is_storyteller else "judgment-card"
            st.html(f'<div class="{card_class}"><span class="judgment-author">{html.escape(label)}</span>'
                    f'<div class="judgment-answer">{html.escape(str(answer))}</div></div>')
        st.html(f'<div class="decision-prompt">Does {html.escape(listener.name)}\'s answer match what you meant?</div>')
        if st.button("Correct", key=f"{room.room_code}_judgment_correct", type="primary", width="stretch"):
            judge_answer(state, storyteller_id, listener.player_id, True)
            self._save_state(room, state)
        if st.button("Not quite", key=f"{room.room_code}_judgment_incorrect", type="primary", width="stretch"):
            judge_answer(state, storyteller_id, listener.player_id, False)
            self._save_state(room, state)

    def _render_two_player_reveal(
        self, room: Room, state: Dict[str, object], storyteller_id: Optional[str],
        current_player_id: Optional[str], is_host: bool, *, held: bool = False,
    ) -> None:
        st.header("The reveal")
        question = (state.get("question") or {}).get("question", "")
        visual.question_context(self._current_theme(state), self._current_level_value(state))
        if not held:
            self._render_save_question(room, state, storyteller_id, current_player_id)
        else:
            visual.question_card(question)
        summary = state.get("round_summary") or {}
        if not summary:
            st.warning("This round has not been judged.")
            return
        lookup = self._player_lookup(room)
        listener = lookup.get(summary.get("listener_id"))
        storyteller = lookup.get(storyteller_id)
        answers = state.get("answer_submissions") or {}
        for player, player_id, role in ((storyteller, storyteller_id, "Storyteller"),
                                        (listener, summary.get("listener_id"), "Listener")):
            name = player.name if player else role
            answer = html.escape(str(answers.get(player_id, "")))
            emoji = (getattr(player, "emoji", "") or "") if player else ""
            author = html.escape(f"{emoji} {name} ({role})".strip())
            card_class = "vote-card correct" if role == "Storyteller" else "vote-card"
            st.html(f'<div class="{card_class}"><div class="vote-content">{answer}</div>'
                    f'<span class="vote-author">{author}</span></div>')
        visual.decision_status(bool(summary.get("correct")))
        with st.container(border=True, key="card_two_player_points"):
            st.markdown("**Points this round**")
            points_by_player = {
                player.player_id: summary.get("points", 0) if player.player_id == summary.get("listener_id") else 0
                for player in room.players
            }
            common.show_player_scores(room.players, points_by_player, prefix="+")
            st.caption(f"{self._current_level_value(state).title()} level")
        if summary.get("winners"):
            st.success("Game complete! Both players have had the same number of Listener turns.")
        self._render_reveal_ready(room, state, current_player_id, bool(summary.get("winners")))

    def _render_guess_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        guesses = dict(state.get("listener_guesses") or {})
        if current_player_id == storyteller_id and storyteller_id is not None:
            heading = "Listeners are guessing"
        elif current_player_id in guesses:
            heading = "Guess submitted"
        else:
            heading = "Find the Storyteller's answer"
        st.header(heading)
        question = (state.get("question") or {}).get("question", "")
        visual.question_context(self._current_theme(state), self._current_level_value(state))
        self._render_save_question(room, state, storyteller_id, current_player_id)

        options = state.get("multiple_choice", {}).get("options", [])
        if not options:
            st.warning("Answers are not ready yet.")
            return

        listeners = [player for player in room.players if player.player_id != storyteller_id]
        listener_ids = {player.player_id for player in listeners}

        eligible_options = [opt for opt in options if opt.get("owner_id") != current_player_id]
        display_to_option = {opt["label"]: opt for opt in eligible_options}

        if current_player_id in listener_ids:
            if current_player_id in guesses:
                chosen_label = guesses[current_player_id].get("label")
                chosen = next((opt.get("text", "") for opt in options if opt.get("label") == chosen_label), "")
                visual.answer_card("Your guess", chosen or "Choice unavailable")
            else:
                if current_player_id in (state.get("invalidated_guesses") or []):
                    st.warning("The player whose answer you chose left. Please choose another answer.")
                if not display_to_option:
                    st.warning("No eligible answers are available to guess.")
                else:
                    storyteller = self._player_lookup(room).get(storyteller_id)
                    if storyteller:
                        st.html(f'<p class="guess-instruction">Choose the answer you think belongs to '
                                f'<strong>{html.escape(storyteller.name)}</strong>.</p>')
                    st.caption("Your own answer is not shown." + (" Scroll sideways to see all choices." if len(display_to_option) > 5 else ""))
                    selection_display = st.radio(
                        "Choose the Storyteller answer",
                        options=list(display_to_option),
                        format_func=lambda label: display_to_option[label]["text"],
                        index=None,
                        key=f"{room.room_code}_guess_select_{current_player_id}",
                    )
                    if st.button("Submit my guess", key=f"{room.room_code}_submit_guess_{current_player_id}",
                                 type="primary", icon=":material/check:", width="stretch"):
                        selected = display_to_option.get(selection_display)
                        if not selected or selected.get("owner_id") == current_player_id:
                            st.error("Please select another player's answer.")
                        else:
                            guesses[current_player_id] = {"label": selected["label"]}
                            state["listener_guesses"] = guesses
                            state["invalidated_guesses"] = [pid for pid in state.get("invalidated_guesses", [])
                                                            if pid != current_player_id]
                            self._save_state(room, state)
        elif current_player_id == storyteller_id and storyteller_id is not None:
            self._render_storyteller_answers(options, storyteller_id)
        else:
            st.warning("Your player session is unavailable. Return to the room and resume your player.")
            return

        remaining_count = len(listener_ids.difference(guesses))
        if remaining_count > 0:
            label = "listener" if remaining_count == 1 else "listeners"
            message = f"Waiting for {remaining_count} {label} to choose…"
            if current_player_id == storyteller_id or current_player_id in guesses:
                visual.waiting_card(message, "")
            else:
                st.caption(message)
        else:
            state["phase"] = "reveal"
            self._save_state(room, state, refresh_on_conflict=True)
            st.success("All guesses submitted! Revealing...")

        if is_host:
            with st.popover("Host controls", key="guess_host_controls", width="stretch"):
                st.caption("Reveal now without the remaining guesses. The round will be scored immediately.")
                if st.button("Reveal without all guesses", key="host_force_reveal", width="stretch"):
                    state["phase"] = "reveal"
                    self._save_state(room, state)

    @staticmethod
    def _render_storyteller_answers(options, storyteller_id: str) -> None:
        """Show all answer choices without revealing who wrote the decoys."""
        cards = []
        for option in options:
            own = option.get("owner_id") == storyteller_id
            label = '<span class="story-answer-label">Your answer</span>' if own else ''
            cards.append(f'<div class="story-answer{" own" if own else ""}" role="listitem">'
                         f'{label}<span>{html.escape(str(option.get("text", "")))}</span></div>')
        groups = [cards[index:index + 5] for index in range(0, len(cards), 5)]
        columns = ''.join(f'<div class="story-answer-column" role="list">{"".join(group)}</div>'
                          for group in groups)
        st.markdown("**Submitted answers**")
        if len(groups) > 1:
            st.caption("Scroll sideways to see all answers →")
        st.html(f'<div class="story-answer-columns{" multiple" if len(groups) > 1 else ""}" '
                f'role="region" tabindex="0" aria-label="Submitted answers">{columns}</div>')

    def _render_reveal_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool, *, held: bool = False,
    ) -> None:
        st.header("The reveal")
        question = (state.get("question") or {}).get("question", "")
        visual.question_context(self._current_theme(state), self._current_level_value(state))
        if not held:
            self._render_save_question(room, state, storyteller_id, current_player_id)
        else:
            visual.question_card(question)

        options = (state.get("multiple_choice") or {}).get("options", [])
        lookup = self._player_lookup(room)
        if not state.get("round_summary"):
            summary = self._compute_scoring(room, state, storyteller_id)
            state["round_summary"] = summary
            self._record_completed_round(room, state, storyteller_id, summary)
            self._save_state(room, state, refresh_on_conflict=True)
        else:
            summary = state["round_summary"]

        guesses = summary.get("guesses", {})
        self._render_reveal_choices(options, guesses, lookup)

        deltas = summary.get("deltas", {})
        with st.container(border=True, key="card_round_points"):
            st.markdown("**Points this round**")
            common.show_player_scores(room.players, deltas, prefix="+")

        if summary.get("winners"):
            st.success("We have a winner!")
        self._render_reveal_ready(room, state, current_player_id, bool(summary.get("winners")))

    def _render_reveal_ready(self, room: Room, state: Dict[str, object], player_id: Optional[str], final: bool) -> None:
        players = {player.player_id for player in room.players}
        if player_id not in players:
            st.warning("Your player session is unavailable. Return to the room and resume your player.")
            return
        ready = set(state.get("reveal_ready") or []) & players
        if player_id in ready:
            detail = "Waiting for the host or Storyteller to continue."
            visual.waiting_card("Waiting for the final results…" if final else "Waiting for the next turn…", detail)
            return
        label = "View final results" if final else "Next turn"
        key = f"{room.room_code}_view_results" if final else f"{room.room_code}_next_turn_action"
        if st.button(label, key=key, type="primary", width="stretch"):
            try:
                self.game_service.mark_reveal_ready(room, player_id, state)
            except GameStateConflictError:
                st.warning("The game changed. Refreshing the current view.")
            common.rerun()

    @staticmethod
    def _render_reveal_choices(options, guesses, lookup) -> None:
        """Render answer authors and voters together, with one column per five choices."""
        labels = {option.get("label") for option in options}
        valid = {pid: guess for pid, guess in guesses.items()
                 if pid in lookup and isinstance(guess, dict) and guess.get("label") in labels}
        cards = []
        for option in options:
            label = option.get("label")
            voters = [lookup[pid] for pid, guess in valid.items() if guess.get("label") == label]
            owner = lookup.get(option.get("owner_id"))
            author = html.escape(f"{getattr(owner, 'emoji', '') or ''} {owner.name if owner else 'Unknown'}".strip())
            text = html.escape(str(option.get("text", "")))
            correct = option.get("kind") == "true"
            thorajit = correct and len(voters) == 1
            share = (100 * len(voters) / len(valid)) if valid else 0
            names = ", ".join(player.name for player in voters) or "nobody"
            description = html.escape(f"{option.get('text', '')}. Written by {owner.name if owner else 'Unknown'}. "
                                      f"Guessed by {names}. {len(voters)} of {len(valid)} guesses."
                                      f"{' Thorajit! Exactly one Listener guessed correctly.' if thorajit else ''}", quote=True)
            # Keep the compact emoji-first design while making the voter identity
            # available on touch and keyboard as well as to screen readers.
            voter_html = "".join(
                f'<details class="vote-voter"><summary aria-label="{html.escape(player.name, quote=True)} voted for this answer">'
                f'{html.escape(getattr(player, "emoji", "") or player.name)}</summary>'
                f'<span class="vote-voter-name">{html.escape(player.name)}</span></details>'
                for player in voters
            )
            badge = ('<span class="vote-correct">✦ Thorajit!</span>' if thorajit else
                     '<span class="vote-correct">✓ Correct</span>' if correct else '')
            decoration = visual.thorajit_decoration() if thorajit else ''
            cards.append(f'''<div class="vote-card{' correct' if correct else ''}{' thor-moment' if thorajit else ''}" role="group" aria-label="{description}">
                <div class="vote-background" aria-hidden="true"><div class="vote-fill" style="--share:{share:.2f}%"></div></div>
                <div class="vote-content"><span>{text}</span><div class="vote-voters">{voter_html}</div></div>
                <span class="vote-author">{author}</span>{badge}{decoration}
                </div>''')
        columns = [cards[index:index + 5] for index in range(0, len(cards), 5)]
        content = "".join(f'<div class="vote-column">{"".join(column)}</div>' for column in columns)
        if len(columns) > 1:
            st.caption("Scroll sideways to see all choices →")
        st.html(f'<div class="vote-columns{" multiple" if len(columns) > 1 else ""}" tabindex="0" '
                f'role="region" aria-label="Answer choices and votes">{content}</div>')

    def _render_results(self, room: Room, state: Dict[str, object], is_host: bool) -> None:
        recap_key = f"{room.room_code}_show_round_recap"
        if st.session_state.get(recap_key):
            self._render_round_recap(room, state, recap_key)
            return
        lookup = self._player_lookup(room)
        scores = state.get("scores") or {}
        scoreboard = sorted(((player.player_id, scores.get(player.player_id, 0)) for player in room.players),
                            key=lambda item: (-item[1], lookup[item[0]].name.casefold()))
        # A manually ended game can have a populated, all-zero scoreboard before
        # anyone has played. Only infer winners when a round was actually played.
        winner_ids = [] if state.get("no_winner") else state.get("winners") or (
            [pid for pid, score in scoreboard if score == scoreboard[0][1]]
            if scoreboard and state.get("completed_rounds") else []
        )
        winners = [lookup[pid] for pid in winner_ids if pid in lookup]
        st.header("Final scoreboard")
        if winners:
            visual.winner_announcement(winners, scores)
        elif not state.get("completed_rounds"):
            st.info("No rounds were completed, so there is no winner yet.")
        elif state.get("no_winner"):
            st.info("The game ended early. The scores are shown below.")
        if state.get("end_reason"):
            st.caption(state["end_reason"])

        rows = []
        previous_score = None
        rank = 0
        for index, (pid, score) in enumerate(scoreboard, 1):
            if score != previous_score:
                rank = index
            previous_score = score
            player = lookup[pid]
            rows.append(f'<div class="results-row"><b>#{rank}</b> '
                        f'<span>{html.escape(getattr(player, "emoji", "") or "")} {html.escape(player.name)}</span>'
                        f'<b>{score} pts</b></div>')
        groups = [rows[i:i + 5] for i in range(0, len(rows), 5)]
        ranking = "".join(f'<div class="results-rank-column">{"".join(group)}</div>' for group in groups)
        stats = (self._build_two_player_statistics_html(room, state) if state.get("game_mode") == "two_player"
                 else self._build_arcade_statistics_html(room, state))
        cue = '<small>Scroll sideways to see all players →</small>' if len(groups) > 1 else ''
        rank_class = "results-rank-columns multiple" if len(groups) > 1 else "results-rank-columns"
        st.html(f'<div class="results-panels"><section class="results-ranking"><h3>🏆 Ranking</h3>{cue}'
                f'<div class="{rank_class}" tabindex="0" role="region" aria-label="Ranking">{ranking}</div></section>'
                f'<div class="results-highlights">{stats}</div></div>')

        if state.get("completed_rounds") and st.button("View round recap", key=f"{room.room_code}_open_recap", width="stretch"):
            st.session_state[recap_key] = True
            st.session_state.pop(f"{room.room_code}_recap_round", None)
            common.rerun()

        if is_host:
            if st.button("Return to host lobby", key="results_return_lobby", type="primary", width="stretch"):
                if (room.game_state or {}).get("question_events_pending"):
                    st.error(
                        "Question statistics are waiting to be saved. Please retry when the database is available."
                    )
                else:
                    try:
                        self.game_service.end_game(room)
                    except GameStateConflictError:
                        st.warning("The game changed. Refresh and try returning to the lobby again.")
                    except RuntimeError:
                        st.error("Question statistics are waiting to be saved. Please retry when the database is available.")
                    else:
                        st.session_state.pop("active_room_code", None)
                        st.session_state["route"] = "host"
                        common.rerun()
        else:
            if st.button("Back to entry", key="results_back_entry", type="primary", width="stretch"):
                st.session_state["route"] = "entry"
                common.rerun()

    def _render_round_recap(self, room: Room, state: Dict[str, object], recap_key: str) -> None:
        rounds = [item for item in (state.get("completed_rounds") or []) if isinstance(item, dict)]
        if st.button("← Back to final scoreboard", key=f"{room.room_code}_recap_back", width="stretch"):
            st.session_state[recap_key] = False
            common.rerun()
        st.header("Round recap")
        if not rounds:
            st.info("No completed rounds to show yet.")
            return
        selection_key = f"{room.room_code}_recap_round"
        indices = list(range(len(rounds)))
        if st.session_state.get(selection_key) not in indices:
            st.session_state[selection_key] = 0

        def move_round(offset: int) -> None:
            st.session_state[selection_key] += offset

        index = st.session_state[selection_key]
        previous, selector, following = st.columns([1, 3, 1], vertical_alignment="bottom")
        previous.button("←", key=f"{room.room_code}_recap_previous", help="Previous round",
                        disabled=index == 0, on_click=move_round, args=(-1,), width="stretch")
        selector.selectbox("Round", indices, format_func=lambda i: f"Round {rounds[i].get('round', i + 1)}",
                           key=selection_key, label_visibility="collapsed")
        following.button("→", key=f"{room.room_code}_recap_next", help="Next round",
                         disabled=index == len(rounds) - 1, on_click=move_round, args=(1,), width="stretch")
        round_data = rounds[st.session_state[selection_key]]
        metadata = " · ".join(str(round_data[key]).title() for key in ("theme", "level") if round_data.get(key))
        if metadata:
            st.html(f'<div class="round-context"><div class="question-setup-text"><span>{html.escape(metadata)}</span></div></div>')
        question = round_data.get("question")
        if question:
            visual.question_card(str(question))
        else:
            st.caption("The question was not saved for this round.")
        lookup = self._player_lookup(room)
        if "listener_id" in round_data:
            answers = round_data.get("answers") or {}
            if not answers:
                st.info("The answers were not saved for this round.")
                return
            for role, pid in (("Storyteller", round_data.get("storyteller_id")),
                              ("Listener", round_data.get("listener_id"))):
                player = lookup.get(pid)
                author = html.escape(f"{getattr(player, 'emoji', '') or ''} {player.name if player else role} ({role})".strip())
                answer = html.escape(str(answers.get(pid, "")))
                card_class = "vote-card correct" if role == "Storyteller" else "vote-card"
                st.html(f'<div class="{card_class}"><div class="vote-content">{answer}</div>'
                        f'<span class="vote-author">{author}</span></div>')
            visual.decision_status(bool(round_data.get("correct")))
        elif round_data.get("options"):
            self._render_reveal_choices(round_data["options"], round_data.get("guesses") or {}, lookup)
        else:
            st.info("The answers were not saved for this round.")

    # ------------------------------------------------------------------ #
    # Scoring & helpers
    # ------------------------------------------------------------------ #
    def _current_theme(self, state: Dict[str, object]) -> str:
        return state.get("selected_theme") or "Open conversation"

    def _current_level_value(self, state: Dict[str, object]) -> str:
        return state.get("selected_level") or Level.SHALLOW.value

    def _inject_results_arcade_css(self) -> None:
        st.markdown(
            """
            <style>
            .wg-results-shell {
              --wg-bg: #070917;
              --wg-panel: rgba(12, 18, 40, 0.92);
              --wg-panel-2: rgba(20, 29, 62, 0.9);
              --wg-cyan: #35f7ff;
              --wg-pink: #ff3df2;
              --wg-yellow: #ffe156;
              --wg-green: #54ff9f;
              --wg-text: #f6f7ff;
              --wg-muted: #9aa8d8;
              margin: 0.5rem 0 1.5rem;
              padding: clamp(1rem, 3vw, 2rem);
              border-radius: 28px;
              background:
                radial-gradient(circle at 10% 0%, rgba(53, 247, 255, 0.18), transparent 28%),
                radial-gradient(circle at 90% 10%, rgba(255, 61, 242, 0.16), transparent 30%),
                linear-gradient(135deg, #060815 0%, #101936 58%, #080a18 100%);
              border: 1px solid rgba(53, 247, 255, 0.28);
              box-shadow: 0 0 42px rgba(53, 247, 255, 0.12), inset 0 0 40px rgba(255,255,255,0.03);
              color: var(--wg-text);
              overflow: hidden;
            }
            .wg-results-hero {
              text-align: center;
              padding: 1.2rem 0 1.5rem;
              animation: wgResultsIn 520ms ease-out both;
            }
            .wg-results-kicker {
              color: var(--wg-yellow);
              letter-spacing: 0.28em;
              font-size: 0.78rem;
              font-weight: 800;
            }
            .wg-results-title {
              margin-top: 0.35rem;
              font-size: clamp(2.2rem, 8vw, 5.3rem);
              line-height: 0.92;
              font-weight: 1000;
              letter-spacing: -0.05em;
              color: #ffffff;
              text-shadow: 0 0 14px rgba(53, 247, 255, 0.75), 0 0 34px rgba(255, 61, 242, 0.4);
              animation: wgNeonPulse 2.8s ease-in-out infinite;
            }
            .wg-results-subtitle {
              margin-top: 0.7rem;
              color: var(--wg-muted);
              font-size: 1rem;
              font-weight: 600;
            }
            .wg-results-reason {
              margin: 0 auto 1rem;
              max-width: 760px;
              padding: 0.75rem 1rem;
              border: 1px solid rgba(255, 225, 86, 0.35);
              border-radius: 999px;
              color: #fff5bc;
              background: rgba(255, 225, 86, 0.08);
              text-align: center;
            }
            .wg-results-champion,
            .wg-results-panel {
              background: linear-gradient(145deg, var(--wg-panel), var(--wg-panel-2));
              border: 1px solid rgba(255, 255, 255, 0.12);
              border-radius: 24px;
              box-shadow: 0 20px 60px rgba(0, 0, 0, 0.26);
              animation: wgResultsIn 620ms ease-out both;
            }
            .wg-results-champion {
              padding: clamp(1.1rem, 3vw, 1.8rem);
              text-align: center;
              border-color: rgba(255, 225, 86, 0.52);
              box-shadow: 0 0 28px rgba(255, 225, 86, 0.12), 0 20px 60px rgba(0,0,0,0.28);
              animation: wgResultsIn 620ms ease-out both, wgWinnerPulse 3.4s ease-in-out infinite;
            }
            .wg-results-card-label,
            .wg-results-section-title {
              color: var(--wg-yellow);
              font-size: 0.88rem;
              font-weight: 900;
              letter-spacing: 0.13em;
              text-transform: uppercase;
            }
            .wg-results-champion-name {
              margin-top: 0.35rem;
              font-size: clamp(1.8rem, 5vw, 3.4rem);
              font-weight: 1000;
              color: #ffffff;
            }
            .wg-results-champion-score {
              color: var(--wg-green);
              font-weight: 900;
              font-size: 1.2rem;
            }
            .wg-results-panel {
              margin-top: 1rem;
              padding: clamp(1rem, 3vw, 1.35rem);
            }
            .wg-results-ranking {
              display: grid;
              gap: 0.7rem;
              margin-top: 0.9rem;
            }
            .wg-results-rank-row {
              display: grid;
              grid-template-columns: auto 1fr auto;
              gap: 0.9rem;
              align-items: center;
              padding: 0.85rem 1rem;
              border-radius: 18px;
              background: rgba(255,255,255,0.055);
              border: 1px solid rgba(255,255,255,0.08);
            }
            .wg-results-rank-number {
              color: var(--wg-cyan);
              font-weight: 1000;
              min-width: 2.2rem;
            }
            .wg-results-rank-name {
              color: var(--wg-text);
              font-weight: 850;
            }
            .wg-results-rank-score {
              color: var(--wg-yellow);
              font-weight: 950;
            }
            .wg-results-stat-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
              gap: 0.85rem;
              margin-top: 1rem;
            }
            .wg-results-stat-card,
            .wg-results-bestie-card {
              padding: 1rem;
              border-radius: 20px;
              background: rgba(5, 9, 24, 0.72);
              border: 1px solid rgba(53, 247, 255, 0.16);
              box-shadow: inset 0 0 18px rgba(53, 247, 255, 0.035);
            }
            .wg-results-stat-title {
              color: var(--wg-cyan);
              font-size: 1rem;
              font-weight: 950;
            }
            .wg-results-stat-subtitle {
              margin-top: 0.2rem;
              color: var(--wg-muted);
              font-size: 0.78rem;
              font-weight: 500;
            }
            .wg-results-stat-value {
              margin-top: 0.72rem;
              color: var(--wg-text);
              font-size: 1.18rem;
              font-weight: 900;
            }
            .wg-results-bestie-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
              gap: 0.85rem;
              margin-top: 1rem;
            }
            .wg-results-bestie-owner {
              color: var(--wg-yellow);
              font-size: 0.85rem;
              font-weight: 900;
            }
            .wg-results-bestie-value {
              margin-top: 0.35rem;
              color: var(--wg-text);
              font-size: 1rem;
              font-weight: 800;
            }
            .wg-results-empty {
              margin-top: 0.8rem;
              color: var(--wg-muted);
            }
            @keyframes wgResultsIn {
              from { opacity: 0; transform: translateY(14px) scale(0.985); }
              to { opacity: 1; transform: translateY(0) scale(1); }
            }
            @keyframes wgNeonPulse {
              0%, 100% { filter: brightness(1); }
              50% { filter: brightness(1.12); }
            }
            @keyframes wgWinnerPulse {
              0%, 100% { box-shadow: 0 0 24px rgba(255,225,86,0.14), 0 20px 60px rgba(0,0,0,0.28); }
              50% { box-shadow: 0 0 38px rgba(255,225,86,0.25), 0 20px 60px rgba(0,0,0,0.28); }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _build_arcade_ranking_html(
        self,
        scoreboard: List[tuple[str, int]],
        lookup: Dict[str, Player],
    ) -> str:
        rows: List[str] = []
        previous_score = None
        rank = 0
        for index, (pid, score) in enumerate(scoreboard, start=1):
            if score != previous_score:
                rank = index
            previous_score = score
            player = lookup.get(pid)
            if not player:
                continue
            rows.append(
                "<div class='wg-results-rank-row'>"
                f"<div class='wg-results-rank-number'>#{rank}</div>"
                f"<div class='wg-results-rank-name'>{html.escape(player.name)}</div>"
                f"<div class='wg-results-rank-score'>{score} pts</div>"
                "</div>"
            )
        return "".join(rows) or "<div class='wg-results-empty'>No scores recorded.</div>"

    def _build_two_player_statistics_html(self, room: Room, state: Dict[str, object]) -> str:
        if not state.get("completed_rounds"):
            return ("<section class='wg-results-panel'><div class='wg-results-section-title'>"
                    "💬 How well did you get each other?</div>"
                    "<div class='wg-results-empty'>No completed rounds yet.</div></section>")
        cards = []
        totals = []
        for player in room.players:
            stats = player_statistics(state, player.player_id)
            totals.append(stats)
            accuracy = f"{stats['accuracy'] * 100:.0f}%" if stats['accuracy'] is not None else "—"
            cards.append(
                "<div class='wg-results-stat-card'>"
                f"<div class='wg-results-stat-title'>{html.escape(player.name)} as Listener</div>"
                f"<div class='wg-results-stat-value'>{stats['correct']} of {stats['turns']} correct · {accuracy}</div>"
                f"<div class='wg-results-stat-subtitle'>Shallow: {stats['shallow']} · Deep: {stats['deep']}</div>"
                "</div>"
            )
        turns = sum(stats['turns'] for stats in totals)
        correct = sum(stats['correct'] for stats in totals)
        shared = f"{correct / turns * 100:.0f}%" if turns else "—"
        return ("<section class='wg-results-panel'>"
                "<div class='wg-results-section-title'>💬 How well did you get each other?</div>"
                f"<div class='wg-results-stat-grid'>{''.join(cards)}</div>"
                f"<div class='wg-results-stat-subtitle'>Shared understanding: {shared} ({correct} of {turns} correct)</div>"
                "</section>")

    def _build_arcade_statistics_html(self, room: Room, state: Dict[str, object]) -> str:
        stats = self._compute_game_statistics(room, state)
        empty_notice = ("<div class='wg-results-empty'>No completed rounds yet.</div>"
                        if not stats["completed_round_count"] else "")
        stat_cards = [
            (
                "🧠 Mind Reader",
                "Highest correct-guess accuracy",
                self._format_stat_winners(stats["mind_reader"], "correct guess"),
            ),
            (
                "🙃 Wrong With Confident",
                "Lowest correct-guess accuracy",
                self._format_accuracy_names(stats["wrong_with_confident"]),
            ),
            (
                "🎭 Best Impostor",
                "Highest decoy success rate",
                self._format_decoy_ratio(stats["best_impostor"]),
            ),
            (
                "🧩 404 Personality",
                "Hardest to guess",
                self._format_stat_winners(stats["personality_404"], "correct guess against them", lower_is_better=True),
            ),
            (
                "👀 No Incognito Mode",
                "Easiest to read",
                self._format_stat_winners(stats["no_incognito_mode"], "correct guess against them"),
            ),
            ("📡 Group Telepathy Score", "Correct guesses by the group",
             f"{stats['group_telepathy_score']:.0f}%" if stats['group_telepathy_score'] is not None else "Not enough data."),
        ]
        cards_html = "".join(
            "<div class='wg-results-stat-card'>"
            f"<div class='wg-results-stat-title'>{html.escape(title)}</div>"
            f"<div class='wg-results-stat-subtitle'>{html.escape(subtitle)}</div>"
            f"<div class='wg-results-stat-value'>{html.escape(value)}</div>"
            "</div>"
            for title, subtitle, value in stat_cards
        )
        besties = stats["certified_besties"]
        groups = [besties[index:index + 5] for index in range(0, len(besties), 5)]
        bestie_columns = "".join(
            f"<div class='wg-results-bestie-column'>{''.join(self._build_bestie_card_html(owner, value) for owner, value in group)}</div>"
            for group in groups
        )
        cue = "<div class='wg-results-stat-subtitle'>Scroll sideways to see all players →</div>" if len(groups) > 1 else ""
        bestie_class = "wg-results-bestie-columns multiple" if len(groups) > 1 else "wg-results-bestie-columns"
        return (
            "<details class='wg-results-panel'>"
            "<summary class='wg-results-section-title'>✨ Game highlights</summary>"
            f"{empty_notice}"
            f"<div class='wg-results-stat-grid'>{cards_html}</div>"
            "</details>"
            "<details class='wg-results-panel'>"
            "<summary class='wg-results-section-title'>🤝 Certified Besties</summary>"
            "<div class='wg-results-stat-subtitle'>Who understood each player best</div>"
            f"{cue}<div class='{bestie_class}' role='region' tabindex='0' aria-label='Certified Besties'>"
            f"{bestie_columns}</div>"
            "</details>"
        )

    def _build_bestie_card_html(self, owner: str, value: str) -> str:
        return (
            "<div class='wg-results-bestie-card'>"
            f"<div class='wg-results-bestie-owner'>{html.escape(owner)}</div>"
            f"<div class='wg-results-bestie-value'>{html.escape(value)}</div>"
            "</div>"
        )

    def _compute_game_statistics(self, room: Room, state: Dict[str, object]) -> Dict[str, object]:
        lookup = self._player_lookup(room)
        completed_rounds = [item for item in state.get("completed_rounds", []) if isinstance(item, dict)]
        correct_guess_counts = {player.player_id: 0 for player in room.players}
        listener_guess_counts = {player.player_id: 0 for player in room.players}
        decoy_pick_counts = {player.player_id: 0 for player in room.players}
        decoy_opportunities = {player.player_id: 0 for player in room.players}
        storyteller_correct_counts = {player.player_id: 0 for player in room.players}
        storyteller_guess_totals = {player.player_id: 0 for player in room.players}
        bestie_counts = {
            storyteller.player_id: {
                listener.player_id: 0 for listener in room.players if listener.player_id != storyteller.player_id
            }
            for storyteller in room.players
        }
        total_guesses = 0
        total_correct = 0

        for round_record in completed_rounds:
            storyteller_id = round_record.get("storyteller_id")
            listener_ids = list(round_record.get("listener_ids") or [])
            guesses = round_record.get("guesses") or {}
            submitted_ids = set(guesses).intersection(listener_ids)
            correct_ids = set(round_record.get("correct_listener_ids") or []).intersection(submitted_ids)
            total_guesses += len(submitted_ids)
            total_correct += len(correct_ids)
            for pid in submitted_ids:
                if pid in listener_guess_counts:
                    listener_guess_counts[pid] += 1
            if storyteller_id in storyteller_guess_totals:
                storyteller_guess_totals[storyteller_id] += len(submitted_ids)
                storyteller_correct_counts[storyteller_id] += len(correct_ids)
            for pid in correct_ids:
                if pid in correct_guess_counts and pid in guesses:
                    correct_guess_counts[pid] += 1
                if storyteller_id in bestie_counts and pid in bestie_counts[storyteller_id]:
                    bestie_counts[storyteller_id][pid] += 1
            options = round_record.get("options") or []
            options_by_label = {option.get("label"): option for option in options}
            decoy_owners = {
                option.get("owner_id") for option in options
                if option.get("kind") == "listener" and option.get("owner_id") in decoy_opportunities
            }
            for guesser_id, guess in guesses.items():
                if guesser_id not in listener_ids:
                    continue
                selected = options_by_label.get(guess.get("label"))
                if not selected:
                    continue
                for owner_id in decoy_owners:
                    if owner_id != guesser_id:
                        decoy_opportunities[owner_id] += 1
                owner_id = selected.get("owner_id")
                if owner_id in decoy_owners and owner_id != guesser_id:
                    decoy_pick_counts[owner_id] += 1

        storyteller_rates: Dict[str, float] = {}
        for pid, guess_total in storyteller_guess_totals.items():
            if guess_total:
                storyteller_rates[pid] = storyteller_correct_counts[pid] / guess_total

        accuracy = {
            pid: Fraction(correct_guess_counts[pid], count)
            for pid, count in listener_guess_counts.items()
            if count > 0 and pid in lookup
        }
        wrong_with_confident = self._accuracy_stat(accuracy, lookup, lowest=True)
        decoy_rates = {
            pid: Fraction(decoy_pick_counts[pid], count)
            for pid, count in decoy_opportunities.items()
            if count > 0 and pid in lookup
        }
        best_impostor = self._accuracy_stat(decoy_rates, lookup)
        best_impostor["ratios"] = {
            lookup[pid].name: (decoy_pick_counts[pid], decoy_opportunities[pid]) for pid in decoy_rates
        }
        return {
            "completed_round_count": len(completed_rounds),
            "group_telepathy_score": (total_correct / total_guesses * 100) if total_guesses else None,
            "mind_reader": self._accuracy_stat(accuracy, lookup),
            "wrong_with_confident": wrong_with_confident,
            "best_impostor": best_impostor,
            "personality_404": self._top_stat_entries(storyteller_rates, lookup, lower_is_better=True),
            "no_incognito_mode": self._top_stat_entries(storyteller_rates, lookup),
            "certified_besties": self._build_certified_bestie_lines(room, bestie_counts),
        }

    @staticmethod
    def _accuracy_stat(accuracy: Dict[str, Fraction], lookup: Dict[str, Player], *, lowest: bool = False) -> dict:
        if not accuracy:
            return {"names": [], "value": None}
        best = min(accuracy.values()) if lowest else max(accuracy.values())
        return {
            "names": sorted(lookup[pid].name for pid, rate in accuracy.items() if rate == best),
            "value": float(best),
        }

    def _top_stat_entries(
        self,
        values: Dict[str, int | float],
        lookup: Dict[str, Player],
        *,
        lower_is_better: bool = False,
    ) -> Dict[str, object]:
        meaningful = {pid: value for pid, value in values.items() if pid in lookup and (lower_is_better or value > 0)}
        if not meaningful:
            return {"names": [], "value": None}
        best_value = min(meaningful.values()) if lower_is_better else max(meaningful.values())
        names = [lookup[pid].name for pid, value in meaningful.items() if value == best_value]
        return {"names": sorted(names), "value": best_value}

    def _build_certified_bestie_lines(
        self,
        room: Room,
        bestie_counts: Dict[str, Dict[str, int]],
    ) -> List[tuple[str, str]]:
        lookup = self._player_lookup(room)
        lines: List[tuple[str, str]] = []
        for player in room.players:
            counts = bestie_counts.get(player.player_id) or {}
            meaningful = {pid: count for pid, count in counts.items() if count > 0 and pid in lookup}
            if not meaningful:
                lines.append((player.name, "No certified bestie yet."))
                continue
            best_value = max(meaningful.values())
            names = sorted(lookup[pid].name for pid, count in meaningful.items() if count == best_value)
            suffix = "time" if best_value == 1 else "times"
            lines.append((player.name, f"{', '.join(names)} ({best_value} {suffix})"))
        return lines

    @staticmethod
    def _format_accuracy_names(stat: Dict[str, object]) -> str:
        names = stat.get("names") or []
        value = stat.get("value")
        if not names or value is None:
            return "Not enough data."
        return "; ".join(f"{name} - {value:.0%}" for name in names)

    @staticmethod
    def _format_decoy_ratio(stat: Dict[str, object]) -> str:
        names = stat.get("names") or []
        ratios = stat.get("ratios") or {}
        if not names:
            return "Not enough data."
        return "; ".join(f"{name} - {ratios[name][0]}/{ratios[name][1]}" for name in names)

    def _format_stat_winners(
        self,
        stat: Dict[str, object],
        unit: str,
        *,
        lower_is_better: bool = False,
    ) -> str:
        names = stat.get("names") or []
        value = stat.get("value")
        if not names or value is None:
            return "Not enough data."
        if isinstance(value, float):
            value_text = f"{value * 100:.0f}%"
        else:
            suffix = unit if value == 1 else self._pluralize_stat_unit(unit)
            value_text = f"{value} {suffix}"
        qualifier = "lowest rate" if lower_is_better and isinstance(value, float) else value_text
        if lower_is_better and isinstance(value, float):
            qualifier = f"{value_text} guessed correctly"
        return f"{', '.join(names)} — {qualifier}"

    @staticmethod
    def _pluralize_stat_unit(unit: str) -> str:
        if unit.endswith("guess"):
            return f"{unit}es"
        return f"{unit}s"

    @staticmethod
    def _queue_event(state: Dict[str, object], question_id: Optional[str], action: str) -> None:
        if question_id:
            state.setdefault("question_events_pending", []).append(
                {"id": str(uuid.uuid4()), "question_id": question_id, "action": action}
            )

    def _render_save_question(
        self, room: Room, state: Dict[str, object], storyteller_id: Optional[str], player_id: Optional[str]
    ) -> None:
        toast_key = f"{room.room_code}_question_saved_toast_{player_id}"
        toast_message = st.session_state.pop(toast_key, None)
        with st.container(key="question_toast_slots"):
            saved_toast = st.empty()
            removed_toast = st.empty()
            if toast_message == "saved":
                saved_toast.toast("Question saved for your next turn!", icon=":material/bookmark:")
            elif toast_message == "removed":
                removed_toast.toast("Question removed from your saved list.", icon=":material/bookmark:")
        question = state.get("question") or {}
        text = str(question.get("question") or "")
        if not player_id or player_id == storyteller_id or not question.get("question_id"):
            visual.question_card(text)
            return
        saved = state.setdefault("saved_questions_by_player", {}).setdefault(player_id, [])
        round_key = str(state.get("round", 1))
        existing = next((item for item in saved if item.get("saved_round") == round_key), None)
        with st.popover(text, key=f"question_card_menu_{room.room_code}_{player_id}", width="stretch"):
            clicked = st.button(
                "Remove saved question" if existing else "Save this question for my next turn",
                key=f"{'unsave' if existing else 'save'}_{room.room_code}_{player_id}",
                icon=":material/bookmark_added:" if existing else ":material/bookmark:",
                width="stretch",
            )
        if clicked and existing:
            saved.remove(existing)
            self._queue_event(state, existing.get("question_id"), "unsaved")
            self._save_state(room, state, toast_key=toast_key, toast_message="removed")
        elif clicked:
            saved.append(
                {
                    "save_id": str(uuid.uuid4()),
                    "saved_round": round_key,
                    "question_id": question["question_id"],
                    "question": question["question"],
                    "question_en": question.get("question_en", ""),
                    "placeholder_player_id": question.get("placeholder_player_id"),
                    "placeholder_player_name": question.get("placeholder_player_name"),
                    "placeholder_storyteller_name": question.get("placeholder_storyteller_name"),
                    "translation_fallback": question.get("translation_fallback", False),
                    "theme": state.get("selected_theme"),
                    "level": state.get("selected_level"),
                }
            )
            self._queue_event(state, question["question_id"], "saved")
            self._save_state(room, state, toast_key=toast_key, toast_message="saved")

    def _prepare_question(
        self, room: Room, state: Dict[str, object], prefill_key: str, *, notify: bool, force: bool = False
    ) -> bool:
        if not force and state.get("question_autogen_attempted"):
            return False
        state["question_autogen_attempted"] = True
        current = state.get("question") or {}
        player_id = self._current_storyteller_id(state)
        if force and current.get("source") == "bank" and not current.get("skipped"):
            question_id = current.get("question_id")
            self._queue_event(state, question_id, "skipped")
            if question_id:
                state.setdefault("question_preference_history", {}).setdefault(player_id, []).append(
                    {"question_id": question_id, "action": "skipped"}
                )
                state["consecutive_question_skips"] = int(state.get("consecutive_question_skips", 0)) + 1
            current["skipped"] = True
        seen = state.setdefault("question_seen_by_player", {}).setdefault(player_id, [])
        bank = load_questions()
        theme = self._current_theme(state)
        level = self._current_level_value(state)
        confirmed = state.get("confirmed_question_ids") or []
        eligible = eligible_questions(bank, theme, level, seen, confirmed)
        eligible_by_id = {item["id"]: item for item in eligible}
        candidate = None
        assisted_ids = [qid for qid in state.get("assisted_candidate_ids", []) if qid in eligible_by_id]
        skip_count = int(state.get("consecutive_question_skips", 0))
        retry_after = int(state.get("assisted_retry_after_skip", 5))
        assisted_unavailable = skip_count >= 5 and skip_count < retry_after and not assisted_ids
        if skip_count >= 5 and eligible:
            if not assisted_ids and skip_count >= retry_after:
                bank_by_id = {item["id"]: item for item in bank}
                history = [
                    {"action": item["action"], "question": bank_by_id[item["question_id"]]["text"]}
                    for item in (state.get("question_preference_history") or {}).get(player_id, [])
                    if item.get("question_id") in bank_by_id and item.get("action") in ("skipped", "confirmed")
                ]
                try:
                    ranked = assisted_candidates(theme, level, history, eligible)
                    assisted_ids = list(dict.fromkeys(qid for qid in ranked if qid in eligible_by_id))[:5]
                    if not assisted_ids:
                        raise ValueError("No eligible assisted questions returned")
                except Exception as exc:
                    # Log the failure category, never provider errors, question text, or credentials.
                    logger.warning("Assisted selection unavailable (%s); retrying after five more skips.",
                                   type(exc).__name__)
                    assisted_ids = []
                    assisted_unavailable = True
                    state["assisted_retry_after_skip"] = skip_count + 5
            if assisted_ids:
                candidate = eligible_by_id[assisted_ids[0]]
        if candidate is None:
            candidate = sample_question(bank, theme, level, seen, confirmed)
        state["assisted_candidate_ids"] = assisted_ids
        if candidate is None:
            state["question"] = None
            self._store_state(room, state)
            self._flush_events(room, state)
            st.info("No more unseen questions for this theme and level. Choose another theme or restart your pool.")
            return False
        try:
            question_en = candidate.get("display_template") or candidate["text"]
            storyteller = self._player_lookup(room).get(player_id)
            if "[STORYTELLER]" in question_en and not storyteller:
                raise ValueError("The current Storyteller could not be found.")
            listener = choose_listener(room.players, player_id) if "[PLAYER]" in question_en else None
            names = []
            if storyteller and "[STORYTELLER]" in question_en:
                question_en = question_en.replace("[STORYTELLER]", storyteller.name)
                names.append(storyteller.name)
            if listener:
                question_en = question_en.replace("[PLAYER]", listener.name)
                names.append(listener.name)
            display = question_en
            translation_fallback = False
            if room.settings.language.lower() != "en":
                for _ in range(2):
                    try:
                        translated = self.llm_service.translate_text_with_trace(
                            question_en, source_language="en", target_language=room.settings.language
                        )
                    except Exception as exc:
                        logger.warning("Question translation unavailable (%s)", type(exc).__name__)
                        translation_fallback = True
                        break
                    if translated["error"]:
                        translation_fallback = True
                        break
                    translated_text = translated["text"]
                    if all(name in translated_text for name in names):
                        display = translated_text
                        break
                else:
                    # Avoid showing a question that names the wrong players.
                    translation_fallback = True
        except Exception as exc:
            self._store_state(room, state)
            self._flush_events(room, state)
            st.error(f"Content service error: {exc}")
            return False
        state["question"] = {
            "question_id": candidate["id"],
            "question": display,
            "question_en": question_en,
            "source": "bank",
            "translation_fallback": translation_fallback,
            "assisted_sampling_unavailable": assisted_unavailable,
        }
        if storyteller and "[STORYTELLER]" in (candidate.get("display_template") or candidate["text"]):
            state["question"]["placeholder_storyteller_name"] = storyteller.name
        if listener:
            state["question"]["placeholder_player_id"] = listener.player_id
            state["question"]["placeholder_player_name"] = listener.name
        seen.append(candidate["id"])
        if state.get("assisted_candidate_ids") and state["assisted_candidate_ids"][0] == candidate["id"]:
            state["assisted_candidate_ids"] = state["assisted_candidate_ids"][1:]
        self._queue_event(state, candidate["id"], "shown")
        st.session_state[prefill_key] = display
        st.session_state.pop(f"{prefill_key.removesuffix('_prefill')}_editing", None)
        self._save_state(room, state)
        return True

    def _flush_events(self, room: Room, state: Dict[str, object]) -> None:
        pending = state.get("question_events_pending") or []
        if not pending:
            return
        try:
            events = QuestionEvents()
            events.record_many(pending)
        except Exception:
            st.warning("Question statistics could not be saved yet; they will be retried.")
            return
        state["question_events_pending"] = []
        try:
            self.game_service.set_state(room, state)
        except (GameStateConflictError, OSError, json.JSONDecodeError):
            state["question_events_pending"] = pending
            st.warning("Question statistics could not be saved yet; they will be retried.")

    def _store_state(self, room: Room, state: Dict[str, object], *, refresh_on_conflict: bool = False) -> None:
        try:
            self.game_service.set_state(room, state)
        except GameStateConflictError:
            if refresh_on_conflict:
                common.rerun()
                return
            st.error("The game changed while you were making that choice. Your action was not saved. "
                     "Please try again; your draft is still here.")
            st.stop()
        except (OSError, json.JSONDecodeError):
            logger.exception("Room storage could not save the game state")
            st.error("The game could not be saved. Your action was not saved. Please try again; "
                     "your draft is still here.")
            st.stop()

    def _save_state(self, room: Room, state: Dict[str, object], *, clear_on_success: tuple[str, ...] = (),
                    refresh_on_conflict: bool = False, toast_key: Optional[str] = None,
                    toast_message: Optional[str] = None) -> None:
        self._store_state(room, state, refresh_on_conflict=refresh_on_conflict)
        for key in clear_on_success:
            st.session_state.pop(key, None)
        self._flush_events(room, state)
        if toast_key and toast_message:
            st.session_state[toast_key] = toast_message
        common.rerun()

    def _is_duplicate_answer(
        self,
        *,
        candidate: str,
        existing_answers: List[str],
        question: str,
        language: str,
    ) -> bool:
        del question, language
        if not existing_answers:
            return False
        normalized_candidate = self._normalize_answer(candidate)
        normalized_existing = {self._normalize_answer(item) for item in existing_answers}
        return normalized_candidate in normalized_existing

    @staticmethod
    def _normalize_answer(value: str) -> str:
        return " ".join(value.lower().strip().split())

    def _build_options_from_submissions(
        self,
        *,
        room: Room,
        storyteller_id: Optional[str],
        submissions: Dict[str, str],
    ) -> List[Dict[str, object]]:
        options: List[Dict[str, object]] = []
        for player in room.players:
            text = (submissions.get(player.player_id) or "").strip()
            if not text:
                continue
            kind = "true" if player.player_id == storyteller_id else "listener"
            options.append(
                {
                    "label": "",
                    "text": text,
                    "kind": kind,
                    "owner_id": player.player_id,
                }
            )
        return self._shuffle_options(options)

    def _compute_scoring(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
    ) -> Dict[str, object]:
        options = {opt["label"]: opt for opt in state.get("multiple_choice", {}).get("options", [])}
        guesses = state.get("listener_guesses", {})
        multiplier = {"shallow": 1, "deep": 2}.get(state.get("selected_level", Level.SHALLOW.value), 1)
        listeners = [player for player in room.players if player.player_id != storyteller_id]
        listener_ids = [player.player_id for player in listeners]
        correct = [pid for pid, guess in guesses.items() if options.get(guess["label"], {}).get("kind") == "true"]
        deltas = {pid: 0 for pid in state.get("scores", {})}

        if listeners:
            if len(correct) == 1:
                deltas[correct[0]] += 3 * multiplier
                if storyteller_id:
                    deltas[storyteller_id] += 3 * multiplier
            elif 0 < len(correct) < len(listeners):
                for pid in correct:
                    deltas[pid] += 2 * multiplier
                if storyteller_id:
                    deltas[storyteller_id] += 2 * multiplier
            else:
                for pid in listener_ids:
                    deltas[pid] += multiplier

            decoy_picks = {pid: 0 for pid in listener_ids}
            for guesser_id, guess in guesses.items():
                label = guess.get("label")
                owner_id = options.get(label, {}).get("owner_id")
                if owner_id in decoy_picks and owner_id != guesser_id:
                    decoy_picks[owner_id] += 1
            for pid, pick_count in decoy_picks.items():
                deltas[pid] += pick_count * multiplier
        else:
            decoy_picks = {}

        for pid, delta in deltas.items():
            state["scores"][pid] = state["scores"].get(pid, 0) + delta

        active_scores = {p.player_id: state["scores"].get(p.player_id, 0) for p in room.players}
        highest = max(active_scores.values(), default=0)
        winners = ([pid for pid, score in active_scores.items() if score == highest]
                   if highest >= room.settings.max_score else [])
        return {
            "guesses": guesses,
            "deltas": deltas,
            "correct": correct,
            "winners": winners,
            "decoy_picks": decoy_picks,
        }

    def _record_completed_round(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        summary: Dict[str, object],
    ) -> None:
        completed_rounds = state.setdefault("completed_rounds", [])
        round_number = int(state.get("round", 1))
        if any(item.get("round") == round_number for item in completed_rounds if isinstance(item, dict)):
            return
        options = (state.get("multiple_choice") or {}).get("options", [])
        guesses = summary.get("guesses", {})
        correct = set(summary.get("correct", []))
        decoy_picks = summary.get("decoy_picks", {})
        completed_rounds.append(
            {
                "round": round_number,
                "storyteller_id": storyteller_id,
                "theme": state.get("selected_theme"),
                "level": state.get("selected_level"),
                "question": (state.get("question") or {}).get("question", ""),
                "listener_ids": [player.player_id for player in room.players if player.player_id != storyteller_id],
                "guesses": copy.deepcopy(guesses),
                "correct_listener_ids": list(correct),
                "decoy_picks": copy.deepcopy(decoy_picks),
                "options": copy.deepcopy(options),
                "deltas": copy.deepcopy(summary.get("deltas", {})),
            }
        )

    def _finalize_results(self, room: Room, state: Dict[str, object], manual: bool = False) -> None:
        scores = {p.player_id: (state.get("scores") or {}).get(p.player_id, 0) for p in room.players}
        if not scores:
            return
        top_score = max(scores.values())
        winners = ([pid for pid, value in scores.items() if value == top_score]
                   if state.get("completed_rounds") else [])
        state["phase"] = "results"
        state["winners"] = winners
        if manual:
            state["end_reason"] = "Game ended by the host."
            st.success("Game ended by host.")
        self._save_state(room, state)

    def _shuffle_options(self, options: List[Dict[str, object]]) -> List[Dict[str, object]]:
        shuffled = [dict(option) for option in options]
        random.shuffle(shuffled)
        for idx, option in enumerate(shuffled):
            option["label"] = chr(ord("A") + idx)
        return shuffled
