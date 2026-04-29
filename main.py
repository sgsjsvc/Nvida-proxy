import argparse
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is in sys.path for embedded Python
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from fastapi import FastAPI, Request, Response

from backend.config_loader import load_config
from backend.key_pool import KeyPool
from backend.proxy import ProxyServer
from backend.database import Database
from backend.health_checker import HealthChecker
from backend.ws_manager import WebSocketManager
from backend.api import create_gui_app


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_proxy(config, config_path, key_pool, db, health_checker, ws_manager):
    proxy = ProxyServer(config, key_pool, log_callback=db.insert_log, db=db)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await proxy.start()
        await health_checker.start()
        logging.getLogger("main").info(
            f"Proxy running on http://{config.server.host}:{config.server.proxy_port}"
        )
        yield
        await health_checker.stop()
        await proxy.stop()
        await db.close()

    app = FastAPI(title="NVIDIA API Pool Proxy", lifespan=lifespan)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_handler(request: Request, path: str):
        return await proxy.handle_request(request)

    config_uvicorn = uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.proxy_port,
        log_level="warning",
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()


async def run_gui(config, config_path, key_pool, db, ws_manager):
    gui_app = create_gui_app(config, config_path, key_pool, db, ws_manager)
    logging.getLogger("main").info(
        f"GUI running on http://{config.server.host}:{config.server.gui_port}"
    )
    config_uvicorn = uvicorn.Config(
        gui_app,
        host=config.server.host,
        port=config.server.gui_port,
        log_level="warning",
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()


async def main():
    parser = argparse.ArgumentParser(description="NVIDIA API Pool Manager")
    parser.add_argument(
        "--config", default="config/config.yaml", help="Path to config file"
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    setup_logging(config.logging.level)

    logger = logging.getLogger("main")
    logger.info(f"Loaded config from {config_path}")
    logger.info(f"Keys configured: {len(config.keys)}")
    logger.info(f"Strategy: {config.strategy}")

    db = Database()
    await db.init()

    key_pool = KeyPool(config.keys, config.strategy, config.rpm_limit)
    ws_manager = WebSocketManager()
    health_checker = HealthChecker(config, key_pool)

    proxy_task = asyncio.create_task(
        run_proxy(config, str(config_path), key_pool, db, health_checker, ws_manager)
    )
    gui_task = asyncio.create_task(
        run_gui(config, str(config_path), key_pool, db, ws_manager)
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    await stop_event.wait()
    logger.info("Shutting down...")
    proxy_task.cancel()
    gui_task.cancel()
    await asyncio.gather(proxy_task, gui_task, return_exceptions=True)
    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
