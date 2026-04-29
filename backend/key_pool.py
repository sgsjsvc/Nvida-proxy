import time
import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .config_loader import KeyConfig


class KeyStatus(Enum):
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    DISABLED = "disabled"


@dataclass
class KeyState:
    config: KeyConfig
    status: KeyStatus = KeyStatus.HEALTHY
    use_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0
    last_error: Optional[str] = None
    cooldown_until: float = 0.0
    # RPM tracking: timestamps of requests in the last 60 seconds
    _request_timestamps: deque = field(default_factory=deque)
    rpm_limit: int = 40  # requests per minute limit

    @property
    def available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.status == KeyStatus.DISABLED:
            return False
        if self.status == KeyStatus.AUTH_FAILED:
            return False
        if self.cooldown_until > time.time():
            return False
        return True

    @property
    def current_rpm(self) -> int:
        """Count of requests in the last 60 seconds."""
        now = time.time()
        cutoff = now - 60.0
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()
        return len(self._request_timestamps)

    @property
    def rpm_available(self) -> bool:
        """Whether this key can accept more requests under RPM limit."""
        return self.current_rpm < self.rpm_limit

    @property
    def masked_key(self) -> str:
        k = self.config.key
        if len(k) <= 12:
            return k[:4] + "***"
        return k[:8] + "***" + k[-4:]

    @property
    def error_rate(self) -> float:
        if self.use_count == 0:
            return 0.0
        return self.fail_count / self.use_count

    def record_request(self):
        """Record a request timestamp for RPM tracking."""
        now = time.time()
        self._request_timestamps.append(now)
        # Clean old entries beyond 60s
        cutoff = now - 60.0
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

    def to_dict(self) -> dict:
        return {
            "key": self.masked_key,
            "full_key": self.config.key,
            "weight": self.config.weight,
            "enabled": self.config.enabled,
            "status": self.status.value,
            "available": self.available,
            "rpm_available": self.rpm_available,
            "current_rpm": self.current_rpm,
            "rpm_limit": self.rpm_limit,
            "use_count": self.use_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "error_rate": round(self.error_rate * 100, 2),
            "last_used": self.last_used,
            "last_error": self.last_error,
        }


