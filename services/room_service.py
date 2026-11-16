"""Domain logic for creating and maintaining rooms before the game starts."""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime
from typing import List, Optional

from models import (
    Player,
    PlayerRole,
    Room,
    RoomSettings,
    SUPPORTED_LANGUAGES,
)
from storage.room_repository import RoomCodeExistsError, RoomNameExistsError, RoomRepository
from services.player_emoji import emoji_key, validate_emoji


class RoomServiceError(Exception):
    """Base error for room related operations."""


class RoomNotFoundError(RoomServiceError):
    pass


class RoomAlreadyStartedError(RoomServiceError):
    pass


class RoomSettingsConflictError(RoomServiceError):
    pass


class InvalidRoomSettingsError(RoomServiceError):
    pass


class PlayerNotFoundError(RoomServiceError):
    pass


class EmojiTakenError(RoomServiceError):
    pass


class PlayerNameTakenError(RoomServiceError):
    pass


class RoomNameTakenError(RoomServiceError):
    def __init__(self, room: Room) -> None:
        self.room = room
        super().__init__("A room with this name already exists.")


class RoomService:
    """Handles room lifecycle before the in-game flow begins."""

    def __init__(self, repository: Optional[RoomRepository] = None) -> None:
        self.repository = repository or RoomRepository()

    def get_room_by_code(self, room_code: str) -> Optional[Room]:
        if not room_code:
            return None
        return self.repository.get_by_code(room_code.strip().upper())

    def get_room_by_name(self, name: str) -> Optional[Room]:
        if not name:
            return None
        return self.repository.get_by_name(name)

    def create_room(
        self,
        host_name: str,
        room_name: str,
        settings: RoomSettings,
        *,
        is_private: bool,
        emoji: Optional[str] = None,
    ) -> Room:
        """Creates a completely new room with the provided configuration."""
        self._validate_settings(settings)
        cleaned_name = room_name.strip()
        if not cleaned_name:
            raise ValueError("Room name cannot be empty.")
        now = datetime.utcnow()
        host_player = self._build_player(host_name, PlayerRole.HOST, emoji=emoji)
        room = Room(
            room_code=self._generate_room_code(),
            name=cleaned_name,
            is_private=is_private,
            host_id=host_player.player_id,
            host_name=host_player.name,
            created_at=now,
            updated_at=now,
            started=False,
            players=[host_player],
            settings=settings,
        )
        while True:
            try:
                self.repository.create(room)
                return room
            except RoomNameExistsError as exc:
                raise RoomNameTakenError(exc.room) from exc
            except RoomCodeExistsError:
                room.room_code = self._generate_room_code()

    def reuse_room(self, room: Room, host_name: str) -> Room:
        """Resets players for an existing room while keeping configuration."""
        host_player = self._build_player(host_name, PlayerRole.HOST)
        room.host_id = host_player.player_id
        room.host_name = host_player.name
        room.players = [host_player]
        room.started = False
        room.update_timestamp()
        self.repository.save(room)
        return room

    def reconfigure_room(
        self,
        room: Room,
        host_name: str,
        settings: RoomSettings,
        *,
        is_private: bool,
    ) -> Room:
        """Keeps the room code/name but overwrites settings."""
        self._validate_settings(settings)
        host_player = self._build_player(host_name, PlayerRole.HOST)
        room.host_id = host_player.player_id
        room.host_name = host_player.name
        room.players = [host_player]
        room.started = False
        room.settings = settings
        room.is_private = is_private
        room.update_timestamp()
        self.repository.save(room)
        return room

    def add_player(self, room: Room, player_name: str, *, emoji: Optional[str] = None) -> Player:
        """Adds a listener to a room if the game hasn't started."""
        normalized_name = player_name.strip().lower()
        if not normalized_name:
            raise ValueError("Player name cannot be empty.")
        if emoji is not None:
            emoji = validate_emoji(emoji)

        def join(latest: Room) -> Player:
            if latest.started:
                raise RoomAlreadyStartedError(f"Room {latest.room_code} has already started the game.")
            existing = next((p for p in latest.players if p.name.strip().lower() == normalized_name), None)
            if existing:
                raise PlayerNameTakenError("That name is already in use. Choose another name or resume your player.")
            self._check_emoji_available(latest, emoji)
            player = self._build_player(player_name, PlayerRole.JOINER, emoji=emoji)
            latest.players.append(player)
            latest.update_timestamp()
            return player

        try:
            updated, player = self.repository.update(room.room_code, join)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(updated.__dict__)
        return player

    def set_player_emoji(self, room: Room, player_id: str, emoji: str) -> Player:
        emoji = validate_emoji(emoji)

        def assign(latest: Room) -> Player:
            player = next((p for p in latest.players if p.player_id == player_id), None)
            if player is None:
                raise PlayerNotFoundError("Player no longer exists in this room.")
            self._check_emoji_available(latest, emoji, except_player_id=player_id)
            player.emoji = emoji
            latest.update_timestamp()
            return player

        try:
            updated, player = self.repository.update(room.room_code, assign)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(updated.__dict__)
        return player

    @staticmethod
    def _check_emoji_available(room: Room, emoji: Optional[str], *, except_player_id: Optional[str] = None) -> None:
        if emoji and any(p.player_id != except_player_id and p.emoji and emoji_key(p.emoji) == emoji_key(emoji)
                         for p in room.players):
            raise EmojiTakenError("That emoji was just taken. Choose another.")

    def reclaim_player(self, room: Room, player_id: str) -> Player:
        if not player_id:
            raise PlayerNotFoundError("Missing player id.")

        def reclaim(latest: Room) -> Player:
            player = next((item for item in latest.players if item.player_id == player_id), None)
            if player is None:
                raise PlayerNotFoundError("This player is no longer in the room.")
            player.is_connected = True
            latest.update_timestamp()
            return player

        try:
            latest, player = self.repository.update(room.room_code, reclaim)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return player

    def update_max_score(self, room: Room, max_score: int, *, customized: bool = True) -> Room:
        if max_score < 1:
            raise InvalidRoomSettingsError("Max score must be a positive number.")

        def update_score(latest: Room) -> None:
            if latest.started:
                raise RoomAlreadyStartedError("The game has already started.")
            latest.settings.max_score = max_score
            latest.settings.max_score_customized = customized
            latest.update_timestamp()

        try:
            latest, _ = self.repository.update(room.room_code, update_score)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def update_lobby_settings(self, room: Room, *, language: str, is_private: bool,
                              expected_language: str, expected_private: bool) -> Room:
        """Change lobby settings without replacing players or later updates."""
        if language not in SUPPORTED_LANGUAGES:
            raise InvalidRoomSettingsError("Choose an available game language.")

        def update(latest: Room) -> None:
            if latest.started:
                raise RoomAlreadyStartedError("The game has already started.")
            if (latest.host_id != room.host_id or latest.settings.language != expected_language
                    or latest.is_private != expected_private):
                raise RoomSettingsConflictError("Room settings changed while you were editing.")
            latest.settings.language = language
            latest.is_private = is_private
            latest.update_timestamp()

        try:
            latest, _ = self.repository.update(room.room_code, update)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def remove_player(self, room: Room, player_id: str) -> Room:
        """Remove a player from the current lobby without losing other updates."""
        def remove(latest: Room) -> None:
            if latest.started:
                raise RoomAlreadyStartedError("The game has already started.")
            filtered = [player for player in latest.players if player.player_id != player_id]
            if len(filtered) != len(latest.players):
                latest.players = filtered
                latest.update_timestamp()

        try:
            latest, _ = self.repository.update(room.room_code, remove)
        except KeyError as exc:
            raise RoomNotFoundError("This room is no longer available.") from exc
        room.__dict__.update(latest.__dict__)
        return room

    def _generate_room_code(self) -> str:
        alphabet = string.ascii_uppercase
        while True:
            code = "".join(random.choices(alphabet, k=5))
            if not self.repository.get_by_code(code):
                return code

    def _build_player(self, name: str, role: PlayerRole, *, emoji: Optional[str] = None) -> Player:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Player name cannot be empty.")
        return Player(
            player_id=str(uuid.uuid4()),
            name=cleaned,
            role=role,
            joined_at=datetime.utcnow(),
            emoji=validate_emoji(emoji) if emoji is not None else None,
        )

    def _validate_settings(self, settings: RoomSettings) -> None:
        if settings.max_score < 1:
            raise InvalidRoomSettingsError("Max score must be greater than zero.")

    def list_rooms(self) -> List[Room]:
        return self.repository.list_rooms()
