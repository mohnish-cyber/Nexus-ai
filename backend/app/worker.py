"""Standalone background worker.

    python -m app.worker

Runs the automation scheduler outside the API process. Use with
SCHEDULER_MODE=external for production so web requests and background jobs
scale and restart independently.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.config import get_settings
from app.database.session import dispose_engine, init_db
from app.logging_config import configure_logging
from app.services.scheduler import get_scheduler

logger = logging.getLogger("nexus.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()
    scheduler = get_scheduler(settings.scheduler_poll_seconds)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    scheduler.start()
    logger.info("NEXUS worker running. Press Ctrl+C to stop.")
    await stop.wait()
    await scheduler.stop()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
