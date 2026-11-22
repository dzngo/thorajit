"""Streamlit-based rendering of the host pre-game journey."""

from __future__ import annotations

from typing import Dict

import streamlit as st

from models import (
    LANGUAGE_FLAGS,
    SUPPORTED_LANGUAGES,
    RoomSettings,
)
from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import EmojiTakenError, InvalidRoomSettingsError, RoomAlreadyStartedError, RoomNameTakenError, RoomNotFoundError, RoomService, RoomSettingsConflictError
from ui import common
from ui.components.emoji_picker import pick_emoji
from ui.components.host_roster import host_roster


class HostFlow:
    STATE_KEY = "host_flow"
    REFRESH_INTERVAL_SECONDS = 3

    def __init__(
        self,
        room_service: RoomService,
        llm_service: LLMService,
        game_service: GameService,
    ) -> None:
        self.room_service = room_service
        self.llm_service = llm_service
        self.game_service = game_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "host_name",
            "host_name": "",
            "emoji": "",
            "room_name": "",
            "is_private": False,
            "room_code": None,
            "existing_room_code": None,
            "editing_existing": False,
            "language": "en",
            "llm_model": "gemini-2.5-flash",
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        state = common.get_flow_state(self.STATE_KEY, defaults=self._default_state())
        defaults = self._default_state()
        for key, value in defaults.items():
            state.setdefault(key, value)
        return state

    def render(self) -> None:
        step = self.state["step"]
        if step in ("host_name", "room_name"):
            self._render_room_name()
        elif step == "existing_room_decision":
            self._render_existing_room_decision()
        elif step == "language":
            self.state["step"] = "room_name"
            self._render_room_name()
        elif step == "lobby":
            self._render_lobby()
        else:
            st.warning("Unknown step. Resetting flow.")
            self.reset()
            common.rerun()

    def _render_room_name(self) -> None:
        state = self.state
        if st.button("← Back", key="room_name_back"):
            self.reset()
            st.session_state["route"] = "entry"
            common.rerun()
        st.header("Create your room")
        st.write("Set up a room for your game and invite your friends to join.")
        host_name = st.text_input("Your name", value=state["host_name"], placeholder="What should we call you?")
        host_error = st.empty()
        st.markdown("**Your emoji**")
        emoji = pick_emoji(key="host_emoji_picker", selected=str(state.get("emoji") or ""))
        emoji_error = st.empty()
        name = st.text_input("Room name", value=state["room_name"], placeholder="Give your room a name")
        room_error = st.empty()
        language_codes = list(SUPPORTED_LANGUAGES)
        current_language = state.get("language", "en")
        language = st.selectbox(
            "Game language", options=language_codes,
            index=language_codes.index(current_language) if current_language in language_codes else 0,
            format_func=lambda code: f"{LANGUAGE_FLAGS.get(code, '')} {SUPPORTED_LANGUAGES[code]}".strip(),
        )
        with st.container(border=True, key="card_private_room"):
            is_private = st.toggle("Private room", value=bool(state.get("is_private", False)))
            help_text = (
                "Share the room code with guests so they can join."
                if is_private
                else "Guests will see the room name directly in the room list."
            )
            st.caption(help_text)
        if st.button("Create room", key="room_name_next", type="primary", width="stretch"):
            cleaned_host = host_name.strip()
            cleaned = name.strip()
            if not cleaned_host:
                host_error.error("Enter your name.")
            if not emoji:
                emoji_error.error("Choose your emoji.")
            if not cleaned:
                room_error.error("Enter a room name.")
            if not cleaned_host or not emoji or not cleaned:
                return
            state["host_name"] = cleaned_host
            state["emoji"] = emoji
            state["room_name"] = cleaned
            state["is_private"] = is_private
            state["language"] = language
            existing = self.room_service.get_room_by_name(cleaned)
            if existing:
                state["existing_room_code"] = existing.room_code
                state["editing_existing"] = False
                state["step"] = "existing_room_decision"
            else:
                state["existing_room_code"] = None
                state["editing_existing"] = False
                try:
                    room = self.room_service.create_room(
                        cleaned_host, cleaned, self._build_room_settings(state), is_private=is_private, emoji=emoji,
                    )
                except RoomNameTakenError as exc:
                    state["existing_room_code"] = exc.room.room_code
                    state["step"] = "existing_room_decision"
                    common.rerun()
                    return
                except (InvalidRoomSettingsError, ValueError) as exc:
                    st.error(str(exc))
                    return
                state["room_code"] = room.room_code
                state["step"] = "lobby"
            common.rerun()

    def _render_existing_room_decision(self) -> None:
        state = self.state
        st.header("Room already exists")
        room = self._get_existing_room()
        if not room:
            st.info("That room is no longer available. You can create it now.")
            state["step"] = "room_name"
            common.rerun()
            return
        st.info("A room with this name already exists. Choose another name or join the existing room.")
        common.show_room_summary(room)
        if st.button("Join existing room", key="existing_join", type="primary", width="stretch"):
            st.session_state["join_flow"] = {
                "step": "reclaim_player" if room.started else "player_name",
                "player_name": state["host_name"], "emoji": state.get("emoji", ""), "player_id": None,
                "candidate_room_code": room.room_code, "joined_room_code": None,
                "selected_player_id": None,
            }
            st.session_state["route"] = "join"
            common.rerun()
        if st.button("Choose another name", key="existing_back", width="stretch"):
            state["step"] = "room_name"
            common.rerun()

    def _render_lobby(self) -> None:
        state = self.state
        room = self._load_room(state["room_code"])
        if not room:
            st.warning("Room could not be found. Let's start again.")
            self.reset()
            common.rerun()
            return

        self._watch_room_updates(room.room_code, room.updated_at.isoformat())

        st.session_state["player_profile"] = {
            "player_id": room.host_id,
            "room_code": room.room_code,
            "name": room.host_name,
        }
        if room.started:
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
            common.rerun()
            return
        host = next((player for player in room.players if player.player_id == room.host_id), None)
        if host and not host.emoji:
            st.header("Choose your emoji")
            st.write("Pick an emoji to represent you in this room.")
            emoji = pick_emoji(key=f"host_resume_emoji_{room.room_code}",
                               taken=[p.emoji for p in room.players if p.emoji])
            if st.button("Save emoji", type="primary", disabled=not emoji):
                try:
                    self.room_service.set_player_emoji(room, host.player_id, emoji)
                except (EmojiTakenError, RoomNotFoundError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    common.rerun()
            return
        st.header("Your room")
        common.show_room_summary(room, show_private_name=True)
        st.markdown("### Players")
        with st.container(border=True, key="card_host_players"):
            selected_id = host_roster(room.players, host_id=room.host_id, key=f"host_roster_{room.room_code}")
            if selected_id and any(player.player_id == selected_id and player.player_id != room.host_id
                                   for player in room.players):
                try:
                    self.room_service.remove_player(room, selected_id)
                except (RoomAlreadyStartedError, RoomNotFoundError):
                    pass
                common.rerun()

        score_key = f"host_lobby_max_score_{room.room_code}"
        observed_score_key = f"host_lobby_observed_score_{room.room_code}"
        default_score = 10 if len(room.players) == 2 else 100
        if not room.settings.max_score_customized and room.settings.max_score != default_score:
            try:
                self.room_service.update_max_score(room, default_score, customized=False)
            except (RoomAlreadyStartedError, RoomNotFoundError):
                common.rerun()
                return
        saved_score = int(room.settings.max_score)
        # Widgets persist in a session independently of rooms. Refresh the value
        # before creating the widget when the saved setting has changed, while
        # preserving an edit made against the last observed setting.
        if (score_key not in st.session_state or
                st.session_state.get(observed_score_key) != saved_score):
            st.session_state[score_key] = saved_score
        st.session_state[observed_score_key] = saved_score
        st.markdown("### Game settings")
        with st.container(border=True, key="card_host_settings"):
            score = st.number_input(
                "Target score",
                min_value=1,
                key=score_key,
            )

            if int(score) != room.settings.max_score:
                try:
                    self.room_service.update_max_score(room, int(score))
                except (RoomAlreadyStartedError, RoomNotFoundError):
                    pass
                common.rerun()
                return

        settings_pending = self._render_lobby_settings(room)

        can_start = len(room.players) >= 2
        if not can_start:
            st.warning("At least two players are required to start the game.")
        else:
            if settings_pending:
                st.info("Save or discard your room settings before starting.")
            if st.button("Start game", type="primary", width="stretch", disabled=settings_pending):
                try:
                    self.game_service.start_game(room)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["active_room_code"] = room.room_code
                    st.session_state["route"] = "game"
                    common.rerun()

        col1, col2 = st.columns(2)
        if col1.button("Refresh lobby", key="lobby_refresh"):
            common.rerun()
        if col2.button("Change room", key="lobby_change_room"):
            state["step"] = "room_name"
            state["existing_room_code"] = None
            state["room_code"] = None
            st.session_state.pop("active_room_code", None)
            common.rerun()

    def _render_lobby_settings(self, room) -> bool:
        """Let the host update language and privacy while retaining the roster."""
        language_key = f"lobby_language_{room.room_code}"
        privacy_key = f"lobby_private_{room.room_code}"
        baseline_key = f"lobby_settings_baseline_{room.room_code}"
        saved = (room.settings.language, room.is_private)
        display_language = saved[0] if saved[0] in SUPPORTED_LANGUAGES else next(iter(SUPPORTED_LANGUAGES))
        with st.expander("Edit room settings"):
            baseline = st.session_state.setdefault(baseline_key, saved)
            if baseline != saved:
                st.warning("Room settings changed elsewhere. Reload them before saving.")
                if st.button("Reload room settings", key=f"{room.room_code}_settings_reload"):
                    st.session_state[baseline_key] = saved
                    st.session_state[language_key] = display_language
                    st.session_state[privacy_key] = saved[1]
                    common.rerun()
            st.session_state.setdefault(language_key, display_language)
            st.session_state.setdefault(privacy_key, saved[1])
            st.selectbox("Game language", options=list(SUPPORTED_LANGUAGES), key=language_key,
                         format_func=lambda code: f"{LANGUAGE_FLAGS.get(code, '')} {SUPPORTED_LANGUAGES[code]}".strip())
            st.toggle("Private room", key=privacy_key)
            st.caption("Share the room code with guests so they can join." if st.session_state[privacy_key]
                       else "Guests will see the room name in the room list.")
            st.caption("Changing these settings keeps everyone in the lobby.")
            dirty = (st.session_state[language_key], st.session_state[privacy_key]) != (display_language, saved[1])

            def discard_changes() -> None:
                st.session_state[baseline_key] = saved
                st.session_state[language_key] = display_language
                st.session_state[privacy_key] = saved[1]

            if st.button("Save room settings", key=f"{room.room_code}_settings_save", type="primary",
                         width="stretch", disabled=baseline != saved or not dirty):
                try:
                    self.room_service.update_lobby_settings(
                        room, language=st.session_state[language_key], is_private=st.session_state[privacy_key],
                        expected_language=baseline[0], expected_private=baseline[1],
                    )
                except (RoomSettingsConflictError, RoomAlreadyStartedError, RoomNotFoundError,
                        InvalidRoomSettingsError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state[baseline_key] = (room.settings.language, room.is_private)
                    common.rerun()
            if dirty:
                st.button("Discard changes", key=f"{room.room_code}_settings_discard", on_click=discard_changes,
                          width="stretch")
        return dirty or baseline != saved
    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_room_updates(self, room_code: str, known_updated_at: str) -> None:
        """Rerun the page only when another player changes the room."""
        if common.room_has_changed(self.room_service, room_code, known_updated_at):
            st.rerun()

    def _build_room_settings(self, state: Dict[str, object]) -> RoomSettings:
        existing_room = self._get_existing_room() if state["editing_existing"] else None
        max_score = existing_room.settings.max_score if existing_room else 100
        return RoomSettings(
            max_score=max_score,
            max_score_customized=existing_room.settings.max_score_customized if existing_room else False,
            language=state.get("language", "en"),
            llm_model=state.get("llm_model", "gemini-2.5-flash"),
        )

    def _get_existing_room(self):
        code = self.state.get("existing_room_code")
        if not code:
            return None
        return self._load_room(code)

    def _load_room(self, room_code):
        if not room_code:
            return None
        return self.room_service.get_room_by_code(room_code)
