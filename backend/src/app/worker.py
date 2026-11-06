"""Run background jobs in their own process: `uv run python -m app.worker`.

Run as many as you like; they share the queue safely. Set JOBS_WORKER_IN_API=false on the API
when you do, so web requests and jobs don't compete for the same CPU.
"""

import logging
import signal
import threading

from app.jobs import work_forever


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logging.info("Worker started")
    work_forever(stop)
    logging.info("Worker stopped")


if __name__ == "__main__":
    main()
