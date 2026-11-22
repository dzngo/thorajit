"""Searchable emoji picker backed by a locally bundled Emoji Mart component."""

from pathlib import Path

import streamlit as st

_BUNDLE = Path(__file__).with_name("emoji_picker_bundle.js")
_PICKER = st.components.v2.component(
    "thor" "ajit_emoji_picker",
    html='<div class="emoji-root"></div>',
    css="""
    .emoji-trigger { min-height: 3rem; padding: .5rem 1rem; border: 2px solid #98501c;
      border-radius: 999px; background: #fff0d4; color: #603112; font-weight: 800;
      font-family: inherit; font-size: 1rem; cursor: pointer; }
    .emoji-trigger:focus-visible { outline: 3px solid #4a6414; outline-offset: 3px; }
    .emoji-message { color: #8e2815; font-weight: 700; }
    em-emoji-picker { max-width: 100%; --rgb-accent: 113, 134, 21; }
    """,
    js=_BUNDLE.read_text(encoding="utf-8"),
)


def pick_emoji(*, key: str, selected: str = "", taken: list[str] | None = None) -> str:
    """Return the selected emoji; names and availability stay owned by Python."""
    state = st.session_state.get(key, {})
    current = state.get("value", selected) if isinstance(state, dict) else selected
    result = _PICKER(
        key=key,
        data={"value": current, "taken": taken or []},
        default={"value": selected},
        on_value_change=lambda: None,
        width="stretch",
    )
    return result.value or ""
