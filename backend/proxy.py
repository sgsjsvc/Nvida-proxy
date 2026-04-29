import time
import json
import asyncio
import logging
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from .config_loader import AppConfig
from .key_pool import KeyPool
from .database import Database

logger = logging.getLogger("proxy")


class ProxyServer:
    def __init__(self, config: AppConfig, key_pool: KeyPool, log_callback=None, db: Database = None):
        self.config = config
        self.key_pool = key_pool
        self._client: Optional[httpx.AsyncClient] = None
        self._log_callback = log_callback
        self._db = db

    async def start(self):
        timeout_val = self.config.upstream.timeout
        # 0 means no timeout
        timeout_cfg = None if timeout_val == 0 else httpx.Timeout(timeout_val)
        self._client = httpx.AsyncClient(
            timeout=timeout_cfg,
            http2=False,
        )

    async def stop(self):
        if self._client:
            await self._client.aclose()

    def _build_upstream_url(self) -> str:
        base = self.config.upstream.base_url.rstrip("/")
        endpoint = self.config.upstream.endpoint
        return f"{base}{endpoint}"

    async def handle_request(self, request: Request) -> Response:
        max_attempts = self.config.retry.max_attempts
        last_error = None

        body = await request.body()
        headers_to_forward = {}
        for h in ["content-type", "accept", "user-agent"]:
            val = request.headers.get(h)
            if val:
                headers_to_forward[h] = val

        # Extract model from request body for logging
        req_model = "unknown"
        try:
            body_json = json.loads(body) if body else {}
            req_model = body_json.get("model", "unknown")
            is_stream = body_json.get("stream", False)
        except Exception:
            is_stream = False

        for attempt in range(max_attempts):
            key_state = await self.key_pool.get_next()
            if not key_state:
                return Response(
                    content='{"error": "No available API keys"}',
                    status_code=503,
                    media_type="application/json",
                )

            api_key = key_state.config.key
            url = self._build_upstream_url()
            headers = {**headers_to_forward, "Authorization": f"Bearer {api_key}"}

            start_time = time.time()

            try:
                if is_stream:
                    return await self._handle_stream(
                        url, headers, body, key_state, start_time, req_model
                    )
                else:
                    resp = await self._client.post(url, headers=headers, content=body)
                    elapsed = round(time.time() - start_time, 3)

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", "60"))
                        await self.key_pool.report_rate_limited(api_key, retry_after)
                        await self._emit_log(
                            "POST", url, 429, elapsed, key_state.masked_key, "rate_limited", req_model
                        )
                        last_error = "429 rate limited"
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(self.config.retry.backoff_ms / 1000)
                            continue
                        return Response(
                            content=resp.content,
                            status_code=429,
                            media_type="application/json",
                        )

                    if resp.status_code in (401, 403):
                        await self.key_pool.report_auth_failed(
                            api_key, f"HTTP {resp.status_code}"
                        )
                        await self._emit_log(
                            "POST", url, resp.status_code, elapsed,
                            key_state.masked_key, "auth_failed", req_model
                        )
                        last_error = f"{resp.status_code} auth failed"
                        if attempt < max_attempts - 1:
                            continue
                        return Response(
                            content=resp.content,
                            status_code=resp.status_code,
                            media_type="application/json",
                        )

                    await self.key_pool.report_success(api_key)
                    await self._emit_log(
                        "POST", url, resp.status_code, elapsed, key_state.masked_key, "success", req_model
                    )

                    # Parse token usage from response
                    await self._record_token_usage(resp.content, key_state.masked_key)

                    return Response(
                        content=resp.content,
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                        media_type=resp.headers.get("content-type", "application/json"),
                    )

            except httpx.TimeoutException:
                elapsed = round(time.time() - start_time, 3)
                await self.key_pool.report_error(api_key, "timeout")
                await self._emit_log(
                    "POST", url, 0, elapsed, key_state.masked_key, "timeout", req_model
                )
                last_error = "timeout"
                if attempt < max_attempts - 1:
                    continue

            except httpx.RequestError as e:
                elapsed = round(time.time() - start_time, 3)
                await self.key_pool.report_error(api_key, str(e))
                await self._emit_log(
                    "POST", url, 0, elapsed, key_state.masked_key, "error", req_model
                )
                last_error = str(e)
                if attempt < max_attempts - 1:
                    continue

        return Response(
            content=f'{{"error": "All retry attempts failed: {last_error}"}}',
            status_code=502,
            media_type="application/json",
        )

    async def _handle_stream(self, url, headers, body, key_state, start_time, req_model="unknown"):
        api_key = key_state.config.key

        try:
            req = self._client.build_request(
                method="POST", url=url, headers=headers, content=body
            )
            resp = await self._client.send(req, stream=True)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", "60"))
                await resp.aclose()
                await self.key_pool.report_rate_limited(api_key, retry_after)
                elapsed = round(time.time() - start_time, 3)
                await self._emit_log(
                    "POST", url, 429, elapsed, key_state.masked_key, "rate_limited", req_model
                )
                raise RetryableError("429 rate limited")

            if resp.status_code in (401, 403):
                await resp.aclose()
                await self.key_pool.report_auth_failed(api_key, f"HTTP {resp.status_code}")
                elapsed = round(time.time() - start_time, 3)
                await self._emit_log(
                    "POST", url, resp.status_code, elapsed, key_state.masked_key, "auth_failed", req_model
                )
                raise RetryableError(f"{resp.status_code} auth failed")

            if resp.status_code != 200:
                await resp.aclose()
                await self.key_pool.report_error(api_key, f"HTTP {resp.status_code}")
                elapsed = round(time.time() - start_time, 3)
                await self._emit_log(
                    "POST", url, resp.status_code, elapsed, key_state.masked_key, "error", req_model
                )
                raise RetryableError(f"HTTP {resp.status_code}")

            await self.key_pool.report_success(api_key)

            content_type = resp.headers.get("content-type", "text/event-stream")

            # State for collecting token usage from SSE chunks
            sse_buffer = ""
            collected_usage = {"model": req_model, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            async def stream_generator():
                nonlocal sse_buffer
                try:
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        # Parse SSE lines to extract token usage
                        sse_buffer += chunk.decode("utf-8", errors="ignore")
                        while "\n" in sse_buffer:
                            line, sse_buffer = sse_buffer.split("\n", 1)
                            line = line.strip()
                            if line.startswith("data: ") and line != "data: [DONE]":
                                try:
                                    data = json.loads(line[6:])
                                    if data.get("model"):
                                        collected_usage["model"] = data["model"]
                                    usage = data.get("usage")
                                    if usage:
                                        collected_usage["prompt_tokens"] = usage.get("prompt_tokens", 0)
                                        collected_usage["completion_tokens"] = usage.get("completion_tokens", 0)
                                        collected_usage["total_tokens"] = usage.get("total_tokens", 0)
                                except (json.JSONDecodeError, KeyError):
                                    pass
                        yield chunk
                finally:
                    elapsed = round(time.time() - start_time, 3)
                    await self._emit_log(
                        "POST", url, 200, elapsed, key_state.masked_key, "stream_done", req_model
                    )
                    # Record token usage from collected SSE data
                    if self._db and collected_usage["total_tokens"] > 0:
                        await self._db.insert_token_usage(
                            key_state.masked_key,
                            collected_usage["model"],
                            collected_usage["prompt_tokens"],
                            collected_usage["completion_tokens"],
                            collected_usage["total_tokens"],
                        )

            return StreamingResponse(
                stream_generator(),
                status_code=200,
                media_type=content_type,
                headers={
                    k: v for k, v in resp.headers.items()
                    if k.lower() in ("content-type", "cache-control", "connection", "x-request-id")
                },
            )

        except RetryableError:
            raise

    async def _emit_log(self, method, url, status, elapsed, masked_key, result, model="unknown"):
        entry = {
            "timestamp": time.time(),
            "method": method,
            "url": url,
            "status": status,
            "elapsed": elapsed,
            "key": masked_key,
            "result": result,
            "model": model,
        }
        if self._log_callback:
            await self._log_callback(entry)
        logger.info(f"{method} {url} {status} {elapsed}s {masked_key} [{result}] model={model}")

    async def _record_token_usage(self, content: bytes, masked_key: str):
        if not self._db:
            return
        try:
            data = json.loads(content)
            usage = data.get("usage", {})
            model = data.get("model", "unknown")
            prompt = usage.get("prompt_tokens", 0)
            completion = usage.get("completion_tokens", 0)
            total = usage.get("total_tokens", prompt + completion)
            if total > 0:
                await self._db.insert_token_usage(masked_key, model, prompt, completion, total)
        except Exception:
            pass


class RetryableError(Exception):
    pass
