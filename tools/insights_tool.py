"""
Insights tools - Ashley's reasoning brain for analyzing patterns,
email stats, and generating smart suggestions from Supabase data.
Multi-user: all data is scoped to the requesting user.
"""

import json
from datetime import datetime
import pytz
from openai import OpenAI
import config
import database as db
from tools.calendar_tool import calendar_get_events

client = OpenAI(api_key=config.OPENAI_API_KEY)


def _get_user_timezone(user_id: str) -> str:
    user = db.get_user(user_id)
    return user.get("timezone", "Asia/Manila") if user else "Asia/Manila"


def insights_email_stats(user_id: str, hours: str = "24") -> str:
    """Get email analysis breakdown from Supabase for the last N hours."""
    try:
        h = int(hours)
    except ValueError:
        h = 24

    try:
        stats = db.get_email_analysis_stats(user_id, hours=h)

        if stats["total"] == 0:
            return json.dumps({
                "message": f"No analyzed emails in the last {h} hours.",
                "stats": stats,
            })

        categories = stats.get("categories", {})
        cat_breakdown = ", ".join(
            f"{cat}: {count}" for cat, count in sorted(categories.items(), key=lambda x: -x[1])
        )

        recent = []
        for r in stats.get("recent_emails", []):
            recent.append({
                "from": r.get("sender_name", "?"),
                "subject": r.get("subject", "?"),
                "category": r.get("category", "?"),
                "urgency": r.get("urgency", "?"),
                "spam_score": r.get("spam_score", 0),
                "action": r.get("suggested_action", "?"),
            })

        return json.dumps({
            "message": f"Email stats for the last {h} hours.",
            "total_emails": stats["total"],
            "spam_count": stats["spam_count"],
            "suspicious_count": stats["suspicious_count"],
            "urgent_count": stats["urgent_count"],
            "category_breakdown": cat_breakdown,
            "recent_emails": recent,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def insights_daily_summary(user_id: str) -> str:
    """Generate a full daily summary: calendar, tasks, emails, and AI insights."""
    tz = pytz.timezone(_get_user_timezone(user_id))
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    summary = {
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
    }

    # Calendar events
    try:
        events_str = calendar_get_events(
            user_id,
            time_min=today_start.isoformat(),
            time_max=today_end.isoformat(),
        )
        events_data = json.loads(events_str)
        events = events_data.get("events", [])
        summary["events_count"] = len(events)
        summary["events"] = [
            {"title": e.get("summary", "?"), "start": e.get("start", "?")}
            for e in events[:10]
        ]
    except Exception as e:
        summary["events_error"] = str(e)

    # Tasks
    try:
        tasks = db.get_tasks(user_id) or []
        summary["tasks_count"] = len(tasks)
        summary["tasks"] = [t.get("name", "?") for t in tasks[:10]]
    except Exception as e:
        summary["tasks_error"] = str(e)

    # Email stats (last 24h)
    try:
        stats = db.get_email_analysis_stats(user_id, hours=24)
        summary["emails_24h"] = stats["total"]
        summary["emails_spam"] = stats["spam_count"]
        summary["emails_urgent"] = stats["urgent_count"]
        summary["emails_suspicious"] = stats["suspicious_count"]
        summary["email_categories"] = stats.get("categories", {})
    except Exception as e:
        summary["email_stats_error"] = str(e)

    # Pending scheduled emails
    try:
        pending = db.get_pending_emails(user_id) or []
        summary["pending_scheduled_emails"] = len(pending)
    except Exception as e:
        summary["pending_error"] = str(e)

    # Sent emails today
    try:
        sent = db.get_today_sent_emails(user_id)
        summary["emails_sent_today"] = len(sent)
    except Exception as e:
        summary["sent_error"] = str(e)

    return json.dumps({"message": "Daily summary generated.", "summary": summary})


def insights_analyze_request(user_id: str, question: str) -> str:
    """
    Ashley's deep reasoning tool. Takes any question and reasons through it
    using all available data for this user.
    """
    context_parts = []

    try:
        stats = db.get_email_analysis_stats(user_id, hours=168)
        context_parts.append(f"EMAIL DATA (last 7 days): {json.dumps(stats, default=str)}")
    except Exception:
        pass

    try:
        tasks = db.get_tasks(user_id) or []
        context_parts.append(f"OPEN TASKS: {json.dumps([t.get('name','') for t in tasks])}")
    except Exception:
        pass

    try:
        pending = db.get_pending_emails(user_id) or []
        context_parts.append(f"PENDING SCHEDULED EMAILS: {len(pending)}")
    except Exception:
        pass

    tz = pytz.timezone(_get_user_timezone(user_id))
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        events_str = calendar_get_events(
            user_id,
            time_min=today_start.isoformat(),
            time_max=today_end.isoformat(),
        )
        context_parts.append(f"TODAY'S CALENDAR: {events_str}")
    except Exception:
        pass

    context = "\n".join(context_parts)

    # Get user name for prompt
    user = db.get_user(user_id)
    user_name = user.get("name", "Boss") if user else "Boss"

    prompt = f"""You are Ashley, an elite AI analyst. The user ({user_name}) is asking you a question.
Use the data below to reason through it step by step and give a clear, helpful answer.

AVAILABLE DATA:
{context}

QUESTION: {question}

Think step by step. Identify patterns, irregularities, or insights. Give actionable suggestions.
Be specific with numbers and names from the data. Keep the answer concise but thorough."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.4,
        )
        answer = response.choices[0].message.content.strip()
        return json.dumps({"analysis": answer})
    except Exception as e:
        return json.dumps({"error": f"Reasoning failed: {str(e)}"})
