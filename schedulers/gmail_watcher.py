"""
Gmail Watcher - Runs every minute.
Multi-user: checks each user's Gmail, analyzes emails,
and sends notifications to each user's Telegram.
"""

import json
import re
import html
import httpx
import database as db
from tools.gmail_tool import gmail_get_unread
from reasoning import analyze_email
import config

# Track notified message IDs per user to avoid duplicates
_notified_ids: dict[str, set] = {}

# Category icons for visual sorting
CATEGORY_ICONS = {
    "Work": "\U0001f4bc",
    "Client": "\U0001f91d",
    "Personal": "\U0001f9d1",
    "Family": "\U0001f3e0",
    "Finance": "\U0001f4b3",
    "Newsletter": "\U0001f4f0",
    "Promotion": "\U0001f6cd",
    "Spam": "\U0001f6ab",
    "Scam": "\u26a0",
    "Government": "\U0001f3db",
    "Social Media": "\U0001f4f1",
    "Notification": "\U0001f514",
    "Other": "\U0001f4e8",
}

URGENCY_ICONS = {
    "Critical": "\U0001f534",
    "High": "\U0001f7e0",
    "Medium": "\U0001f7e1",
    "Low": "\U0001f7e2",
    "None": "\u26aa",
}


def extract_email_from_header(from_header: str) -> str | None:
    """Extract email address from 'Name <email>' format."""
    match = re.search(r"<(.+?)>", from_header)
    if match:
        return match.group(1)
    if "@" in from_header:
        return from_header.strip()
    return None


def extract_name_from_header(from_header: str) -> str:
    """Extract name from 'Name <email>' format."""
    name = from_header.split("<")[0].strip().strip('"').strip("'")
    return name if name else "Unknown"


def send_telegram_notification(chat_id: str, text: str):
    """Send a formatted notification message to a specific user via Telegram."""
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
    except Exception as e:
        print(f"[Gmail Watcher] Telegram notification failed for {chat_id}: {e}")


def format_notification(email_data: dict, analysis: dict) -> str:
    """Build a clean, structured HTML notification for Telegram."""
    category = analysis.get("category", "Other")
    urgency = analysis.get("urgency", "Medium")
    spam_score = analysis.get("spam_score", 0)
    is_suspicious = analysis.get("is_suspicious", False)
    red_flags = analysis.get("red_flags", [])
    sender_type = analysis.get("sender_type", "Unknown")
    action = analysis.get("suggested_action", "Read & Archive")
    summary = analysis.get("summary", "")
    ashley_note = analysis.get("ashley_note", "")

    cat_icon = CATEGORY_ICONS.get(category, "\U0001f4e8")
    urg_icon = URGENCY_ICONS.get(urgency, "\u26aa")

    lines = []

    lines.append(f"{cat_icon} <b>{category.upper()}</b> | {urg_icon} {urgency}")
    lines.append("")
    lines.append(f"<b>From:</b> {_esc(email_data['sender_name'])}")
    lines.append(f"<b>Subject:</b> {_esc(email_data['subject'])}")
    lines.append("")

    if email_data.get("snippet"):
        lines.append(f"<i>{_esc(email_data['snippet'])}</i>")
        lines.append("")

    if summary:
        lines.append(f"\U0001f9e0 <b>Summary:</b> {_esc(summary)}")

    lines.append(f"\U0001f464 <b>Sender:</b> {_esc(sender_type)}")
    lines.append(f"\u2192 <b>Action:</b> {_esc(action)}")

    if spam_score >= 40 or is_suspicious:
        lines.append("")
        lines.append(f"\u26a0 <b>SPAM SCORE: {spam_score}/100</b>")
        if red_flags:
            for flag in red_flags[:3]:
                lines.append(f"  \u2022 {_esc(flag)}")

    if ashley_note:
        lines.append("")
        lines.append(f"\U0001f4ac <b>Ashley:</b> {_esc(ashley_note)}")

    return "\n".join(lines)


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _get_user_notified_ids(user_id: str) -> set:
    """Get the set of notified message IDs for a user."""
    if user_id not in _notified_ids:
        _notified_ids[user_id] = set()
    return _notified_ids[user_id]


def check_new_emails():
    """Check for new unread emails for ALL active users."""
    try:
        users = db.get_all_active_users()
    except Exception as e:
        print(f"[Gmail Watcher] Error fetching users: {e}")
        return

    for user in users:
        user_id = user["telegram_chat_id"]

        # Skip users without Google token
        if not user.get("google_token"):
            continue

        _check_emails_for_user(user_id)


def _check_emails_for_user(user_id: str):
    """Check and process new emails for a single user."""
    try:
        result_str = gmail_get_unread(user_id)
        result = json.loads(result_str)
    except Exception as e:
        print(f"[Gmail Watcher] Error checking emails for user {user_id}: {e}")
        return

    if "error" in result:
        print(f"[Gmail Watcher] Gmail error for user {user_id}: {result['error']}")
        return

    emails = result.get("emails", [])
    notified = _get_user_notified_ids(user_id)

    for email in emails:
        msg_id = email.get("id", "")

        if msg_id in notified:
            continue

        from_header = email.get("from", "Unknown")
        sender_email = extract_email_from_header(from_header)
        sender_name = extract_name_from_header(from_header)
        subject = email.get("subject", "No subject")
        snippet = email.get("snippet", "")

        # Clean up the snippet
        snippet = html.unescape(snippet)
        snippet = re.sub(r"On .+wrote:", "", snippet)
        snippet = re.sub(r"<[^>]+>", "", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."

        # Auto-save unknown contacts
        if sender_email:
            existing = db.get_contact_by_email(user_id, sender_email)
            if not existing:
                try:
                    db.add_contact(user_id, sender_name, sender_email)
                    print(f"[Gmail Watcher] Saved new contact for user {user_id}: {sender_name} ({sender_email})")
                except Exception as e:
                    print(f"[Gmail Watcher] Failed to save contact: {e}")

        # Run AI analysis
        analysis = analyze_email(
            sender_name=sender_name,
            sender_email=sender_email or "unknown",
            subject=subject,
            snippet=snippet,
        )

        print(f"[Gmail Watcher] [{user_id}] Analyzed: {subject} -> {analysis.get('category', '?')} | "
              f"Spam: {analysis.get('spam_score', '?')}/100")

        # Save analysis to Supabase
        try:
            db.save_email_analysis(
                user_id=user_id,
                message_id=msg_id,
                sender_name=sender_name,
                sender_email=sender_email or "unknown",
                subject=subject,
                analysis=analysis,
            )
        except Exception as e:
            print(f"[Gmail Watcher] Failed to save analysis: {e}")

        # Send notification to THIS user's Telegram
        email_data = {
            "sender_name": sender_name,
            "sender_email": sender_email or "unknown",
            "subject": subject,
            "snippet": snippet,
        }
        notification = format_notification(email_data, analysis)
        send_telegram_notification(user_id, notification)

        notified.add(msg_id)

        # Keep the set from growing forever
        if len(notified) > 500:
            oldest = list(notified)[:250]
            for old_id in oldest:
                notified.discard(old_id)
