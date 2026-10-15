"""Gmail tools - send and read emails. Multi-user: each call uses the user's own Gmail."""

import json
import base64
from email.mime.text import MIMEText
from google_auth import get_gmail_service


def gmail_send(user_id: str, to: str, subject: str, message: str) -> str:
    """Send an email via Gmail API using the user's account."""
    try:
        service = get_gmail_service(user_id)

        mime = MIMEText(message)
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return json.dumps({
            "message": f"Email sent successfully to {to}!",
            "message_id": result.get("id"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def gmail_get_unread(user_id: str, after_date: str = "") -> str:
    """Get unread emails from inbox. after_date format: YYYY/MM/DD"""
    try:
        service = get_gmail_service(user_id)

        query = "is:unread in:inbox"
        if after_date:
            query += f" after:{after_date}"

        result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
        messages = result.get("messages", [])

        if not messages:
            return json.dumps({"message": "No unread emails found.", "emails": []})

        emails = []
        for msg_ref in messages:
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="metadata").execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg_ref["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "No subject"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return json.dumps({"message": f"Found {len(emails)} unread email(s).", "emails": emails})
    except Exception as e:
        return json.dumps({"error": str(e)})
