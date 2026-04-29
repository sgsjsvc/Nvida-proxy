import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class WebSocketManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"WebSocket connected, total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected, total: {len(self._connections)}")

    async def broadcast(self, message: dict):
        if not self._connections:
            return
        data = json.dumps(message, default=str)
        dead = set()
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.add(ws)
            self._connections -= dead

    async def broadcast_log(self, log_entry: dict):
        await self.broadcast({"type": "log", "data": log_entry})

    async def broadcast_stats(self, stats: dict):
        await self.broadcast({"type": "stats", "data": stats})

    async def broadcast_keys(self, keys: list):
        await self.broadcast({"type": "keys", "data": keys})

    @property
    def connection_count(self) -> int:
        return len(self._connections)
