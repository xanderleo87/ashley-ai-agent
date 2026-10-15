"""
Supabase database layer for Ashley AI Agent.
Multi-user: all data is scoped by user_id (Telegram chat ID).
"""

from supabase import create_client, Client
import config

supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)


# ── Users ──

def get_user(telegram_chat_id: str) -> dict | None:
    """Get a user by their Telegram chat ID."""
    result = supabase.table("users").select("*").eq("telegram_chat_id", telegram_chat_id).limit(1).execute()
    return result.data[0] if result.data else None


def create_user(telegram_chat_id: str, name: str, email: str = "", timezone: str = "Asia/Manila") -> dict:
    """Create a new user (pending approval by default)."""
    result = supabase.table("users").insert({
        "telegram_chat_id": telegram_chat_id,
        "name": name,
        "email": email,
        "timezone": timezone,
        "is_active": True,
        "is_admin": False,
        "is_approved": False,
    }).execute()
    return result.data[0] if result.data else {}


def update_user(telegram_chat_id: str, updates: dict):
    """Update a user's fields."""
    result = supabase.table("users").update(updates).eq("telegram_chat_id", telegram_chat_id).execute()
    return result.data


def get_all_active_users() -> list:
    """Get all active AND approved users (for schedulers)."""
    result = supabase.table("users").select("*").eq("is_active", True).eq("is_approved", True).execute()
    return result.data or []


def is_user_approved(telegram_chat_id: str) -> bool:
    """Check if a user is approved to use Ashley."""
    user = get_user(telegram_chat_id)
    if not user:
        return False
    return bool(user.get("is_approved", False))


def approve_user(telegram_chat_id: str) -> dict | None:
    """Approve a user to use Ashley."""
    result = supabase.table("users").update({"is_approved": True}).eq("telegram_chat_id", telegram_chat_id).execute()
    return result.data[0] if result.data else None


def reject_user(telegram_chat_id: str) -> dict | None:
    """Reject/deactivate a user."""
    result = supabase.table("users").update({"is_approved": False, "is_active": False}).eq("telegram_chat_id", telegram_chat_id).execute()
    return result.data[0] if result.data else None


def get_pending_users() -> list:
    """Get users awaiting approval."""
    result = supabase.table("users").select("*").eq("is_active", True).eq("is_approved", False).execute()
    return result.data or []


def get_admin_chat_ids() -> list:
    """Get Telegram chat IDs of all admin users."""
    result = supabase.table("users").select("telegram_chat_id").eq("is_admin", True).eq("is_active", True).execute()
    return [r["telegram_chat_id"] for r in (result.data or [])]


def save_user_google_token(telegram_chat_id: str, token_data: dict):
    """Save Google OAuth token for a user."""
    supabase.table("users").update({"google_token": token_data}).eq("telegram_chat_id", telegram_chat_id).execute()


def get_user_google_token(telegram_chat_id: str) -> dict | None:
    """Get a user's stored Google OAuth token."""
    result = supabase.table("users").select("google_token").eq("telegram_chat_id", telegram_chat_id).limit(1).execute()
    if result.data and result.data[0].get("google_token"):
        return result.data[0]["google_token"]
    return None


# ── Contacts ──

def get_contacts(user_id: str):
    """Fetch all contacts for a user."""
    result = supabase.table("contacts").select("*").eq("user_id", user_id).execute()
    return result.data


def search_contact(user_id: str, name: str):
    """Search contacts by name (case-insensitive partial match)."""
    result = supabase.table("contacts").select("*").eq("user_id", user_id).ilike("name", f"%{name}%").execute()
    return result.data


def get_contact_by_email(user_id: str, email: str):
    """Find a contact by exact email."""
    result = supabase.table("contacts").select("*").eq("user_id", user_id).eq("email", email).execute()
    return result.data


def add_contact(user_id: str, name: str, email: str):
    """Add a new contact."""
    result = supabase.table("contacts").insert({"user_id": user_id, "name": name, "email": email}).execute()
    return result.data


# ── Tasks ──

def get_tasks(user_id: str):
    """Fetch all tasks for a user."""
    result = supabase.table("tasks").select("*").eq("user_id", user_id).order("created_at", desc=False).execute()
    return result.data


def create_task(user_id: str, name: str):
    """Create a new task."""
    result = supabase.table("tasks").insert({"user_id": user_id, "name": name}).execute()
    return result.data


def delete_task(user_id: str, task_id: int):
    """Delete a task by ID."""
    result = supabase.table("tasks").delete().eq("user_id", user_id).eq("id", task_id).execute()
    return result.data


