import time
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger("database")

DB_PATH = Path(__file__).parent.parent / "data" / "proxy.db"


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or str(DB_PATH)
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()
        await self._migrate()

    async def close(self):
        if self._db:
            await self._db.close()

    async def _create_tables(self):
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                method TEXT NOT NULL,
                url TEXT NOT NULL,
                status INTEGER NOT NULL,
                elapsed REAL NOT NULL,
                masked_key TEXT NOT NULL,
                result TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'unknown'
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON request_logs(timestamp)
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                fetched_at REAL NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                masked_key TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_timestamp ON token_usage(timestamp)
        """)
        await self._db.commit()

    async def insert_log(self, entry: dict):
        await self._db.execute(
            """INSERT INTO request_logs (timestamp, method, url, status, elapsed, masked_key, result, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["timestamp"],
                entry["method"],
                entry["url"],
                entry["status"],
                entry["elapsed"],
                entry["key"],
                entry["result"],
                entry.get("model", "unknown"),
            ),
        )
        await self._db.commit()

    async def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        key_filter: Optional[str] = None,
        status_filter: Optional[int] = None,
    ) -> list[dict]:
        query = "SELECT * FROM request_logs WHERE 1=1"
        params = []
        if key_filter:
            query += " AND masked_key = ?"
            params.append(key_filter)
        if status_filter is not None:
            query += " AND status = ?"
            params.append(status_filter)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_log_count(
        self,
        key_filter: Optional[str] = None,
        status_filter: Optional[int] = None,
    ) -> int:
        query = "SELECT COUNT(*) as cnt FROM request_logs WHERE 1=1"
        params = []
        if key_filter:
            query += " AND masked_key = ?"
            params.append(key_filter)
        if status_filter is not None:
            query += " AND status = ?"
            params.append(status_filter)
        cursor = await self._db.execute(query, params)
        row = await cursor.fetchone()
        return row[0]

    async def get_hourly_stats(self, hours: int = 24) -> list[dict]:
        since = time.time() - hours * 3600
        cursor = await self._db.execute(
            """SELECT
                 CAST((timestamp / 3600) * 3600 AS INTEGER) as hour_ts,
                 COUNT(*) as total,
                 SUM(CASE WHEN result = 'success' OR result = 'stream_done' THEN 1 ELSE 0 END) as success,
                 SUM(CASE WHEN result = 'rate_limited' THEN 1 ELSE 0 END) as rate_limited,
                 AVG(elapsed) as avg_elapsed
               FROM request_logs
               WHERE timestamp >= ?
               GROUP BY hour_ts
               ORDER BY hour_ts""",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_key_usage_stats(self, hours: int = 24) -> list[dict]:
        since = time.time() - hours * 3600
        cursor = await self._db.execute(
            """SELECT
                 masked_key,
                 COUNT(*) as total,
                 SUM(CASE WHEN result = 'success' OR result = 'stream_done' THEN 1 ELSE 0 END) as success,
                 SUM(CASE WHEN result = 'rate_limited' THEN 1 ELSE 0 END) as rate_limited,
                 SUM(CASE WHEN result = 'error' THEN 1 ELSE 0 END) as errors,
                 AVG(elapsed) as avg_elapsed
               FROM request_logs
               WHERE timestamp >= ?
               GROUP BY masked_key
               ORDER BY total DESC""",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def cleanup_old_logs(self, days: int = 7):
        cutoff = time.time() - days * 86400
        await self._db.execute(
            "DELETE FROM request_logs WHERE timestamp < ?", (cutoff,)
        )
        await self._db.execute(
            "DELETE FROM token_usage WHERE timestamp < ?", (cutoff,)
        )
        await self._db.commit()

    async def _migrate(self):
        """Add columns to existing tables if missing."""
        cursor = await self._db.execute("PRAGMA table_info(request_logs)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "model" not in columns:
            await self._db.execute(
                "ALTER TABLE request_logs ADD COLUMN model TEXT NOT NULL DEFAULT 'unknown'"
            )
            await self._db.commit()

    async def insert_token_usage(self, masked_key: str, model: str,
                                  prompt_tokens: int, completion_tokens: int, total_tokens: int):
        await self._db.execute(
            """INSERT INTO token_usage (timestamp, masked_key, model, prompt_tokens, completion_tokens, total_tokens)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (time.time(), masked_key, model, prompt_tokens, completion_tokens, total_tokens),
        )
        await self._db.commit()

    async def get_token_totals(self) -> dict:
        cursor = await self._db.execute(
            """SELECT
                 COUNT(*) as total_requests,
                 COALESCE(SUM(prompt_tokens), 0) as total_prompt,
                 COALESCE(SUM(completion_tokens), 0) as total_completion,
                 COALESCE(SUM(total_tokens), 0) as total_tokens
               FROM token_usage"""
        )
        row = await cursor.fetchone()
        return dict(row)

    async def get_token_by_key(self) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT masked_key,
                 COUNT(*) as requests,
                 SUM(prompt_tokens) as prompt_tokens,
                 SUM(completion_tokens) as completion_tokens,
                 SUM(total_tokens) as total_tokens
               FROM token_usage
               GROUP BY masked_key
               ORDER BY total_tokens DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_token_by_model(self) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT model,
                 COUNT(*) as requests,
                 SUM(prompt_tokens) as prompt_tokens,
                 SUM(completion_tokens) as completion_tokens,
                 SUM(total_tokens) as total_tokens
               FROM token_usage
               GROUP BY model
               ORDER BY total_tokens DESC
               LIMIT 20"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_token_hourly(self, hours: int = 24) -> list[dict]:
        since = time.time() - hours * 3600
        cursor = await self._db.execute(
            """SELECT
                 CAST((timestamp / 3600) * 3600 AS INTEGER) as hour_ts,
                 SUM(prompt_tokens) as prompt_tokens,
                 SUM(completion_tokens) as completion_tokens,
                 SUM(total_tokens) as total_tokens
               FROM token_usage
               WHERE timestamp >= ?
               GROUP BY hour_ts
               ORDER BY hour_ts""",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_models(self, model_ids: list[str]):
        """Replace all models with new list."""
        now = time.time()
        await self._db.execute("DELETE FROM models")
        await self._db.executemany(
            "INSERT INTO models (id, fetched_at) VALUES (?, ?)",
            [(mid, now) for mid in model_ids],
        )
        await self._db.commit()

    async def get_models(self, search: Optional[str] = None) -> list[dict]:
        query = "SELECT id, fetched_at FROM models"
        params = []
        if search:
            query += " WHERE id LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY id ASC"
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_model_count(self) -> int:
        cursor = await self._db.execute("SELECT COUNT(*) FROM models")
        row = await cursor.fetchone()
        return row[0]
