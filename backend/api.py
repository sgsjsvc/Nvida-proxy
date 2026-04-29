import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config_loader import AppConfig, load_config, save_config
from .key_pool import KeyPool
from .database import Database
from .ws_manager import WebSocketManager


class KeyCreate(BaseModel):
    key: str
    weight: int = 1
    enabled: bool = True


class KeyUpdate(BaseModel):
    weight: Optional[int] = None
    enabled: Optional[bool] = None


class StrategyUpdate(BaseModel):
    strategy: str

class TimeoutUpdate(BaseModel):
    timeout: int


def create_gui_app(
    config: AppConfig,
    config_path: str,
    key_pool: KeyPool,
    db: Database,
    ws_manager: WebSocketManager,
) -> FastAPI:
    app = FastAPI(title="NVIDIA API Pool Manager")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/keys")
    async def list_keys():
        return await key_pool.get_all()

    @app.post("/api/keys", status_code=201)
    async def add_key(data: KeyCreate):
        existing = await key_pool.get_all()
        for k in existing:
            if k["full_key"] == data.key:
                raise HTTPException(400, "Key already exists")
        await key_pool.add_key(data.key, data.weight, data.enabled)
        config.keys.append(
            __import__("backend.config_loader", fromlist=["KeyConfig"]).KeyConfig(
                key=data.key, weight=data.weight, enabled=data.enabled
            )
        )
        save_config(config_path, config)
        keys = await key_pool.get_all()
        await ws_manager.broadcast_keys(keys)
        return {"status": "ok"}

    @app.delete("/api/keys/{key_id}")
    async def delete_key(key_id: str):
        import urllib.parse
        full_key = urllib.parse.unquote(key_id)
        for k in config.keys:
            if k.key == full_key:
                await key_pool.remove_key(k.key)
                config.keys.remove(k)
                save_config(config_path, config)
                keys = await key_pool.get_all()
                await ws_manager.broadcast_keys(keys)
                return {"status": "ok"}
        raise HTTPException(404, "Key not found")

    @app.patch("/api/keys/{key_id}")
    async def update_key(key_id: str, data: KeyUpdate):
        import urllib.parse
        full_key = urllib.parse.unquote(key_id)
        for k in config.keys:
            if k.key == full_key:
                kwargs = {}
                if data.weight is not None:
                    kwargs["weight"] = data.weight
                    k.weight = data.weight
                if data.enabled is not None:
                    kwargs["enabled"] = data.enabled
                    k.enabled = data.enabled
                await key_pool.update_key(k.key, **kwargs)
                save_config(config_path, config)
                keys = await key_pool.get_all()
                await ws_manager.broadcast_keys(keys)
                return {"status": "ok"}
        raise HTTPException(404, "Key not found")

    @app.post("/api/keys/{key_id}/reset")
    async def reset_key(key_id: str):
        import urllib.parse
        full_key = urllib.parse.unquote(key_id)
        for k in config.keys:
            if k.key == full_key:
                await key_pool.reset_key(k.key)
                keys = await key_pool.get_all()
                await ws_manager.broadcast_keys(keys)
                return {"status": "ok"}
        raise HTTPException(404, "Key not found")

    @app.get("/api/stats")
    async def get_stats():
        pool_stats = await key_pool.get_stats()
        hourly = await db.get_hourly_stats(24)
        key_usage = await db.get_key_usage_stats(24)
        token_totals = await db.get_token_totals()
        token_by_key = await db.get_token_by_key()
        token_by_model = await db.get_token_by_model()
        token_hourly = await db.get_token_hourly(24)
        return {
            "pool": pool_stats,
            "hourly": hourly,
            "key_usage": key_usage,
            "token": {
                "totals": token_totals,
                "by_key": token_by_key,
                "by_model": token_by_model,
                "hourly": token_hourly,
            },
        }

    @app.get("/api/logs")
    async def get_logs(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        key: Optional[str] = None,
        status: Optional[int] = None,
    ):
        logs = await db.get_logs(limit, offset, key, status)
        total = await db.get_log_count(key, status)
        return {"logs": logs, "total": total}

    @app.get("/api/config")
    async def get_config():
        return {
            "strategy": config.strategy,
            "rpm_limit": config.rpm_limit,
            "health_check": {
                "enabled": config.health_check.enabled,
                "interval": config.health_check.interval,
            },
            "retry": {
                "max_attempts": config.retry.max_attempts,
                "backoff_ms": config.retry.backoff_ms,
            },
            "upstream": {
                "base_url": config.upstream.base_url,
                "endpoint": config.upstream.endpoint,
                "timeout": config.upstream.timeout,
            },
        }

    @app.put("/api/config/strategy")
    async def update_strategy(data: StrategyUpdate):
        valid = ["round_robin", "weighted_round_robin", "least_used", "rpm_aware"]
        if data.strategy not in valid:
            raise HTTPException(400, f"Invalid strategy, must be one of: {valid}")
        config.strategy = data.strategy
        await key_pool.set_strategy(data.strategy)
        save_config(config_path, config)
        return {"status": "ok", "strategy": data.strategy}

    @app.put("/api/config/timeout")
    async def update_timeout(data: TimeoutUpdate):
        if data.timeout < 0:
            raise HTTPException(400, "Timeout must be >= 0")
        config.upstream.timeout = data.timeout
        save_config(config_path, config)
        return {"status": "ok", "timeout": data.timeout}

    @app.get("/api/models")
    async def get_models(search: Optional[str] = None):
        """Get models from local DB, optionally filtered by search query."""
        models = await db.get_models(search)
        count = await db.get_model_count()
        return {"models": models, "total": count}

    @app.post("/api/models/fetch")
    async def fetch_models():
        """Fetch models from NVIDIA API and persist to DB."""
        key_state = await key_pool.get_next()
        if not key_state:
            raise HTTPException(503, "No available API keys")
        api_key = key_state.config.key
        url = f"{config.upstream.base_url.rstrip('/')}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {api_key}"}
                )
            if resp.status_code == 200:
                data = resp.json()
                model_ids = sorted(set(m.get("id", "") for m in data.get("data", []) if m.get("id")))
                await db.save_models(model_ids)
                return {"count": len(model_ids)}
            else:
                raise HTTPException(resp.status_code, f"Upstream error: {resp.text[:200]}")
        except Exception as e:
            raise HTTPException(502, str(e))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            keys = await key_pool.get_all()
            stats = await key_pool.get_stats()
            await websocket.send_json({"type": "keys", "data": keys})
            await websocket.send_json({"type": "stats", "data": stats})
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)

    @app.post("/api/chat")
    async def chat_proxy(request: Request):
        """Proxy chat completions for the GUI chat interface."""
        body = await request.body()
        max_attempts = config.retry.max_attempts

        for attempt in range(max_attempts):
            key_state = await key_pool.get_next()
            if not key_state:
                raise HTTPException(503, "No available API keys")

            api_key = key_state.config.key
            url = f"{config.upstream.base_url.rstrip('/')}{config.upstream.endpoint}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                timeout_cfg = None if config.upstream.timeout == 0 else httpx.Timeout(config.upstream.timeout)
                async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                    resp = await client.post(url, headers=headers, content=body)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", "60"))
                    await key_pool.report_rate_limited(api_key, retry_after)
                    if attempt < max_attempts - 1:
                        continue
                    return Response(
                        content=resp.content, status_code=429, media_type="application/json"
                    )

                if resp.status_code in (401, 403):
                    await key_pool.report_auth_failed(api_key, f"HTTP {resp.status_code}")
                    if attempt < max_attempts - 1:
                        continue
                    return Response(
                        content=resp.content, status_code=resp.status_code, media_type="application/json"
                    )

                await key_pool.report_success(api_key)
                keys = await key_pool.get_all()
                await ws_manager.broadcast_keys(keys)

                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type="application/json",
                )

            except Exception as e:
                await key_pool.report_error(api_key, str(e))
                if attempt < max_attempts - 1:
                    continue
                raise HTTPException(502, str(e))

    # Serve frontend static files in production
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and (static_dir / "index.html").exists():
        @app.get("/")
        async def serve_index():
            return FileResponse(static_dir / "index.html")

        @app.get("/assets/{file_path:path}")
        async def serve_assets(file_path: str):
            return FileResponse(static_dir / "assets" / file_path)

    return app