# ── Email Queue ──

def add_to_email_queue(user_id: str, recipient_email: str, subject: str, body_content: str, scheduled_time: str):
    """Add an email to the queue with status 'Pending'."""
    result = supabase.table("email_queue").insert({
        "user_id": user_id,
        "recipient_email": recipient_email,
        "subject": subject,
        "body_content": body_content,
        "scheduled_time": scheduled_time,
        "status": "Pending"
    }).execute()
    return result.data


def get_pending_emails(user_id: str = None):
    """Fetch pending emails. If user_id given, filter by user."""
    query = supabase.table("email_queue").select("*").eq("status", "Pending")
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.execute()
    return result.data


def mark_email_sent(email_id: int):
    """Mark an email as sent."""
    result = supabase.table("email_queue").update({"status": "Sent"}).eq("id", email_id).execute()
    return result.data


# ── Email Analysis ──

def save_email_analysis(user_id: str, message_id: str, sender_name: str, sender_email: str,
                        subject: str, analysis: dict):
    """Save Ashley's email analysis to Supabase."""
    result = supabase.table("email_analysis").upsert({
        "user_id": user_id,
        "message_id": message_id,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "category": analysis.get("category", "Other"),
        "urgency": analysis.get("urgency", "Medium"),
        "spam_score": analysis.get("spam_score", 0),
        "is_suspicious": analysis.get("is_suspicious", False),
        "sender_type": analysis.get("sender_type", "Unknown"),
        "suggested_action": analysis.get("suggested_action", "Read & Archive"),
        "summary": analysis.get("summary", ""),
    }).execute()
    return result.data


def get_email_analysis_stats(user_id: str, hours: int = 24) -> dict:
    """Get email analysis stats for the last N hours."""
    from datetime import datetime, timedelta
    import pytz

    user = get_user(user_id)
    tz_name = user.get("timezone", "Asia/Manila") if user else "Asia/Manila"
    tz = pytz.timezone(tz_name)
    since = (datetime.now(tz) - timedelta(hours=hours)).isoformat()

    result = supabase.table("email_analysis") \
        .select("*") \
        .eq("user_id", user_id) \
        .gte("analyzed_at", since) \
        .order("analyzed_at", desc=True) \
        .execute()

    records = result.data or []

    categories = {}
    spam_count = 0
    suspicious_count = 0
    urgent_count = 0

    for r in records:
        cat = r.get("category", "Other")
        categories[cat] = categories.get(cat, 0) + 1
        if r.get("spam_score", 0) >= 50:
            spam_count += 1
        if r.get("is_suspicious"):
            suspicious_count += 1
        if r.get("urgency") in ("Critical", "High"):
            urgent_count += 1

    return {
        "total": len(records),
        "categories": categories,
        "spam_count": spam_count,
        "suspicious_count": suspicious_count,
        "urgent_count": urgent_count,
        "recent_emails": records[:5],
    }


def get_today_sent_emails(user_id: str) -> list:
    """Get emails sent today from the queue."""
    from datetime import datetime
    import pytz

    user = get_user(user_id)
    tz_name = user.get("timezone", "Asia/Manila") if user else "Asia/Manila"
    tz = pytz.timezone(tz_name)
    today_start = datetime.now(tz).replace(hour=0, minute=0, second=0).isoformat()

    result = supabase.table("email_queue") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("status", "Sent") \
        .gte("scheduled_time", today_start) \
        .execute()
    return result.data or []


# ── Job Search ──

def get_jobs(user_id: str, source: str = None, limit: int = 50) -> list:
    """Get jobs from the jobs table."""
    query = supabase.table("jobs").select("*").eq("is_expired", False).eq("user_id", user_id)
    if source:
        query = query.eq("source", source)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def get_jobs_by_keyword(user_id: str, keyword: str, limit: int = 30) -> list:
    """Search jobs by keyword in title or company."""
    kw = keyword.strip().replace(",", " ").replace(".", " ")
    result = supabase.table("jobs").select("*") \
        .eq("is_expired", False) \
        .eq("user_id", user_id) \
        .or_(f"title.ilike.%25{kw}%25,company.ilike.%25{kw}%25") \
        .order("created_at", desc=True) \
        .limit(limit).execute()
    return result.data or []


def get_job_applications(user_id: str, status: str = None, limit: int = 50) -> list:
    """Get job applications with linked job data."""
    query = supabase.table("applications").select("*, jobs(*)").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("match_score", desc=True).limit(limit).execute()
    return result.data or []


