"""Streamlit helpers shared between host and join flows."""

from __future__ import annotations

from typing import Any, Dict
import html

import streamlit as st

from models import LANGUAGE_FLAGS, Room, SUPPORTED_LANGUAGES, SUPPORTED_LLM_MODELS
from storage.room_repository import RoomStorageError


def get_flow_state(key: str, *, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a mutable dict stored in session_state under ``key``."""
    if key not in st.session_state:
        st.session_state[key] = defaults.copy()
    return st.session_state[key]


def reset_flow_state(key: str, *, defaults: Dict[str, Any]) -> None:
    st.session_state[key] = defaults.copy()


def go_home() -> None:
    st.session_state["route"] = "entry"


def rerun() -> None:
    """Trigger a Streamlit rerun while supporting older versions."""
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()
    else:
        getattr(st, "experimental_rerun")()


def show_room_summary(room: Room, display_llm: bool = False, *, show_private_name: bool = False) -> None:
    display_name = room.name if not room.is_private or show_private_name else room.room_code
    settings = room.settings
    language_name = SUPPORTED_LANGUAGES.get(settings.language.lower(), settings.language.upper())
    flag = LANGUAGE_FLAGS.get(settings.language.lower(), "")
    language_display = f"{flag} {language_name}".strip()
    privacy_label = "Private" if room.is_private else "Public"
    count = len(room.players)
    mode = (room.game_state or {}).get("game_mode") if room.started else ("two_player" if count == 2 else "standard")
    rows = [("Room", f"{privacy_label} · {language_display}")]
    if room.is_private and show_private_name:
        rows.append(("Room code", room.room_code))
    rows.extend([
        ("Players", str(count)),
        ("Status", "In game" if room.started else "Lobby"),
        ("Target score", str(settings.max_score)),
        ("Mode", "Two players" if mode == "two_player" else "Standard"),
    ])
    if display_llm:
        rows.append(("Assistant", SUPPORTED_LLM_MODELS.get(settings.llm_model, settings.llm_model)))
    details = "".join(
        f'<div class="room-detail"><dt>{html.escape(str(label))}</dt><dd>{html.escape(str(value))}</dd></div>'
        for label, value in rows
    )
    with st.container(border=True, key="card_room_summary"):
        st.html(f'<h3 class="room-card-title">{html.escape(display_name)}</h3><dl class="room-details">{details}</dl>')


def _show_player_columns(rows: list[str], *, label: str) -> None:
    groups = [rows[index:index + 5] for index in range(0, len(rows), 5)]
    if not groups:
        st.caption("No players yet.")
        return
    if len(groups) > 1:
        st.caption("Scroll sideways to see all players →")
    columns = "".join(f'<div class="player-column" role="list">{"".join(group)}</div>' for group in groups)
    multiple = " multiple" if len(groups) > 1 else ""
    st.html(f'<div class="player-columns{multiple}" role="region" tabindex="0" '
            f'aria-label="{html.escape(label, quote=True)}">{columns}</div>')


def show_players(players: list, *, current_player_id: str | None = None) -> None:
    """Display players in ordered, horizontally scrollable columns of five."""
    rows = []
    for player in players:
        role = " (Host)" if player.role.value == "host" else ""
        you = " (You)" if player.player_id == current_player_id else ""
        emoji = f"{player.emoji} " if getattr(player, "emoji", None) else ""
        text = html.escape(f"{emoji}{player.name}{role}{you}")
        rows.append(f'<div class="player-row" role="listitem"><span>{text}</span></div>')
    _show_player_columns(rows, label="Players")


def show_player_scores(players: list, scores: dict, *, prefix: str = "", storyteller_id: str | None = None) -> None:
    """Display player scores in the same five-per-column layout as the roster."""
    rows = []
    for player in players:
        emoji = f"{player.emoji} " if getattr(player, "emoji", None) else ""
        role = " (Storyteller)" if player.player_id == storyteller_id else ""
        name = html.escape(f"{emoji}{player.name}{role}")
        score = html.escape(f"{prefix}{scores.get(player.player_id, 0)}")
        rows.append(f'<div class="player-row" role="listitem"><span>{name}</span><strong>{score}</strong></div>')
    _show_player_columns(rows, label="Player scores")


def room_has_changed(room_service, room_code: str, known_updated_at: str) -> bool:
    """Poll the room without turning a temporary storage failure into a traceback."""
    try:
        room = room_service.get_room_by_code(room_code)
    except RoomStorageError:
        st.warning("Room connection interrupted. Trying again automatically…")
        return False
    return not room or room.updated_at.isoformat() != known_updated_at


def room_join_label(room: Room) -> str:
    return room.room_code if room.is_private else room.name


def style_buttons() -> None:
    """Inject client-side styling for key button categories."""
    st.html(
        """
        <script>
        (function() {
          const root = document;
          if (!root) return;
          const warnColor = '#000000';
          const positiveColor = '#0f9d58';
          const dangerColor = '#c52233';
          const confirmColor = '#1a73e8';
          const aiColor = '#ea8600';
          const magicColor = '#a73ac9';
          const loveColor = '#cd0487' ;
          const savedColor = '#6b7280';
          const editColor = '#795548';
          const paint = () => {
            const buttons = root.querySelectorAll('button');
            buttons.forEach((btn) => {
              const label = btn.innerText.replace(/\\s+/g, ' ').trim().toLowerCase();
              if (!label) return;
              let bg = '';
              if (['end game', 'force reveal'].includes(label)) {
                bg = warnColor;
              } else if (
                label === 'not quite' ||
                label.includes('back') || 
                label.includes('change room') || 
                label.includes('change theme') ||
                label.includes('change level') ||
                label.includes('return') ||
                label.includes('switch account') ||
                label.includes('report')
              ) {
                bg = dangerColor;
              } else if (
                label.includes('confirm') || 
                label.includes('submit') || 
                label.includes('start') || 
                label.includes('join') || 
                label.includes('reuse') || 
                label.includes('change settings')
              ) {
                bg = confirmColor;
              } else if (label === 'correct' || label.includes('next') || label.includes('refresh') || label.includes('create room')) {
                bg = positiveColor;
              } else if (
                label.includes('suggest') ||
                label.includes('change question') ||
                label.includes('regenerate')
              ) {
                bg = aiColor;
              } else if (label.includes('edit question')) {
                bg = editColor;
              } else if (label.includes('saved for your turn')) {
                bg = savedColor;
              } else if (
                label.includes('like') ||
                label.includes('save for my turn')
              ) {
                bg = loveColor;
              } else if (
                label.includes('rephrase')
              ) {
                bg = magicColor;
              }
              if (bg) {
                btn.style.backgroundColor = bg;
                btn.style.borderColor = bg;
                btn.style.color = '#ffffff';
              }
            });
          };
          const key = '__wg_button_observer';
          if (root[key]) {
            try { root[key].disconnect(); } catch (err) {}
          }
          const observer = new MutationObserver(() => paint());
          observer.observe(root.body, { childList: true, subtree: true });
          root[key] = observer;
          setTimeout(paint, 0);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )
