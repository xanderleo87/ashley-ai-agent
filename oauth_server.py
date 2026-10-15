"""
OAuth + Dashboard Web Server for Ashley AI Agent.
Serves both Google OAuth flows AND the dashboard API + static files
on a single port so one ngrok tunnel covers everything.
"""

import json
import secrets
import threading
import logging
import mimetypes
from pathlib import Path
from datetime import datetime
from flask import Flask, redirect, request, jsonify, send_file, Response
import pytz

import config
import database as db

logger = logging.getLogger("Ashley.OAuth")

app = Flask(__name__)

BASE_DIR = Path(__file__).parent

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

_pending_states = {}


def _load_client_config() -> dict:
    with open(config.GOOGLE_CREDENTIALS_FILE, "r") as f:
        client_config = json.load(f)
    if "installed" in client_config:
        installed = client_config["installed"]
        return {
            "web": {
                "client_id": installed["client_id"],
                "client_secret": installed["client_secret"],
                "auth_uri": installed["auth_uri"],
                "token_uri": installed["token_uri"],
                "auth_provider_x509_cert_url": installed.get(
                    "auth_provider_x509_cert_url",
                    "https://www.googleapis.com/oauth2/v1/certs",
                ),
                "redirect_uris": [f"{config.OAUTH_BASE_URL}/auth/callback"],
            }
        }
    return client_config


SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Ashley - Google Connected!</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .card {{
            background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);
            border-radius: 20px; padding: 40px; text-align: center;
            max-width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }}
        .check {{ font-size: 64px; margin-bottom: 16px; }}
        h1 {{ margin: 0 0 12px; font-size: 24px; }}
        p {{ opacity: 0.9; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="check">&#10004;</div>
        <h1>Google Account Connected!</h1>
        <p>Hey {name}! Your Gmail and Calendar are now linked to Ashley.</p>
        <p>You can close this tab and go back to Telegram.</p>
    </div>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Ashley - Connection Failed</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; margin: 0;
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
        }}
        .card {{
            background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);
            border-radius: 20px; padding: 40px; text-align: center;
            max-width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }}
        .icon {{ font-size: 64px; margin-bottom: 16px; }}
        h1 {{ margin: 0 0 12px; font-size: 24px; }}
        p {{ opacity: 0.9; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#10060;</div>
        <h1>Connection Failed</h1>
        <p>{error}</p>
        <p>Please go back to Telegram and try /connectgoogle again.</p>
    </div>
</body>
</html>
"""


def _send_telegram_notification(chat_id: str, text: str):
    try:
        import httpx
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification to {chat_id}: {e}")


def _cors_json(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _get_uid():
    return request.args.get("uid")


def _require_uid():
    uid = _get_uid()
    if not uid:
        return None
    return uid


# ══════════════════════════════════════════════════
#  OAUTH ROUTES
# ══════════════════════════════════════════════════

@app.route("/auth/start/<chat_id>")
def start_auth(chat_id):
    from google_auth_oauthlib.flow import Flow
    user = db.get_user(chat_id)
    if not user:
        return ERROR_HTML.format(error="User not found. Please /register on Telegram first."), 404
    if not user.get("is_approved"):
        return ERROR_HTML.format(error="Your account hasn't been approved yet. Please wait for admin approval."), 403
    try:
        client_config = _load_client_config()
        redirect_uri = f"{config.OAUTH_BASE_URL}/auth/callback"
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
        state = secrets.token_urlsafe(32)
        _pending_states[state] = chat_id
        auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", state=state, prompt="consent")
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"OAuth start failed for {chat_id}: {e}")
        return ERROR_HTML.format(error=f"Failed to start authorization: {e}"), 500


@app.route("/auth/callback")
def auth_callback():
    from google_auth_oauthlib.flow import Flow
    error = request.args.get("error")
    if error:
        return ERROR_HTML.format(error=f"Google authorization was denied: {error}"), 400
    state = request.args.get("state")
    code = request.args.get("code")
    if not state or not code:
        return ERROR_HTML.format(error="Missing authorization parameters."), 400
    chat_id = _pending_states.pop(state, None)
    if not chat_id:
        return ERROR_HTML.format(error="Authorization session expired or invalid. Please try /connectgoogle again."), 400
    user = db.get_user(chat_id)
    if not user:
        return ERROR_HTML.format(error="User not found."), 404
    try:
        client_config = _load_client_config()
        redirect_uri = f"{config.OAUTH_BASE_URL}/auth/callback"
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri, state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_data = json.loads(creds.to_json())
        db.save_user_google_token(chat_id, token_data)
        logger.info(f"Google account connected for user {user['name']} ({chat_id})")
        _send_telegram_notification(chat_id, f"Your Google account is now connected!\n\nAshley can now access your Gmail and Calendar.\nTry asking me to check your emails or schedule something!")
        return SUCCESS_HTML.format(name=user.get("name", "there")), 200
    except Exception as e:
        logger.error(f"OAuth callback failed for {chat_id}: {e}")
        return ERROR_HTML.format(error=f"Failed to complete authorization: {e}"), 500


# ══════════════════════════════════════════════════
#  DASHBOARD API ROUTES
# ══════════════════════════════════════════════════

@app.route("/api/auth")
def api_auth():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return _cors_json({"error": "Email required"}, 400)
    try:
        result = db.supabase.table("users").select("*").eq("email", email).eq("is_approved", True).limit(1).execute()
        if result.data:
            user = result.data[0]
            return _cors_json({
                "success": True,
                "user": {
                    "uid": user["telegram_chat_id"],
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "timezone": user.get("timezone", "Asia/Manila"),
                    "google_connected": bool(user.get("google_token")),
                }
            })
        else:
            return _cors_json({"error": "Account not found or not approved."}, 403)
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/dashboard")
def api_dashboard():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        from tools.calendar_tool import calendar_get_events
        user = db.get_user(uid)
        tz_name = user.get("timezone", config.TIMEZONE) if user else config.TIMEZONE
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)

        data = {
            "timestamp": now.isoformat(),
            "date": now.strftime("%A, %B %d, %Y"),
            "time": now.strftime("%I:%M %p"),
            "user_name": user.get("name", "") if user else "",
        }

        try:
            data["email_stats"] = db.get_email_analysis_stats(uid, hours=168)
        except Exception:
            data["email_stats"] = {"total": 0, "categories": {}, "spam_count": 0, "suspicious_count": 0, "urgent_count": 0}

        try:
            data["job_stats"] = db.get_job_stats(uid)
        except Exception:
            data["job_stats"] = {"total_jobs": 0, "total_applications": 0}

        try:
            data["tasks"] = db.get_tasks(uid) or []
        except Exception:
            data["tasks"] = []

        try:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
            events = json.loads(calendar_get_events(user_id=uid, time_min=start, time_max=end))
            data["events"] = events.get("events", [])
        except Exception:
            data["events"] = []

        try:
            data["top_matches"] = db.get_top_job_matches(uid, limit=5)
        except Exception:
            data["top_matches"] = []

        try:
            data["pending_emails"] = db.get_pending_emails(uid) or []
        except Exception:
            data["pending_emails"] = []

        try:
            data["lead_stats"] = db.get_lead_stats(uid)
            data["outreach_stats"] = db.get_outreach_stats(uid)
        except Exception:
            data["lead_stats"] = {"total_leads": 0}
            data["outreach_stats"] = {"total": 0}

        return _cors_json(data)
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/email-stats")
def api_email_stats():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json(db.get_email_analysis_stats(uid, hours=168))
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/email-queue")
def api_email_queue():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        all_emails = db.supabase.table("email_queue").select("*").eq("user_id", uid).order("scheduled_time", desc=True).limit(50).execute()
        return _cors_json({"emails": all_emails.data or []})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/job-stats")
def api_job_stats():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json(db.get_job_stats(uid))
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/jobs")
def api_jobs():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"jobs": db.get_jobs(uid, limit=100)})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/applications")
def api_applications():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"applications": db.get_job_applications(uid, limit=100)})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/top-matches")
def api_top_matches():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"matches": db.get_top_job_matches(uid, limit=10)})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/tasks")
def api_tasks():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"tasks": db.get_tasks(uid) or []})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/calendar")
def api_calendar():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        from tools.calendar_tool import calendar_get_events
        user = db.get_user(uid)
        tz_name = user.get("timezone", config.TIMEZONE) if user else config.TIMEZONE
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        events = json.loads(calendar_get_events(user_id=uid, time_min=start, time_max=end))
        return _cors_json(events)
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/leads")
def api_leads():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"leads": db.get_leads(uid, limit=100)})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/lead-stats")
def api_lead_stats():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        stats = db.get_lead_stats(uid)
        stats["outreach"] = db.get_outreach_stats(uid)
        return _cors_json(stats)
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/outreach")
def api_outreach():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        return _cors_json({"messages": db.get_outreach_messages(uid, limit=100)})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/job-search-data")
def api_job_search_data():
    uid = _require_uid()
    if not uid:
        return _cors_json({"error": "Not logged in.", "code": "AUTH_REQUIRED"}, 401)
    try:
        jobs_raw = db.get_jobs(uid, limit=200)
        apps_raw = db.get_job_applications(uid, limit=200)
        cv = db.get_cv(uid)
        stats = db.get_job_stats(uid)

        jobs = [{"id": j.get("id"), "title": j.get("title", ""), "company": j.get("company", ""),
                 "location": j.get("location", ""), "salary": j.get("salary", ""), "source": j.get("source", ""),
                 "link": j.get("application_link", ""), "description": j.get("description", "")} for j in (jobs_raw or [])]

        applications = []
        for a in (apps_raw or []):
            job = a.get("jobs", {}) or {}
            applications.append({"id": a.get("id"), "job_id": a.get("job_id"), "title": job.get("title", ""),
                "company": job.get("company", ""), "score": a.get("match_score", 0), "status": a.get("status", "pending"),
                "summary": a.get("summary", ""), "draft": a.get("draft_email", ""), "link": job.get("application_link", "")})

        return _cors_json({"jobs": jobs, "applications": applications, "cv": cv or "", "stats": stats})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


# ── POST endpoints ──

@app.route("/api/send-outreach", methods=["POST"])
def api_send_outreach():
    body = request.get_json(force=True) or {}
    uid = body.get("uid") or _get_uid()
    if not uid:
        return _cors_json({"error": "Login required", "code": "AUTH_REQUIRED"}, 401)
    try:
        to = body.get("to", "").strip()
        subject = body.get("subject", "").strip()
        email_body = body.get("body", "").strip()
        msg_id = body.get("message_id")
        if not to or not subject or not email_body:
            return _cors_json({"error": "Missing to, subject, or body"}, 400)
        from tools.gmail_tool import gmail_send
        result = json.loads(gmail_send(user_id=uid, to=to, subject=subject, message=email_body))
        if "error" in result:
            return _cors_json({"error": result["error"]}, 500)
        if msg_id:
            db.update_outreach_message(int(msg_id), {"status": "sent", "sent_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat()})
        return _cors_json({"success": True, "message_id": result.get("message_id")})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/update-outreach", methods=["POST"])
def api_update_outreach():
    body = request.get_json(force=True) or {}
    msg_id = body.get("message_id")
    status = body.get("status")
    if not msg_id or not status:
        return _cors_json({"error": "Missing message_id or status"}, 400)
    try:
        db.update_outreach_message(int(msg_id), {"status": status})
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/update-lead", methods=["POST"])
def api_update_lead():
    body = request.get_json(force=True) or {}
    lead_id = body.get("lead_id")
    status = body.get("status")
    if not lead_id or not status:
        return _cors_json({"error": "Missing lead_id or status"}, 400)
    try:
        db.update_lead(int(lead_id), {"status": status})
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/save-outreach-draft", methods=["POST"])
def api_save_outreach_draft():
    body = request.get_json(force=True) or {}
    msg_id = body.get("message_id")
    if not msg_id:
        return _cors_json({"error": "Missing message_id"}, 400)
    try:
        updates = {}
        if body.get("subject") is not None:
            updates["subject"] = body["subject"]
        if body.get("body") is not None:
            updates["body_content"] = body["body"]
        db.update_outreach_message(int(msg_id), updates)
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/job-scan", methods=["POST"])
def api_job_scan():
    body = request.get_json(force=True) or {}
    uid = body.get("uid") or _get_uid()
    try:
        keywords = body.get("keywords", "")
        max_per_source = body.get("max_per_source", 30)
        from job_scanner import run_job_scan
        kw_list = keywords if isinstance(keywords, list) else [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
        result = run_job_scan(keywords=kw_list, max_per_source=int(max_per_source), user_id=uid)
        return _cors_json({"success": True, **result})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/job-analyze", methods=["POST"])
def api_job_analyze():
    body = request.get_json(force=True) or {}
    uid = body.get("uid") or _get_uid()
    try:
        from job_scanner import run_job_analysis
        result = run_job_analysis(min_score=int(body.get("min_score", 50)), max_jobs=int(body.get("max_jobs", 20)), user_id=uid)
        return _cors_json({"success": True, **result})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/save-cv", methods=["POST"])
def api_save_cv():
    body = request.get_json(force=True) or {}
    uid = body.get("uid") or _get_uid()
    cv_content = body.get("content", "").strip()
    if not cv_content:
        return _cors_json({"error": "CV content is empty"}, 400)
    try:
        if uid:
            db.supabase.table("cv").delete().eq("user_id", uid).execute()
            db.supabase.table("cv").insert({"user_id": uid, "content": cv_content, "filename": "web_upload",
                "uploaded_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat()}).execute()
        else:
            db.supabase.table("cv").delete().neq("id", 0).execute()
            db.supabase.table("cv").insert({"content": cv_content, "filename": "web_upload",
                "uploaded_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat()}).execute()
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/update-app-status", methods=["POST"])
def api_update_app_status():
    body = request.get_json(force=True) or {}
    app_id = body.get("app_id")
    status = body.get("status")
    if not app_id or not status:
        return _cors_json({"error": "Missing app_id or status"}, 400)
    try:
        db.supabase.table("applications").update({"status": status}).eq("id", int(app_id)).execute()
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/save-app-draft", methods=["POST"])
def api_save_app_draft():
    body = request.get_json(force=True) or {}
    app_id = body.get("app_id")
    if not app_id:
        return _cors_json({"error": "Missing app_id"}, 400)
    try:
        db.supabase.table("applications").update({"draft_email": body.get("draft", "")}).eq("id", int(app_id)).execute()
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.route("/api/send-app-email", methods=["POST"])
def api_send_app_email():
    body = request.get_json(force=True) or {}
    uid = body.get("uid") or _get_uid()
    if not uid:
        return _cors_json({"error": "Login required", "code": "AUTH_REQUIRED"}, 401)
    try:
        to = body.get("to", "").strip()
        subject = body.get("subject", "").strip()
        email_body = body.get("body", "").strip()
        app_id = body.get("app_id")
        if not to or not subject or not email_body:
            return _cors_json({"error": "Missing to, subject, or body"}, 400)
        from tools.gmail_tool import gmail_send
        result = json.loads(gmail_send(user_id=uid, to=to, subject=subject, message=email_body))
        if "error" in result:
            return _cors_json({"error": result["error"]}, 500)
        if app_id:
            db.supabase.table("applications").update({"status": "sent",
                "sent_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat()}).eq("id", int(app_id)).execute()
        return _cors_json({"success": True})
    except Exception as e:
        return _cors_json({"error": str(e)}, 500)


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, ngrok-skip-browser-warning"
    return resp


@app.route("/api/<path:path>", methods=["OPTIONS"])
def api_options(path):
    resp = Response("")
    return resp


# ══════════════════════════════════════════════════
#  STATIC FILES (Dashboard)
# ══════════════════════════════════════════════════

@app.route("/")
def serve_dashboard():
    return send_file(BASE_DIR / "dashboard.html")


@app.route("/jobs")
def serve_jobs():
    return send_file(BASE_DIR / "job_search.html")


@app.route("/<path:filename>")
def serve_static(filename):
    file_path = BASE_DIR / filename
    if file_path.is_file() and not filename.startswith("."):
        content_type, _ = mimetypes.guess_type(str(file_path))
        return send_file(file_path, mimetype=content_type)
    return "Not found", 404


# ══════════════════════════════════════════════════
#  SERVER STARTUP
# ══════════════════════════════════════════════════

def _run_flask(port):
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e) or "10048" in str(e):
            logger.warning(f"Port {port} busy, trying {port + 1}...")
            try:
                app.run(host="0.0.0.0", port=port + 1, debug=False, use_reloader=False)
            except Exception as e2:
                logger.error(f"Server failed to start: {e2}")
        else:
            logger.error(f"Server failed: {e}")
    except Exception as e:
        logger.error(f"Server failed: {e}")


def run_oauth_server():
    """Run the OAuth + Dashboard server in a background thread."""
    port = config.OAUTH_PORT
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)
    thread = threading.Thread(target=_run_flask, args=(port,), daemon=True, name="OAuthDashboardServer")
    thread.start()
    logger.info(f"OAuth + Dashboard server started on port {port}")
    return thread