def get_job_stats(user_id: str) -> dict:
    """Get job search statistics."""
    jobs_r = supabase.table("jobs").select("id,source", count="exact") \
        .eq("is_expired", False).eq("user_id", user_id).execute()
    apps_r = supabase.table("applications").select("id,status,match_score", count="exact") \
        .eq("user_id", user_id).execute()

    total_jobs = jobs_r.count if jobs_r.count is not None else len(jobs_r.data or [])

    sources = {}
    for j in (jobs_r.data or []):
        src = j.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    apps_data = apps_r.data or []
    total_apps = len(apps_data)
    pending = sum(1 for a in apps_data if a.get("status") == "pending")
    approved = sum(1 for a in apps_data if a.get("status") == "approved")
    sent = sum(1 for a in apps_data if a.get("status") == "sent")
    scores = [a["match_score"] for a in apps_data if a.get("match_score")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "total_jobs": total_jobs,
        "sources": sources,
        "total_applications": total_apps,
        "pending": pending,
        "approved": approved,
        "sent": sent,
        "avg_score": avg_score,
    }


def get_top_job_matches(user_id: str, limit: int = 10) -> list:
    """Get top job matches by score."""
    result = supabase.table("applications").select("*, jobs(*)") \
        .eq("user_id", user_id) \
        .order("match_score", desc=True) \
        .limit(limit).execute()
    return result.data or []


def get_cv(user_id: str) -> str:
    """Get the current CV content."""
    result = supabase.table("cv").select("content") \
        .eq("user_id", user_id) \
        .order("uploaded_at", desc=True).limit(1).execute()
    if result.data:
        return result.data[0].get("content", "")
    return ""


# ── Leads ──

def save_lead(user_id: str, lead: dict) -> list:
    """Save a scraped lead to Supabase."""
    lead["user_id"] = user_id
    result = supabase.table("leads").upsert(lead, on_conflict="place_id").execute()
    return result.data


def get_leads(user_id: str, status: str = None, limit: int = 50) -> list:
    """Get leads with optional status filter."""
    query = supabase.table("leads").select("*").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("lead_score", desc=True).order("scraped_at", desc=True).limit(limit).execute()
    return result.data or []


def get_lead_by_id(lead_id: int) -> dict | None:
    """Get a single lead by ID."""
    result = supabase.table("leads").select("*").eq("id", lead_id).limit(1).execute()
    return result.data[0] if result.data else None


def update_lead(lead_id: int, updates: dict):
    """Update a lead."""
    result = supabase.table("leads").update(updates).eq("id", lead_id).execute()
    return result.data


def get_lead_stats(user_id: str) -> dict:
    """Get lead generation stats."""
    result = supabase.table("leads").select("id,status,lead_score").eq("user_id", user_id).execute()
    data = result.data or []
    total = len(data)
    new = sum(1 for d in data if d.get("status") == "new")
    contacted = sum(1 for d in data if d.get("status") == "contacted")
    replied = sum(1 for d in data if d.get("status") == "replied")
    converted = sum(1 for d in data if d.get("status") == "converted")
    scores = [d["lead_score"] for d in data if d.get("lead_score")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "total_leads": total,
        "new": new,
        "contacted": contacted,
        "replied": replied,
        "converted": converted,
        "avg_lead_score": avg_score,
    }


# ── Outreach Messages ──

def save_outreach_message(user_id: str, message: dict) -> list:
    """Save an outreach message draft."""
    message["user_id"] = user_id
    result = supabase.table("outreach_messages").insert(message).execute()
    return result.data


def get_outreach_messages(user_id: str, status: str = None, limit: int = 50) -> list:
    """Get outreach messages with linked lead data."""
    query = supabase.table("outreach_messages").select("*, leads(*)").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def update_outreach_message(msg_id: int, updates: dict):
    """Update an outreach message."""
    result = supabase.table("outreach_messages").update(updates).eq("id", msg_id).execute()
    return result.data


def get_outreach_stats(user_id: str) -> dict:
    """Get outreach message stats."""
    result = supabase.table("outreach_messages").select("id,status").eq("user_id", user_id).execute()
    data = result.data or []
    return {
        "total": len(data),
        "drafts": sum(1 for d in data if d.get("status") == "draft"),
        "approved": sum(1 for d in data if d.get("status") == "approved"),
        "sent": sum(1 for d in data if d.get("status") == "sent"),
    }
