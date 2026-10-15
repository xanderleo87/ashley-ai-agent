"""
Ashley AI Agent - Dashboard Server (Multi-User)
Serves the Ashley dashboard HTML and provides API endpoints
for email analysis, job search, calendar, tasks, and insights.
Each user is identified by ?uid=<telegram_chat_id> on API calls.
"""

import asyncio
import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import pytz

import sys
sys.path.insert(0, str(Path(__file__).parent))

import config
import database as db
from tools.calendar_tool import calendar_get_events
from reasoning import analyze_email


def run_sync(fn, *args, **kwargs):
    """Run a function (handles both sync and async)."""
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(result)
        finally:
            loop.close()
    return result


class AshleyDashboardHandler(BaseHTTPRequestHandler):
    """Handle static files and API requests for Ashley's dashboard."""

    BASE_DIR = Path(__file__).parent

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _get_uid(self):
        """Extract user_id (uid) from query params."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        uid = params.get("uid", [None])[0]
        return uid

    def _require_uid(self):
        """Get uid or send 401. Returns uid or None (if error sent)."""
        uid = self._get_uid()
        if not uid:
            self._send_json({"error": "Not logged in. Please log in first.", "code": "AUTH_REQUIRED"}, 401)
            return None
        return uid

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        # API: Login - verify user by email
        if path == "/api/auth":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            email = params.get("email", [None])[0]
            if not email:
                self._send_json({"error": "Email required"}, 400)
                return
            try:
                result = db.supabase.table("users").select("*").eq("email", email.strip().lower()).eq("is_approved", True).limit(1).execute()
                if result.data:
                    user = result.data[0]
                    self._send_json({
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
                    self._send_json({"error": "Account not found or not approved."}, 403)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Full dashboard data
        if path == "/api/dashboard":
            uid = self._require_uid()
            if not uid:
                return
            try:
                self._send_json(self._get_dashboard_data(uid))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Email stats
        if path == "/api/email-stats":
            uid = self._require_uid()
            if not uid:
                return
            try:
                stats = db.get_email_analysis_stats(uid, hours=168)
                self._send_json(stats)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Job stats
        if path == "/api/job-stats":
            uid = self._require_uid()
            if not uid:
                return
            try:
                stats = db.get_job_stats(uid)
                self._send_json(stats)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Jobs list
        if path == "/api/jobs":
            uid = self._require_uid()
            if not uid:
                return
            try:
                jobs = db.get_jobs(uid, limit=100)
                self._send_json({"jobs": jobs})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Job applications
        if path == "/api/applications":
            uid = self._require_uid()
            if not uid:
                return
            try:
                apps = db.get_job_applications(uid, limit=100)
                self._send_json({"applications": apps})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Top matches
        if path == "/api/top-matches":
            uid = self._require_uid()
            if not uid:
                return
            try:
                matches = db.get_top_job_matches(uid, limit=10)
                self._send_json({"matches": matches})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Tasks
        if path == "/api/tasks":
            uid = self._require_uid()
            if not uid:
                return
            try:
                tasks = db.get_tasks(uid) or []
                self._send_json({"tasks": tasks})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Today's calendar
        if path == "/api/calendar":
            uid = self._require_uid()
            if not uid:
                return
            try:
                user = db.get_user(uid)
                tz_name = user.get("timezone", config.TIMEZONE) if user else config.TIMEZONE
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)
                start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
                events = json.loads(calendar_get_events(user_id=uid, time_min=start, time_max=end))
                self._send_json(events)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Leads
        if path == "/api/leads":
            uid = self._require_uid()
            if not uid:
                return
            try:
                leads = db.get_leads(uid, limit=100)
                self._send_json({"leads": leads})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Lead stats
        if path == "/api/lead-stats":
            uid = self._require_uid()
            if not uid:
                return
            try:
                stats = db.get_lead_stats(uid)
                outreach = db.get_outreach_stats(uid)
                stats["outreach"] = outreach
                self._send_json(stats)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Outreach messages
        if path == "/api/outreach":
            uid = self._require_uid()
            if not uid:
                return
            try:
                messages = db.get_outreach_messages(uid, limit=100)
                self._send_json({"messages": messages})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Job search data
        if path == "/api/job-search-data":
            uid = self._require_uid()
            if not uid:
                return
            try:
                jobs_raw = db.get_jobs(uid, limit=200)
                apps_raw = db.get_job_applications(uid, limit=200)
                cv = db.get_cv(uid)
                stats = db.get_job_stats(uid)

                jobs = []
                for j in (jobs_raw or []):
                    jobs.append({
                        "id": j.get("id"),
                        "title": j.get("title", ""),
                        "company": j.get("company", ""),
                        "location": j.get("location", ""),
                        "salary": j.get("salary", ""),
                        "source": j.get("source", ""),
                        "link": j.get("application_link", ""),
                        "description": j.get("description", ""),
                    })

                applications = []
                for a in (apps_raw or []):
                    job = a.get("jobs", {}) or {}
                    applications.append({
                        "id": a.get("id"),
                        "job_id": a.get("job_id"),
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "score": a.get("match_score", 0),
                        "status": a.get("status", "pending"),
                        "summary": a.get("summary", ""),
                        "draft": a.get("draft_email", ""),
                        "link": job.get("application_link", ""),
                    })

                self._send_json({
                    "jobs": jobs,
                    "applications": applications,
                    "cv": cv or "",
                    "stats": stats,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Static files
        if path == "/" or path == "":
            path = "/dashboard.html"
        elif path == "/jobs":
            path = "/job_search.html"

        file_path = self.BASE_DIR / path.lstrip("/")
        if file_path.is_file():
            content_type, _ = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        uid = self._get_uid()

        # For POST requests, also check uid from body as fallback
        def get_uid_from_body(body):
            return body.get("uid") or uid

        # Send outreach email
        if path == "/api/send-outreach":
            try:
                body = self._read_body()
                user_id = get_uid_from_body(body)
                if not user_id:
                    self._send_json({"error": "Login required", "code": "AUTH_REQUIRED"}, 401)
                    return
                msg_id = body.get("message_id")
                to = body.get("to", "").strip()
                subject = body.get("subject", "").strip()
                email_body = body.get("body", "").strip()

                if not to or not subject or not email_body:
                    self._send_json({"error": "Missing to, subject, or body"}, 400)
                    return

                from tools.gmail_tool import gmail_send
                result = json.loads(gmail_send(user_id=user_id, to=to, subject=subject, message=email_body))

                if "error" in result:
                    self._send_json({"error": result["error"]}, 500)
                else:
                    if msg_id:
                        db.update_outreach_message(int(msg_id), {
                            "status": "sent",
                            "sent_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat(),
                        })
                    self._send_json({"success": True, "message_id": result.get("message_id")})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Update outreach message status
        if path == "/api/update-outreach":
            try:
                body = self._read_body()
                msg_id = body.get("message_id")
                status = body.get("status")
                if not msg_id or not status:
                    self._send_json({"error": "Missing message_id or status"}, 400)
                    return
                db.update_outreach_message(int(msg_id), {"status": status})
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Update lead status
        if path == "/api/update-lead":
            try:
                body = self._read_body()
                lead_id = body.get("lead_id")
                status = body.get("status")
                if not lead_id or not status:
                    self._send_json({"error": "Missing lead_id or status"}, 400)
                    return
                db.update_lead(int(lead_id), {"status": status})
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Save edited outreach draft
        if path == "/api/save-outreach-draft":
            try:
                body = self._read_body()
                msg_id = body.get("message_id")
                subject = body.get("subject")
                draft = body.get("body")
                if not msg_id:
                    self._send_json({"error": "Missing message_id"}, 400)
                    return
                updates = {}
                if subject is not None:
                    updates["subject"] = subject
                if draft is not None:
                    updates["body_content"] = draft
                db.update_outreach_message(int(msg_id), updates)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Run scan
        if path == "/api/job-scan":
            try:
                body = self._read_body()
                user_id = get_uid_from_body(body)
                keywords = body.get("keywords", "")
                max_per_source = body.get("max_per_source", 30)
                from job_scanner import run_job_scan
                kw_list = keywords if isinstance(keywords, list) else [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
                result = run_job_scan(keywords=kw_list, max_per_source=int(max_per_source), user_id=user_id)
                self._send_json({"success": True, **result})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Run AI analysis
        if path == "/api/job-analyze":
            try:
                body = self._read_body()
                user_id = get_uid_from_body(body)
                min_score = int(body.get("min_score", 50))
                max_jobs = int(body.get("max_jobs", 20))
                from job_scanner import run_job_analysis
                result = run_job_analysis(min_score=min_score, max_jobs=max_jobs, user_id=user_id)
                self._send_json({"success": True, **result})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Save CV
        if path == "/api/save-cv":
            try:
                body = self._read_body()
                user_id = get_uid_from_body(body)
                cv_content = body.get("content", "").strip()
                if not cv_content:
                    self._send_json({"error": "CV content is empty"}, 400)
                    return
                if user_id:
                    db.supabase.table("cv").delete().eq("user_id", user_id).execute()
                    db.supabase.table("cv").insert({
                        "user_id": user_id,
                        "content": cv_content,
                        "filename": "web_upload",
                        "uploaded_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat(),
                    }).execute()
                else:
                    db.supabase.table("cv").delete().neq("id", 0).execute()
                    db.supabase.table("cv").insert({
                        "content": cv_content,
                        "filename": "web_upload",
                        "uploaded_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat(),
                    }).execute()
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Update application status
        if path == "/api/update-app-status":
            try:
                body = self._read_body()
                app_id = body.get("app_id")
                status = body.get("status")
                if not app_id or not status:
                    self._send_json({"error": "Missing app_id or status"}, 400)
                    return
                db.supabase.table("applications").update({"status": status}).eq("id", int(app_id)).execute()
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Save application draft
        if path == "/api/save-app-draft":
            try:
                body = self._read_body()
                app_id = body.get("app_id")
                draft = body.get("draft", "")
                if not app_id:
                    self._send_json({"error": "Missing app_id"}, 400)
                    return
                db.supabase.table("applications").update({"draft_email": draft}).eq("id", int(app_id)).execute()
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # Job search: Send application email
        if path == "/api/send-app-email":
            try:
                body = self._read_body()
                user_id = get_uid_from_body(body)
                if not user_id:
                    self._send_json({"error": "Login required", "code": "AUTH_REQUIRED"}, 401)
                    return
                to = body.get("to", "").strip()
                subject = body.get("subject", "").strip()
                email_body = body.get("body", "").strip()
                app_id = body.get("app_id")
                if not to or not subject or not email_body:
                    self._send_json({"error": "Missing to, subject, or body"}, 400)
                    return
                from tools.gmail_tool import gmail_send
                result = json.loads(gmail_send(user_id=user_id, to=to, subject=subject, message=email_body))
                if "error" in result:
                    self._send_json({"error": result["error"]}, 500)
                else:
                    if app_id:
                        db.supabase.table("applications").update({
                            "status": "sent",
                            "sent_at": datetime.now(pytz.timezone(config.TIMEZONE)).isoformat(),
                        }).eq("id", int(app_id)).execute()
                    self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": "Not found"}, 404)

    def _get_dashboard_data(self, uid):
        """Aggregate all data for the dashboard, scoped to user."""
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

        # Email stats
        try:
            data["email_stats"] = db.get_email_analysis_stats(uid, hours=168)
        except Exception:
            data["email_stats"] = {"total": 0, "categories": {}, "spam_count": 0, "suspicious_count": 0, "urgent_count": 0}

        # Job stats
        try:
            data["job_stats"] = db.get_job_stats(uid)
        except Exception:
            data["job_stats"] = {"total_jobs": 0, "total_applications": 0}

        # Tasks
        try:
            data["tasks"] = db.get_tasks(uid) or []
        except Exception:
            data["tasks"] = []

        # Today's calendar
        try:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
            events = json.loads(calendar_get_events(user_id=uid, time_min=start, time_max=end))
            data["events"] = events.get("events", [])
        except Exception:
            data["events"] = []

        # Top matches
        try:
            matches = db.get_top_job_matches(uid, limit=5)
            data["top_matches"] = matches
        except Exception:
            data["top_matches"] = []

        # Pending emails
        try:
            data["pending_emails"] = db.get_pending_emails(uid) or []
        except Exception:
            data["pending_emails"] = []

        # Lead stats
        try:
            data["lead_stats"] = db.get_lead_stats(uid)
            data["outreach_stats"] = db.get_outreach_stats(uid)
        except Exception:
            data["lead_stats"] = {"total_leads": 0}
            data["outreach_stats"] = {"total": 0}

        return data

    def log_message(self, format, *args):
        print(f"[Ashley Dashboard] {args[0]}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = HTTPServer(("0.0.0.0", port), AshleyDashboardHandler)
    print(f"\n  Ashley AI Dashboard running at: http://localhost:{port}/")
    print(f"  API: http://localhost:{port}/api/dashboard?uid=<chat_id>")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
