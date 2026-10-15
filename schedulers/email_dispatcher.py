"""
Email Dispatcher - Runs every minute.
Multi-user: loops through all users with pending emails,
sends via each user's own Gmail account.
"""

from datetime import datetime
import pytz
import json
import database as db
from tools.gmail_tool import gmail_send


def dispatch_pending_emails():
    """Check for pending emails across ALL users and send any that are due."""
    try:
        users = db.get_all_active_users()
    except Exception as e:
        print(f"[Email Dispatcher] Error fetching users: {e}")
        return

    for user in users:
        user_id = user["telegram_chat_id"]
        timezone = user.get("timezone", "Asia/Manila")

        # Skip users without Google token
        if not user.get("google_token"):
            continue

        try:
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
        except Exception:
            now = datetime.now(pytz.timezone("Asia/Manila"))

        try:
            pending = db.get_pending_emails(user_id)
        except Exception as e:
            print(f"[Email Dispatcher] Error fetching queue for user {user_id}: {e}")
            continue

        if not pending:
            continue

        for email in pending:
            try:
                scheduled_str = email.get("scheduled_time", "")
                if not scheduled_str:
                    continue

                scheduled_time = datetime.fromisoformat(scheduled_str)
                if scheduled_time.tzinfo is None:
                    scheduled_time = tz.localize(scheduled_time)

                if scheduled_time <= now:
                    result_str = gmail_send(
                        user_id,
                        to=email["recipient_email"],
                        subject=email["subject"],
                        message=email["body_content"],
                    )
                    result = json.loads(result_str)

                    if "error" in result:
                        print(f"[Email Dispatcher] Failed for user {user_id} to {email['recipient_email']}: {result['error']}")
                    else:
                        db.mark_email_sent(email["id"])
                        print(f"[Email Dispatcher] Sent for user {user_id} to {email['recipient_email']} - {email['subject']}")

            except Exception as e:
                print(f"[Email Dispatcher] Error processing email ID {email.get('id')}: {e}")
