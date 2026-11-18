"""Streamlit router handling entry -> host/join/game flows."""

from __future__ import annotations

import streamlit as st
from textwrap import dedent

from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
from storage.room_repository import RoomStorageError
from ui import common
from ui import visual
from ui.game_flow import GameFlow
from ui.host_flow import HostFlow
from ui.join_flow import JoinFlow


class Router:
    RULES_SUMMARY = dedent(
        """
        ### Roles
        - **Storyteller** - chooses the theme, level, and final question, then submits the Storyteller answer.
        - **Listeners** - submit plausible answers, then guess which answer belongs to the Storyteller.

        ---

        ### How a round works: 3 or more players
        1. **Pick the vibe** - The Storyteller chooses a theme and level: Shallow or Deep.
        2. **Get a question** - A question is proposed; the Storyteller can edit it or ask for a new one.
        3. **Write answers** - Every player submits one answer to the same question.
        4. **Everyone guesses** - Listeners choose the answer they think belongs to the Storyteller.
        5. **Reveal & points** - The Storyteller answer is shown, guesses are revealed, and points are awarded.

        ---

        ### Two-player mode
        - Both players answer independently; matching answers are allowed.
        - The Storyteller judges whether the Listener's answer is correct.
        - Correct answers earn the Listener 1 point for Shallow or 3 points for Deep.
        - Players alternate roles. The target is checked after equal Listener turns; equal top scores tie.

        ---

        ### Question styles
        - **Shallow** - funny, quick, low-pressure questions. Expect playful hypotheticals, silly choices, and imagined situations.
        - **Deep** - reflective, emotionally safe questions about memories, values, relationships, beliefs, hopes, or self-understanding.
        - **Random theme** - a wildcard theme for surprising questions.

        ---

        ### Scoring rules
        - **Depth multiplier** - Shallow = x1, Deep = x2.
        - **Exactly one Listener is correct**: that Listener **+3 x depth**, Storyteller **+3 x depth**.
        - **More than one, but not all Listeners are correct**: each Listener **+2 x depth**, Storyteller **+2 x depth**.
        - **Everyone or nobody is correct**: each Listener **+1 x depth**, Storyteller **0**.
        - **Decoy bonus**: if a Listener's submitted answer is chosen by N other Listeners, that Listener gets **+N x depth**.

        ---

        ### How to win
        - The game ends when someone reaches the target score (or the host ends the session). The highest score wins.
        """
    ).strip()

    def __init__(self) -> None:
        self.room_service = RoomService()
        self.game_service = GameService(self.room_service)
        self.llm_service = LLMService()
        self.game_flow = GameFlow(self.room_service, self.game_service, self.llm_service)
        self.host_flow = HostFlow(self.room_service, self.llm_service, self.game_service)
        self.join_flow = JoinFlow(self.room_service)

    def render(self) -> None:
        if "route" not in st.session_state:
            st.session_state["route"] = "entry"
        route = st.session_state["route"]
        visual.apply_style()
        visual.render_brand()
        if route == "entry":
            self._render_entry()
        elif route == "host":
            self.host_flow.render()
        elif route == "join":
            self.join_flow.render()
        elif route == "game":
            self._ensure_game_llm()
            self.game_flow.render()
        else:
            st.session_state["route"] = "entry"
            common.rerun()

    def _render_entry(self) -> None:
        notice = st.session_state.pop("entry_notice", None)
        if notice:
            st.info(notice)
        with st.container(key="welcome"):
            st.header("How well do you know each other?")
            if st.button("Create room", key="entry_create", type="primary", width="stretch"):
                st.session_state["route"] = "host"
                common.rerun()
            if st.button("Join room", key="entry_join", width="stretch"):
                st.session_state["route"] = "join"
                common.rerun()
            with st.expander("How to play"):
                st.markdown(self.RULES_SUMMARY)

    def _ensure_game_llm(self) -> None:
        room_code = st.session_state.get("active_room_code")
        if not room_code:
            return
        room = self.room_service.get_room_by_code(room_code)
        if not room:
            return
        target_model = getattr(room.settings, "llm_model", None) or "gpt-4o-mini"
        current_model = getattr(self.game_flow.llm_service, "selection_name", None)
        if current_model == target_model.lower():
            return
        self.game_flow.llm_service = LLMService(llm_name=target_model)


def run() -> None:
    try:
        Router().render()
    except RoomStorageError:
        st.error("We couldn't load or save the room. Check your connection and try again. "
                 "Your latest action may not have finished.")
        if st.button("Retry", key="room_storage_retry", width="stretch"):
            common.rerun()
