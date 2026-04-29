import asyncio
import logging

import httpx

from .config_loader import AppConfig
from .key_pool import KeyPool

logger = logging.getLogger("health_checker")


class HealthChecker:
    def __init__(self, config: AppConfig, key_pool: KeyPool):
        self.config = config
        self.key_pool = key_pool
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        if not self.config.health_check.enabled:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Health checker started, interval={self.config.health_check.interval}s"
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        async with httpx.AsyncClient(timeout=10) as client:
            while self._running:
                try:
                    await self._check_all(client)
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                await asyncio.sleep(self.config.health_check.interval)

    async def _check_all(self, client: httpx.AsyncClient):
        url = f"{self.config.upstream.base_url.rstrip('/')}{self.config.health_check.endpoint}"
        keys = await self.key_pool.get_all()

        for key_info in keys:
            full_key = key_info["full_key"]
            try:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {full_key}"},
                )
                if resp.status_code == 200:
                    await self.key_pool.health_check_reset(full_key)
                    logger.debug(f"Health check OK: {key_info['key']}")
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", "60"))
                    await self.key_pool.report_rate_limited(full_key, retry_after)
                    logger.warning(f"Health check rate limited: {key_info['key']}")
                elif resp.status_code in (401, 403):
                    await self.key_pool.report_auth_failed(full_key, f"HTTP {resp.status_code}")
                    logger.warning(f"Health check auth failed: {key_info['key']}")
                else:
                    logger.debug(
                        f"Health check {resp.status_code}: {key_info['key']}"
                    )
            except Exception as e:
                logger.warning(f"Health check failed for {key_info['key']}: {e}")
