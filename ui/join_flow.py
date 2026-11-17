"""Streamlit implementation of the joiner flow."""

from __future__ import annotations

from typing import Dict

import streamlit as st

from services.room_service import EmojiTakenError, PlayerNameTakenError, PlayerNotFoundError, RoomAlreadyStartedError, RoomNotFoundError, RoomService
from ui import common, visual
from ui.components.emoji_picker import pick_emoji


class JoinFlow:
    STATE_KEY = "join_flow"
    REFRESH_INTERVAL_SECONDS = 3

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "room_list",
            "player_name": "",
            "emoji": "",
            "player_id": None,
            "candidate_room_code": None,
            "joined_room_code": None,
            "selected_player_id": None,
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        return common.get_flow_state(self.STATE_KEY, defaults=self._default_state())

    def render(self) -> None:
        step = self.state["step"]
        if step == "room_list":
            self._render_room_list()
        elif step == "private_room":
            self._render_private_room()
        elif step == "player_name":
            self._render_player_name()
        elif step == "reclaim_player":
            self._render_reclaim_player()
        elif step == "lobby":
            self._render_lobby()
        else:
            st.warning("Unknown step. Resetting join flow.")
            self.reset()
            common.rerun()

    def _render_room_list(self) -> None:
        state = self.state
        if st.button("← Back", key="room_list_back"):
            self.reset()
            st.session_state["route"] = "entry"
            common.rerun()
        st.header("Find your game")
        if state.get("notice"):
            st.warning(state["notice"])
        st.write("Choose a public room to join, or resume a game already in progress.")
        if st.button("Join private room", key="join_private_room", width="stretch"):
            state.pop("notice", None)
            state["step"] = "private_room"
            common.rerun()
        rooms = sorted(
            (room for room in self.room_service.list_rooms() if not room.is_private),
            key=lambda room: (not room.started, room.updated_at),
            reverse=True,
        )
        if not rooms:
            st.info("No public rooms available. Ask your host for a private room code or to create a room.")
            if st.button("Refresh", key="room_list_refresh_empty", width="stretch"):
                common.rerun()
            return

        room_options = {room.room_code: room for room in rooms}
        selected_room_code = st.selectbox(
            "Available rooms",
            options=list(room_options.keys()),
            format_func=lambda code: self._format_room_option(room_options[code]),
        )
        selected_room = room_options[selected_room_code]
        common.show_room_summary(selected_room)

        if st.button("Join room", key="room_list_next", type="primary", width="stretch"):
            state["candidate_room_code"] = selected_room_code
            state["room_list_origin"] = "room_list"
            state.pop("notice", None)
            if selected_room.started:
                state["selected_player_id"] = None
                state["step"] = "reclaim_player"
                common.rerun()
                return
            state["step"] = "player_name"
            common.rerun()
        if st.button("Refresh", key="room_list_refresh", width="stretch"):
            common.rerun()

    def _render_private_room(self) -> None:
        state = self.state
        if st.button("← Back", key="private_room_back"):
            state["step"] = "room_list"
            common.rerun()
        st.header("Join private room")
        st.write("Enter the room code shared by your host.")
        code = st.text_input("Room code", key="private_room_code", placeholder="Enter room code")
        if st.button("Continue", key="private_room_continue", type="primary", width="stretch"):
            if not code.strip():
                st.error("Enter the room code.")
                return
            room = self.room_service.get_room_by_code(code.strip().upper())
            if not room or not room.is_private:
                st.error("Private room not found. Check the code and try again.")
                return
            state["candidate_room_code"] = room.room_code
            state["room_list_origin"] = "private_room"
            state["selected_player_id"] = None
            state.pop("notice", None)
            state["step"] = "reclaim_player" if room.started else "player_name"
            common.rerun()

    def _render_player_name(self) -> None:
        state = self.state
        room_code = state.get("candidate_room_code")
        room = self.room_service.get_room_by_code(room_code) if room_code else None
        if not room:
            self._remember_profile_draft(room_code)
            state["notice"] = "That room is no longer available. Refresh the room list and choose another room."
            state["step"] = "room_list"
            state["candidate_room_code"] = None
            common.rerun()
            return
        if room.started:
            self._remember_profile_draft(room_code)
            state["notice"] = "This game has already started. Choose your player to resume."
            state["step"] = "reclaim_player"
            common.rerun()
            return

        back_slot = st.container()
        st.header("What should we call you?")
        st.write("Your name will be shown to the other players in the room.")
        name_key = f"join_name_{room.room_code}"
        if name_key not in st.session_state:
            st.session_state[name_key] = state["player_name"]
        player_name = st.text_input("Player name", key=name_key, placeholder="Enter your name")
        name_error = st.empty()
        st.markdown("**Your emoji**")
        taken = [p.emoji for p in room.players if p.emoji]
        emoji = pick_emoji(key=f"join_emoji_{room.room_code}", selected=str(state.get("emoji") or ""), taken=taken)
        emoji_error = st.empty()
        if back_slot.button("← Back", key="player_name_back"):
            state["player_name"] = player_name
            state["emoji"] = emoji
            state["step"] = state.get("room_list_origin", "room_list")
            common.rerun()
        if st.button("Join room", key="player_name_join", type="primary", width="stretch"):
            cleaned_name = player_name.strip()
            if not cleaned_name:
                name_error.error("Enter your name.")
            if not emoji:
                emoji_error.error("Choose your emoji.")
            if not cleaned_name or not emoji:
                return
            state["player_name"] = cleaned_name
            state["emoji"] = emoji
            try:
                player = self.room_service.add_player(room, cleaned_name, emoji=emoji)
            except RoomAlreadyStartedError:
                state["notice"] = "This game has already started. Choose your player to resume."
                state["step"] = "reclaim_player"
                common.rerun()
                return
            except RoomNotFoundError:
                state["notice"] = "That room is no longer available. Refresh the room list and choose another room."
                state["step"] = "room_list"
                state["candidate_room_code"] = None
                common.rerun()
                return
            except EmojiTakenError as exc:
                emoji_error.error(str(exc))
                return
            except PlayerNameTakenError as exc:
                name_error.error(str(exc))
                return
            except ValueError as exc:
                st.error(str(exc))
                return
            state["player_id"] = player.player_id
            state["joined_room_code"] = room.room_code
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
            }
            if player.player_id == room.host_id:
                self._resume_host_lobby(room.room_code, player.name)
                return
            state["step"] = "lobby"
            common.rerun()
        if st.button("Resume an existing player", key="resume_lobby_player"):
            state["player_name"] = player_name
            state["emoji"] = emoji
            state["step"] = "reclaim_player"
            common.rerun()

    def _remember_profile_draft(self, room_code: str | None) -> None:
        """Keep a partially completed profile if the selected room changes."""
        if not room_code:
            return
        name = st.session_state.get(f"join_name_{room_code}")
        if isinstance(name, str):
            self.state["player_name"] = name
        picker = st.session_state.get(f"join_emoji_{room_code}")
        if isinstance(picker, dict) and picker.get("value"):
            self.state["emoji"] = picker["value"]

    def _render_reclaim_player(self) -> None:
        state = self.state
        room_code = state.get("candidate_room_code")
        room = self.room_service.get_room_by_code(room_code) if room_code else None
        if not room:
            state["notice"] = "That room is no longer available. Refresh the room list and choose another room."
            state["step"] = "room_list"
            state["candidate_room_code"] = None
            common.rerun()
            return
        if st.button("← Back", key="reclaim_back"):
            state["step"] = state.get("room_list_origin", "room_list")
            state["selected_player_id"] = None
            common.rerun()
        if not room.players:
            st.warning("No players found in this room.")
            return

        st.header("Welcome back")
        if state.get("notice"):
            st.warning(state["notice"])
        else:
            st.write("Choose your player to continue.")
        players = {player.player_id: player for player in room.players}
        options = list(players.keys())
        if len(options) > 5:
            st.caption("Scroll sideways to see all players →")
        selected_player_id = st.radio(
            "Choose your player",
            options=options,
            index=None,
            key=f"{room.room_code}_resume_player",
            format_func=lambda pid: f"{players[pid].emoji or '👤'} {players[pid].name}",
        )
        state["selected_player_id"] = selected_player_id
        existing_player = players.get(selected_player_id)
        emoji = existing_player.emoji if existing_player else None
        if existing_player and not emoji:
            st.markdown("**Choose your emoji to resume**")
            emoji = pick_emoji(key=f"resume_emoji_{room.room_code}_{selected_player_id}",
                               taken=[p.emoji for p in room.players if p.emoji])

        action = "Resume game" if room.started else "Return to lobby"
        if st.button(action, key="reclaim_confirm", type="primary", width="stretch",
                     disabled=existing_player is None):
            if not existing_player:
                st.error("Choose your player to continue.")
                return
            if not emoji:
                st.error("Choose your emoji to continue.")
                return
            try:
                if not existing_player.emoji:
                    self.room_service.set_player_emoji(room, selected_player_id, emoji)
                player = self.room_service.reclaim_player(room, selected_player_id)
            except (EmojiTakenError, PlayerNotFoundError, RoomNotFoundError, ValueError) as exc:
                st.error(str(exc))
                return
            state.pop("notice", None)
            state["player_id"] = player.player_id
            state["player_name"] = player.name
            state["joined_room_code"] = room.room_code
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
            }
            if room.started:
                st.session_state["active_room_code"] = room.room_code
                st.session_state["route"] = "game"
            elif player.player_id == room.host_id:
                self._resume_host_lobby(room.room_code, player.name)
                return
            else:
                state["step"] = "lobby"
            common.rerun()

    def _render_lobby(self) -> None:
        state = self.state
        room = self._load_joined_room()
        if not room:
            state["notice"] = "That room has closed. Refresh the room list and choose another room."
            state["step"] = "room_list"
            state["joined_room_code"] = None
            state["player_id"] = None
            common.rerun()
            return
        if not any(player.player_id == state.get("player_id") for player in room.players):
            state["notice"] = "You are no longer in that room. Choose a room to join again."
            state["step"] = "room_list"
            state["joined_room_code"] = None
            state["player_id"] = None
            st.session_state.pop("player_profile", None)
            st.session_state.pop("active_room_code", None)
            common.rerun()
            return
        if room.started:
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
            common.rerun()
            return
        self._watch_room_updates(room.room_code, room.updated_at.isoformat())
        st.header("Your room")
        common.show_room_summary(room, display_llm=False)
        st.markdown("### Players")
        with st.container(border=True, key="card_guest_players"):
            common.show_players(room.players, current_player_id=state["player_id"])
        visual.waiting_card("Waiting for the host to start…", "")
        col1, col2 = st.columns(2)
        if col1.button("Refresh", key="join_lobby_refresh"):
            common.rerun()
        if col2.button("Change room", key="join_lobby_change"):
            self._leave_current_room()
            state["step"] = "room_list"
            state["candidate_room_code"] = None
            common.rerun()

    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_room_updates(self, room_code: str, known_updated_at: str) -> None:
        """Rerun the page only when the lobby changes."""
        if common.room_has_changed(self.room_service, room_code, known_updated_at):
            st.rerun()

    def _load_joined_room(self):
        code = self.state.get("joined_room_code")
        if not code:
            return None
        return self.room_service.get_room_by_code(code)

    def _resume_host_lobby(self, room_code: str, host_name: str) -> None:
        current_host_state = st.session_state.get("host_flow")
        if not isinstance(current_host_state, dict):
            current_host_state = {}
        current_host_state.setdefault("room_name", "")
        current_host_state.setdefault("existing_room_code", None)
        current_host_state.setdefault("editing_existing", False)
        current_host_state.setdefault("language", "en")
        current_host_state.setdefault("llm_model", "gemini-2.5-flash")
        current_host_state["step"] = "lobby"
        current_host_state["host_name"] = host_name
        current_host_state["room_code"] = room_code
        st.session_state["host_flow"] = current_host_state
        st.session_state["route"] = "host"
        common.rerun()

    def _leave_current_room(self) -> None:
        room_code = self.state.get("joined_room_code")
        player_id = self.state.get("player_id")
        if not (room_code and player_id):
            return
        room = self.room_service.get_room_by_code(room_code)
        if room:
            try:
                self.room_service.remove_player(room, player_id)
            except (RoomAlreadyStartedError, RoomNotFoundError):
                # Keep the player in a game that started while they were leaving.
                pass
        self.state["joined_room_code"] = None
        self.state["player_id"] = None
        st.session_state.pop("player_profile", None)
        if st.session_state.get("active_room_code") == room_code:
            st.session_state.pop("active_room_code", None)

    def _format_room_option(self, room) -> str:
        join_label = common.room_join_label(room)
        return f"{join_label} · In game" if room.started else join_label
