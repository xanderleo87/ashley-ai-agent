"""Email queue tools - schedule emails for later, read pending queue. Multi-user."""

import json
import database as db


def email_queue_schedule(user_id: str, recipient_email: str, subject: str, body_content: str, scheduled_time: str) -> str:
    """Schedule an email for later delivery."""
    try:
        result = db.add_to_email_queue(user_id, recipient_email, subject, body_content, scheduled_time)
        return json.dumps({
            "message": f"Email to {recipient_email} scheduled for {scheduled_time}!",
            "subject": subject,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def email_queue_read_pending(user_id: str) -> str:
    """Read all pending emails in the queue."""
    try:
        pending = db.get_pending_emails(user_id)
        if not pending:
            return json.dumps({"message": "The queue is empty. No pending emails.", "emails": []})

        return json.dumps({
            "message": f"{len(pending)} email(s) pending in the queue.",
            "emails": [{
                "id": e["id"],
                "to": e["recipient_email"],
                "subject": e["subject"],
                "scheduled_time": e["scheduled_time"],
            } for e in pending],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
