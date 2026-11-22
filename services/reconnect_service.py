"""Anonymous browser credentials, stored as digests alongside room data."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from storage.room_repository import RoomRepository


class ReconnectService:
    def __init__(self, repository: RoomRepository):
        self.repository = repository

    def issue(self, room_code: str, player_id: str) -> str:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        def assign(room):
            player = next((p for p in room.players if p.player_id == player_id), None)
            if player is None:
                raise ValueError("Player no longer exists")
            player.reconnect_digest = digest
            player.reconnect_expires_at = expires

        self.repository.update(room_code, assign)
        return token

    def resolve(self, token: str):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        for room in self.repository.list_rooms():
            for player in room.players:
                if not player.reconnect_digest or not player.reconnect_expires_at:
                    continue
                try:
                    expiry = datetime.fromisoformat(player.reconnect_expires_at)
                    valid = expiry.tzinfo is not None and expiry > now
                except (ValueError, TypeError):
                    valid = False
                if valid and hmac.compare_digest(player.reconnect_digest, digest):
                    return room, player
        return None

    def revoke(self, room_code: str, player_id: str, token: str) -> None:
        digest = hashlib.sha256(token.encode()).hexdigest()

        def clear(room):
            player = next((p for p in room.players if p.player_id == player_id), None)
            if player and player.reconnect_digest and hmac.compare_digest(player.reconnect_digest, digest):
                player.reconnect_digest = None
                player.reconnect_expires_at = None

        try:
            self.repository.update(room_code, clear)
        except KeyError:
            pass
