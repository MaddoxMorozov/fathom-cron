"""
Fathom -> Google Drive/Sheets Background Sync

Polls the Fathom API every 30 minutes, saves transcripts to Google Drive,
and logs date + link to a Google Sheet.

Usage: python main.py
"""

import sys
import signal
from apscheduler.schedulers.blocking import BlockingScheduler
from config import settings
from logger import logger
from sync import run_sync


def main():
    logger.info("Fathom Sync Service starting up")

    if not settings.FATHOM_API_KEY or "your_" in settings.FATHOM_API_KEY:
        logger.critical("FATHOM_API_KEY is not set or is a placeholder. Exiting.")
        sys.exit(1)

    # Run once immediately on startup
    logger.info("Running initial sync...")
    run_sync()

    # Schedule recurring sync
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_sync,
        "interval",
        minutes=settings.SYNC_INTERVAL_MINUTES,
        id="fathom_sync",
        max_instances=1,
        misfire_grace_time=300,
    )

    logger.info(
        f"Scheduler started. Polling every {settings.SYNC_INTERVAL_MINUTES} minutes. "
        f"Press Ctrl+C to stop."
    )

    def shutdown(signum, frame):
        logger.info("Shutdown signal received. Stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
