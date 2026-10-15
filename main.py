"""
Ashley AI Agent - Main Entry Point
Starts the Telegram bot and background schedulers.
"""

import asyncio
import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from bot import create_bot
from oauth_server import run_oauth_server
from schedulers.email_dispatcher import dispatch_pending_emails
from schedulers.gmail_watcher import check_new_emails
from schedulers.daily_digest import send_daily_digest
import config

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("Ashley")


def main():
    print("=" * 50)
    print("  Ashley AI Agent - Starting Up...")
    print("=" * 50)
    print()

    # Set up background schedulers (runs in a separate thread)
    scheduler = BackgroundScheduler()

    scheduler.add_job(dispatch_pending_emails, "interval", minutes=1, id="email_dispatcher")
    logger.info("Email Dispatcher scheduled (every 1 min)")

    scheduler.add_job(check_new_emails, "interval", minutes=1, id="gmail_watcher")
    logger.info("Gmail Watcher scheduled (every 1 min)")

    scheduler.add_job(send_daily_digest, "cron", hour=7, minute=0,
                      timezone="Asia/Manila", id="daily_digest")
    logger.info("Daily Digest scheduled (every day at 7:00 AM)")

    scheduler.start()
    logger.info("Background schedulers started")

    # Start OAuth web server (for self-service Google auth)
    run_oauth_server()
    logger.info(f"OAuth server: {config.OAUTH_BASE_URL}/auth/start/<chat_id>")

    # Start the bot with retry on network errors
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            # Create a fresh event loop for each attempt (run_polling closes the loop on failure)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app = create_bot()
            print()
            print("Ashley is online!")
            print("Send a message on Telegram to get started.")
            print("Press Ctrl+C to stop.")
            print()
            app.run_polling(drop_pending_updates=False)
            break  # Clean exit
        except Exception as e:
            if attempt < max_retries:
                wait = min(attempt * 5, 30)
                logger.warning(f"Connection failed (attempt {attempt}/{max_retries}): {e}")
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Failed after {max_retries} attempts. Giving up.")
                raise


if __name__ == "__main__":
    main()