class Strategy(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_USED = "least_used"
    RPM_AWARE = "rpm_aware"


class KeyPool:
    def __init__(self, keys: list[KeyConfig], strategy: str = "round_robin", rpm_limit: int = 40):
        self._lock = asyncio.Lock()
        self._keys: list[KeyState] = []
        for k in keys:
            ks = KeyState(config=k)
            ks.rpm_limit = rpm_limit
            self._keys.append(ks)
        self._strategy = Strategy(strategy)
        self._rr_index = 0
        self._wrr_sequence: list[int] = []
        self._wrr_pos = 0
        self._rebuild_wrr()

    def _rebuild_wrr(self):
        self._wrr_sequence = []
        for i, ks in enumerate(self._keys):
            if ks.available and ks.rpm_available:
                self._wrr_sequence.extend([i] * ks.config.weight)
        self._wrr_pos = 0

    def _available_keys(self) -> list[KeyState]:
        """Get all keys that are available AND under RPM limit."""
        return [ks for ks in self._keys if ks.available and ks.rpm_available]

    async def add_key(self, key: str, weight: int = 1, enabled: bool = True) -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    return
            cfg = KeyConfig(key=key, weight=weight, enabled=enabled)
            ks = KeyState(config=cfg)
            ks.rpm_limit = self._keys[0].rpm_limit if self._keys else 40
            self._keys.append(ks)
            self._rebuild_wrr()

    async def remove_key(self, key: str) -> bool:
        async with self._lock:
            for i, ks in enumerate(self._keys):
                if ks.config.key == key:
                    self._keys.pop(i)
                    self._rebuild_wrr()
                    return True
            return False

    async def update_key(self, key: str, **kwargs) -> bool:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    if "weight" in kwargs:
                        ks.config.weight = kwargs["weight"]
                    if "enabled" in kwargs:
                        ks.config.enabled = kwargs["enabled"]
                        if not kwargs["enabled"]:
                            ks.status = KeyStatus.DISABLED
                        elif ks.status == KeyStatus.DISABLED:
                            ks.status = KeyStatus.HEALTHY
                    if "rpm_limit" in kwargs:
                        ks.rpm_limit = kwargs["rpm_limit"]
                    self._rebuild_wrr()
                    return True
            return False

    async def get_next(self) -> Optional[KeyState]:
        async with self._lock:
            available = self._available_keys()
            if not available:
                # Fallback: if all keys hit RPM limit, pick the one with lowest current RPM
                # that is still healthy/enabled (ignore rpm_available)
                fallback = [ks for ks in self._keys if ks.available]
                if not fallback:
                    return None
                available = fallback

            if self._strategy == Strategy.ROUND_ROBIN:
                return self._get_round_robin(available)
            elif self._strategy == Strategy.WEIGHTED_ROUND_ROBIN:
                return self._get_weighted_round_robin(available)
            elif self._strategy == Strategy.LEAST_USED:
                return self._get_least_used(available)
            elif self._strategy == Strategy.RPM_AWARE:
                return self._get_rpm_aware(available)
            return self._get_rpm_aware(available)

    def _get_round_robin(self, available: list[KeyState]) -> KeyState:
        all_available = self._available_keys()
        if not all_available:
            all_available = [ks for ks in self._keys if ks.available]
        if not all_available:
            return available[0]
        idx = self._rr_index % len(all_available)
        self._rr_index += 1
        return all_available[idx]

    def _get_weighted_round_robin(self, available: list[KeyState]) -> KeyState:
        self._rebuild_wrr()
        if not self._wrr_sequence:
            return available[0]
        idx = self._wrr_sequence[self._wrr_pos % len(self._wrr_sequence)]
        self._wrr_pos += 1
        return self._keys[idx]

    def _get_least_used(self, available: list[KeyState]) -> KeyState:
        return min(available, key=lambda ks: ks.use_count)

    def _get_rpm_aware(self, available: list[KeyState]) -> KeyState:
        """Pick the key with the most remaining RPM headroom."""
        return max(available, key=lambda ks: ks.rpm_limit - ks.current_rpm)

    async def report_success(self, key: str) -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    ks.use_count += 1
                    ks.success_count += 1
                    ks.last_used = time.time()
                    ks.record_request()
                    if ks.status == KeyStatus.RATE_LIMITED:
                        ks.status = KeyStatus.HEALTHY
                        ks.cooldown_until = 0.0
                    self._rebuild_wrr()
                    break

    async def report_rate_limited(self, key: str, retry_after: int = 60) -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    ks.use_count += 1
                    ks.fail_count += 1
                    ks.status = KeyStatus.RATE_LIMITED
                    ks.last_error = "429 Rate Limited"
                    ks.last_used = time.time()
                    ks.cooldown_until = time.time() + retry_after
                    self._rebuild_wrr()
                    break

    async def report_auth_failed(self, key: str, error: str = "") -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    ks.use_count += 1
                    ks.fail_count += 1
                    ks.status = KeyStatus.AUTH_FAILED
                    ks.last_error = f"Auth failed: {error}"
                    ks.last_used = time.time()
                    self._rebuild_wrr()
                    break

    async def report_error(self, key: str, error: str) -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    ks.use_count += 1
                    ks.fail_count += 1
                    ks.last_error = error
                    ks.last_used = time.time()
                    break

    async def reset_key(self, key: str) -> bool:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key:
                    ks.status = KeyStatus.HEALTHY
                    ks.cooldown_until = 0.0
                    ks.last_error = None
                    ks._request_timestamps.clear()
                    self._rebuild_wrr()
                    return True
            return False

    async def get_all(self) -> list[dict]:
        async with self._lock:
            return [ks.to_dict() for ks in self._keys]

    async def get_stats(self) -> dict:
        async with self._lock:
            total = len(self._keys)
            available = sum(1 for ks in self._keys if ks.available and ks.rpm_available)
            total_requests = sum(ks.use_count for ks in self._keys)
            total_success = sum(ks.success_count for ks in self._keys)
            total_fail = sum(ks.fail_count for ks in self._keys)
            return {
                "total_keys": total,
                "available_keys": available,
                "total_requests": total_requests,
                "total_success": total_success,
                "total_fail": total_fail,
                "strategy": self._strategy.value,
            }

    async def health_check_reset(self, key: str) -> None:
        async with self._lock:
            for ks in self._keys:
                if ks.config.key == key and ks.status == KeyStatus.RATE_LIMITED:
                    if ks.cooldown_until <= time.time():
                        ks.status = KeyStatus.HEALTHY
                        ks.cooldown_until = 0.0
                        self._rebuild_wrr()
                    break

    @property
    def strategy(self) -> Strategy:
        return self._strategy

    async def set_strategy(self, strategy: str) -> None:
        async with self._lock:
            self._strategy = Strategy(strategy)
            self._rr_index = 0
            self._wrr_pos = 0
            self._rebuild_wrr()
