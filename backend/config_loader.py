import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KeyConfig:
    key: str
    weight: int = 1
    enabled: bool = True


@dataclass
class HealthCheckConfig:
    enabled: bool = True
    interval: int = 60
    endpoint: str = "/v1/models"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_ms: int = 1000


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    proxy_port: int = 8080
    gui_port: int = 8081


@dataclass
class UpstreamConfig:
    base_url: str = "https://integrate.api.nvidia.com"
    endpoint: str = "/v1/chat/completions"
    timeout: int = 900


@dataclass
class LoggingConfig:
    level: str = "info"
    file: str = "proxy.log"


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)
    keys: list[KeyConfig] = field(default_factory=list)
    strategy: str = "rpm_aware"
    rpm_limit: int = 40
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    server_raw = raw.get("server", {})
    upstream_raw = raw.get("upstream", {})
    hc_raw = raw.get("health_check", {})
    retry_raw = raw.get("retry", {})
    log_raw = raw.get("logging", {})

    keys = [
        KeyConfig(key=k["key"], weight=k.get("weight", 1), enabled=k.get("enabled", True))
        for k in raw.get("keys", [])
    ]

    return AppConfig(
        server=ServerConfig(
            host=server_raw.get("host", "127.0.0.1"),
            proxy_port=server_raw.get("proxy_port", 8080),
            gui_port=server_raw.get("gui_port", 8081),
        ),
        upstream=UpstreamConfig(
            base_url=upstream_raw.get("base_url", "https://integrate.api.nvidia.com"),
            endpoint=upstream_raw.get("endpoint", "/v1/chat/completions"),
            timeout=upstream_raw.get("timeout", 30),
        ),
        keys=keys,
        strategy=raw.get("strategy", "rpm_aware"),
        rpm_limit=raw.get("rpm_limit", 40),
        health_check=HealthCheckConfig(
            enabled=hc_raw.get("enabled", True),
            interval=hc_raw.get("interval", 60),
            endpoint=hc_raw.get("endpoint", "/v1/models"),
        ),
        retry=RetryConfig(
            max_attempts=retry_raw.get("max_attempts", 3),
            backoff_ms=retry_raw.get("backoff_ms", 1000),
        ),
        logging=LoggingConfig(
            level=log_raw.get("level", "info"),
            file=log_raw.get("file", "proxy.log"),
        ),
    )


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    data = {
        "server": {
            "host": config.server.host,
            "proxy_port": config.server.proxy_port,
            "gui_port": config.server.gui_port,
        },
        "upstream": {
            "base_url": config.upstream.base_url,
            "endpoint": config.upstream.endpoint,
            "timeout": config.upstream.timeout,
        },
        "keys": [
            {"key": k.key, "weight": k.weight, "enabled": k.enabled}
            for k in config.keys
        ],
        "strategy": config.strategy,
        "rpm_limit": config.rpm_limit,
        "health_check": {
            "enabled": config.health_check.enabled,
            "interval": config.health_check.interval,
            "endpoint": config.health_check.endpoint,
        },
        "retry": {
            "max_attempts": config.retry.max_attempts,
            "backoff_ms": config.retry.backoff_ms,
        },
        "logging": {
            "level": config.logging.level,
            "file": config.logging.file,
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
