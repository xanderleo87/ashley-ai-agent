"""
Daily Digest - Runs once every morning.
Multi-user: sends personalized morning briefing to each active user.
"""

import json
from datetime import datetime
import pytz
import httpx
from openai import OpenAI
import config
import database as db
from tools.calendar_tool import calendar_get_events

client = OpenAI(api_key=config.OPENAI_API_KEY)


def send_telegram_message(chat_id: str, text: str):
    """Send an HTML-formatted message to a specific user via Telegram."""
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
    except Exception as e:
        print(f"[Daily Digest] Telegram send failed for {chat_id}: {e}")


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def gather_daily_data(user_id: str, timezone: str) -> dict:
    """Pull all data for a user's morning briefing."""
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    data = {
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "events": [],
        "tasks": [],
        "email_stats": {},
        "pending_emails": [],
    }

    # Calendar events
    try:
        events_str = calendar_get_events(
            user_id,
            time_min=today_start.isoformat(),
            time_max=today_end.isoformat(),
        )
        events_data = json.loads(events_str)
        data["events"] = events_data.get("events", [])
    except Exception as e:
        print(f"[Daily Digest] Calendar error for {user_id}: {e}")

    # Tasks
    try:
        data["tasks"] = db.get_tasks(user_id) or []
    except Exception as e:
        print(f"[Daily Digest] Tasks error for {user_id}: {e}")

    # Email stats (last 24h)
    try:
        data["email_stats"] = db.get_email_analysis_stats(user_id, hours=24)
    except Exception as e:
        print(f"[Daily Digest] Email stats error for {user_id}: {e}")

    # Pending scheduled emails
    try:
        data["pending_emails"] = db.get_pending_emails(user_id) or []
    except Exception as e:
        print(f"[Daily Digest] Pending emails error for {user_id}: {e}")

    return data


def generate_ashley_insights(user_name: str, data: dict) -> str:
    """Use AI to generate personalized morning insights."""
    prompt = f"""You are Ashley, the witty and sharp Executive Assistant for {user_name}.
Generate a SHORT morning briefing insight (3-5 bullet points max) based on this data.
Be personality-driven, helpful, and proactive. Mention specific things from the data.
If there are potential issues (schedule conflicts, overdue tasks, spam surge), flag them.
Give 1-2 actionable suggestions for the day.

DATA:
- Date: {data['date']}
- Calendar events today: {len(data['events'])} events
  {json.dumps(data['events'][:8], indent=2) if data['events'] else 'None'}
- Open tasks: {len(data['tasks'])} tasks
  {json.dumps([t.get('name','') for t in data['tasks'][:10]]) if data['tasks'] else 'None'}
- Emails in last 24h: {data['email_stats'].get('total', 0)} total,
  {data['email_stats'].get('spam_count', 0)} spam,
  {data['email_stats'].get('suspicious_count', 0)} suspicious,
  {data['email_stats'].get('urgent_count', 0)} urgent
  Categories: {json.dumps(data['email_stats'].get('categories', {}))}
- Pending scheduled emails: {len(data['pending_emails'])}

Return ONLY the bullet points, no greeting or signoff. Keep it under 500 characters."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Daily Digest] AI insights error: {e}")
        return "Could not generate insights today. Check your dashboard manually!"


def send_digest_to_user(user: dict):
    """Build and send morning digest to a single user."""
    user_id = user["telegram_chat_id"]
    user_name = user.get("name", "Boss")
    timezone = user.get("timezone", "Asia/Manila")

    # Skip users without Google token (can't fetch calendar/email)
    if not user.get("google_token"):
        return

    print(f"[Daily Digest] Generating briefing for {user_name} ({user_id})...")

    data = gather_daily_data(user_id, timezone)
    insights = generate_ashley_insights(user_name, data)

    lines = []

    # Header
    lines.append(f"\u2615 <b>Good Morning, {_esc(user_name)}!</b>")
    lines.append(f"\U0001f4c5 {_esc(data['date'])} | {_esc(data['time'])}")
    lines.append("")

    # Calendar
    events = data["events"]
    lines.append(f"\U0001f4c6 <b>TODAY'S SCHEDULE</b> ({len(events)} event{'s' if len(events) != 1 else ''})")
    if events:
        for ev in events[:8]:
            start = ev.get("start", "")
            if "T" in start:
                try:
                    t = datetime.fromisoformat(start).strftime("%I:%M %p")
                except Exception:
                    t = start
            else:
                t = "All day"
            lines.append(f"  \u2022 {t} - {_esc(ev.get('summary', 'No title'))}")
    else:
        lines.append("  No events today. Free day or planning day?")
    lines.append("")

    # Tasks
    tasks = data["tasks"]
    lines.append(f"\u2611 <b>OPEN TASKS</b> ({len(tasks)})")
    if tasks:
        for t in tasks[:8]:
            lines.append(f"  \u2022 {_esc(t.get('name', ''))}")
        if len(tasks) > 8:
            lines.append(f"  ... and {len(tasks) - 8} more")
    else:
        lines.append("  All clear! No pending tasks.")
    lines.append("")

    # Email Stats
    stats = data["email_stats"]
    total = stats.get("total", 0)
    lines.append(f"\U0001f4e7 <b>EMAIL REPORT</b> (last 24h)")
    lines.append(f"  Total: {total} | Spam: {stats.get('spam_count', 0)} | "
                 f"Urgent: {stats.get('urgent_count', 0)} | "
                 f"Suspicious: {stats.get('suspicious_count', 0)}")
    categories = stats.get("categories", {})
    if categories:
        cat_parts = [f"{cat}: {count}" for cat, count in sorted(categories.items(), key=lambda x: -x[1])]
        lines.append(f"  Breakdown: {', '.join(cat_parts[:6])}")
    lines.append("")

    # Pending scheduled emails
    pending = data["pending_emails"]
    if pending:
        lines.append(f"\U0001f4e4 <b>SCHEDULED EMAILS</b> ({len(pending)} waiting)")
        for p in pending[:5]:
            lines.append(f"  \u2022 To: {_esc(p.get('recipient_email', '?'))} - {_esc(p.get('subject', '?'))}")
        lines.append("")

    # Ashley's Insights
    lines.append(f"\U0001f9e0 <b>ASHLEY'S INSIGHTS</b>")
    for line in insights.split("\n"):
        lines.append(f"  {_esc(line)}")

    message = "\n".join(lines)
    send_telegram_message(user_id, message)
    print(f"[Daily Digest] Sent briefing to {user_name}")


def send_daily_digest():
    """Send morning digest to ALL active users."""
    print("[Daily Digest] Starting morning briefings for all users...")

    try:
        users = db.get_all_active_users()
    except Exception as e:
        print(f"[Daily Digest] Error fetching users: {e}")
        return

    for user in users:
        try:
            send_digest_to_user(user)
        except Exception as e:
            print(f"[Daily Digest] Error for user {user.get('telegram_chat_id')}: {e}")

    print(f"[Daily Digest] All briefings sent ({len(users)} users)")
