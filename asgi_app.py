"""Single-process Streamlit launcher with a same-origin realtime channel."""
import asyncio
from pathlib import Path

import streamlit as st
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from services.reconnect_service import ReconnectService
from storage.room_repository import RoomRepository


async def realtime(websocket):
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")
    if origin not in (f"http://{host}", f"https://{host}"):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        token = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        repository = RoomRepository()
        reconnect = ReconnectService(repository)
        identity = await asyncio.to_thread(reconnect.resolve, token)
        if not identity:
            await websocket.send_text("invalid")
            await websocket.close(code=1008)
            return
        room, _ = identity
        notifications = repository.notifications
        key = repository.notification_key
        subscriber = notifications.subscribe(key, room.room_code)
        version = notifications.version(key, room.room_code)
        try:
            # Always resynchronise after connecting, including after missed events.
            await websocket.send_text("sync")
            while True:
                try:
                    await asyncio.wait_for(subscriber[1].wait(), timeout=20)
                except asyncio.TimeoutError:
                    if not await asyncio.to_thread(reconnect.resolve, token):
                        await websocket.send_text("invalid")
                        await websocket.close(code=1008)
                        return
                    await websocket.send_text("ping")
                    continue
                subscriber[1].clear()
                next_version = notifications.version(key, room.room_code)
                if next_version != version:
                    version = next_version
                    await websocket.send_text("sync")
                    if not await asyncio.to_thread(reconnect.resolve, token):
                        await websocket.send_text("invalid")
                        await websocket.close(code=1008)
                        return
        finally:
            notifications.unsubscribe(key, room.room_code, subscriber)
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
        pass


app = st.App(Path(__file__).parent / "app.py", routes=[WebSocketRoute("/api/realtime", realtime)])
