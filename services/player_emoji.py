"""Emoji validation shared by room operations and the picker."""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path


def emoji_key(value: str) -> str:
    """Treat text/emoji presentation selectors as the same choice."""
    return unicodedata.normalize("NFC", value).replace("\ufe0f", "")


@lru_cache(maxsize=1)
def available_emoji() -> frozenset[str]:
    path = Path(__file__).resolve().parent.parent / "ui/components/emoji_data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(emoji_key(skin["native"]) for item in data["emojis"].values()
                     for skin in item.get("skins", []) if "native" in skin)


def validate_emoji(value: str) -> str:
    value = value.strip()
    if emoji_key(value) not in available_emoji():
        raise ValueError("Choose one emoji from the picker.")
    return value
