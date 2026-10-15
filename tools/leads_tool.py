"""
Lead generation tools - Ashley can scrape Google Maps,
analyze business websites, compose outreach, and manage leads.
Multi-user: all data scoped by user_id.
"""

import json
import database as db
from lead_scraper import scrape_and_process


def leads_scrape(user_id: str, query: str, location: str = "", max_results: str = "15") -> str:
    """Scrape businesses from Google Maps, analyze their websites, and compose outreach."""
    try:
        mx = min(int(max_results), 30)
    except ValueError:
        mx = 15

    try:
        result = scrape_and_process(query=query, location=location, max_results=mx, user_id=user_id)

        if "error" in result:
            return json.dumps({"error": result["error"]})

        return json.dumps({
            "message": f"Lead scraping complete!",
            "leads_found": result["leads_found"],
            "leads_saved": result["leads_saved"],
            "websites_analyzed": result["websites_analyzed"],
            "messages_composed": result["messages_composed"],
            "note": "Check the Ashley dashboard to review leads and outreach messages.",
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def leads_browse(user_id: str, status: str = "", limit: str = "10") -> str:
    """Browse scraped leads with optional status filter."""
    try:
        lim = min(int(limit), 20)
    except ValueError:
        lim = 10

    try:
        leads = db.get_leads(user_id, status=status if status else None, limit=lim)
        if not leads:
            return json.dumps({"message": "No leads found.", "leads": []})

        formatted = []
        for l in leads:
            formatted.append({
                "id": l.get("id"),
                "business": l.get("business_name", "?"),
                "category": l.get("category", ""),
                "email": l.get("email", ""),
                "phone": l.get("phone", ""),
                "website": l.get("website", ""),
                "rating": l.get("rating"),
                "reviews": l.get("review_count", 0),
                "lead_score": l.get("lead_score", 0),
                "status": l.get("status", "new"),
                "analysis": l.get("website_analysis", "")[:150],
            })

        return json.dumps({
            "message": f"Found {len(formatted)} lead(s).",
            "leads": formatted,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def leads_stats(user_id: str) -> str:
    """Get lead generation statistics."""
    try:
        lead_stats = db.get_lead_stats(user_id)
        outreach_stats = db.get_outreach_stats(user_id)

        return json.dumps({
            "message": "Lead stats retrieved.",
            "total_leads": lead_stats["total_leads"],
            "new": lead_stats["new"],
            "contacted": lead_stats["contacted"],
            "replied": lead_stats["replied"],
            "converted": lead_stats["converted"],
            "avg_lead_score": lead_stats["avg_lead_score"],
            "outreach_total": outreach_stats["total"],
            "outreach_drafts": outreach_stats["drafts"],
            "outreach_sent": outreach_stats["sent"],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def leads_outreach_messages(user_id: str, status: str = "") -> str:
    """Get outreach messages with optional status filter."""
    try:
        messages = db.get_outreach_messages(user_id, status=status if status else None, limit=15)
        if not messages:
            return json.dumps({"message": "No outreach messages found.", "messages": []})

        formatted = []
        for m in messages:
            lead = m.get("leads", {}) or {}
            formatted.append({
                "id": m.get("id"),
                "business": lead.get("business_name", "?"),
                "to": m.get("recipient_email", "?"),
                "subject": m.get("subject", ""),
                "body_preview": (m.get("body_content", ""))[:150],
                "service": m.get("service_offered", ""),
                "status": m.get("status", "draft"),
            })

        return json.dumps({
            "message": f"Found {len(formatted)} outreach message(s).",
            "messages": formatted,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
