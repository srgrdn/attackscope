import asyncio
import contextlib
import logging
import signal
import socket
import time
from collections.abc import Iterator

import uvicorn
from sqlalchemy import Engine

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime
from attackscope.classification.engine import WindowCache, process_pending
from attackscope.core.config import Settings
from attackscope.storage.retention import cleanup
from attackscope.storage.store import Store

logger = logging.getLogger("attackscope.server")


class ManagedServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        # Both listeners share one lifecycle; only the coordinator owns signals.
        yield


def bind_socket(host: str, port: int) -> socket.socket:
    # Resolve both address families; no shell or URLs are involved.
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    family, kind, protocol, _, address = addresses[0]
    listener = socket.socket(family, kind, protocol)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(address)
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise


async def background_work(runtime: Runtime) -> None:
    last_cleanup = 0.0
    cache = WindowCache()
    while True:
        try:
            await asyncio.to_thread(process_pending, runtime.store, runtime.settings, 100, cache)
            if time.monotonic() - last_cleanup >= 60:
                await asyncio.to_thread(cleanup, runtime.store, runtime.settings)
                last_cleanup = time.monotonic()
        except Exception as error:
            logger.error("Background work failed: %s", type(error).__name__)
        await asyncio.sleep(2)


async def serve(settings: Settings, engine: Engine) -> None:
    runtime = Runtime(Store(engine, write_timeout=settings.write_wait_seconds), settings)
    servers = [
        ManagedServer(
            uvicorn.Config(
                create_app(engine, ingestion=ingestion, runtime=runtime),
                log_level=settings.log_level,
                access_log=False,
                server_header=False,
                timeout_graceful_shutdown=10,
                limit_concurrency=32,
            )
        )
        for ingestion in (False, True)
    ]
    worker = asyncio.create_task(background_work(runtime))
    tasks: list[asyncio.Task[None]] = []
    loop = asyncio.get_running_loop()

    def stop() -> None:
        for server in servers:
            server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    try:
        with contextlib.ExitStack() as stack:
            # Bind both before starting either: one occupied port cannot leave half a service.
            listeners = [
                stack.enter_context(bind_socket(settings.bind_host, port))
                for port in (settings.read_port, settings.ingest_port)
            ]
            tasks = [
                asyncio.create_task(server.serve(sockets=[listener]))
                for server, listener in zip(servers, listeners, strict=True)
            ]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if not all(server.should_exit for server in servers):
                    raise RuntimeError("A listener stopped unexpectedly")
            finally:
                stop()
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True), timeout=15
                    )
                except TimeoutError:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.error("Graceful shutdown timed out")
    finally:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
