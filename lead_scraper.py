"""
Ashley Lead Scraper - Google Maps Business Scraper via Apify.
Scrapes businesses, extracts contact info, analyzes websites,
scores leads, and composes personalized outreach messages.
"""

import json
import re
import httpx
from openai import OpenAI
import config
import database as db

client = OpenAI(api_key=config.OPENAI_API_KEY)

APIFY_BASE = "https://api.apify.com/v2"


def scrape_google_maps(query: str, location: str = "", max_results: int = 20) -> list:
    """
    Scrape businesses from Google Maps using Apify.
    Returns list of scraped business data.
    """
    if not config.APIFY_API_KEY:
        return [{"error": "APIFY_API_KEY not configured"}]

    # Apify Google Maps Scraper actor
    actor_id = "nwua9Gu5YrADL7ZDj"  # compass/Google-Maps-Scraper
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"

    search_term = f"{query} {location}".strip() if location else query

    payload = {
        "searchStringsArray": [search_term],
        "maxCrawledPlacesPerSearch": max_results,
        "language": "en",
        "includeWebResults": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.APIFY_API_KEY}",
    }

    try:
        print(f"[Lead Scraper] Scraping Google Maps: '{search_term}' (max {max_results})")
        response = httpx.post(
            url, json=payload, headers=headers,
            timeout=180,
        )
        print(f"[Lead Scraper] Apify response status: {response.status_code}")
        response.raise_for_status()
        results = response.json()
        print(f"[Lead Scraper] Response type: {type(results).__name__}, length: {len(results) if isinstance(results, list) else 'N/A'}")

        # Handle unexpected response formats
        if isinstance(results, dict):
            # Apify might wrap results in a dict
            results = results.get("items", results.get("data", [results]))
        if not isinstance(results, list):
            return [{"error": f"Unexpected Apify response format: {type(results).__name__}"}]

        leads = []
        for i, item in enumerate(results):
            if not isinstance(item, dict):
                print(f"[Lead Scraper] Skipping non-dict item #{i}: {type(item).__name__} = {str(item)[:100]}")
                continue
            try:
                lead = {
                    "place_id": item.get("placeId", ""),
                    "business_name": item.get("title", "Unknown Business"),
                    "category": item.get("categoryName", ""),
                    "address": item.get("address", ""),
                    "phone": item.get("phone", ""),
                    "email": _extract_email_from_item(item),
                    "website": item.get("website", ""),
                    "rating": item.get("totalScore"),
                    "review_count": item.get("reviewsCount", 0),
                    "google_maps_url": item.get("url", ""),
                    "search_query": search_term,
                    "status": "new",
                    "lead_score": 0,
                }
                leads.append(lead)
            except Exception as e:
                print(f"[Lead Scraper] Error parsing item #{i}: {e}")

        print(f"[Lead Scraper] Found {len(leads)} businesses")
        return leads

    except httpx.HTTPStatusError as e:
        print(f"[Lead Scraper] Apify HTTP error: {e.response.status_code} - {e.response.text[:200]}")
        return [{"error": f"Apify API error: {e.response.status_code}"}]
    except Exception as e:
        print(f"[Lead Scraper] Scrape error: {e}")
        return [{"error": str(e)}]


def _extract_email_from_item(item: dict) -> str:
    """Try to extract email from Apify result."""
    # Check direct email field
    if item.get("email"):
        return item["email"]
    # Check additional info (items can be dicts or strings)
    for info in item.get("additionalInfo", []):
        if isinstance(info, dict):
            val = str(info.get("value", ""))
            if "@" in val:
                return info["value"]
        elif isinstance(info, str) and "@" in info:
            return info
    return ""


def analyze_website(url: str, business_name: str, category: str) -> dict:
    """
    Analyze a business website using OpenAI to understand what they do,
    what they need, and how we can help them.
    """
    if not url:
        return {"analysis": "No website found", "needs": [], "score": 20}

    # Fetch website content
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; AshleyBot/1.0)"})
        html = resp.text[:8000]  # First 8000 chars
        # Strip HTML tags for cleaner text
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()[:3000]
    except Exception as e:
        return {"analysis": f"Could not fetch website: {e}", "needs": [], "score": 20}

    prompt = f"""You are Ashley, an elite business analyst. Analyze this business's website to identify:
1. What the business does
2. Their potential pain points or needs
3. How an AI automation expert / web developer could help them
4. Score this lead 0-100 (how likely they need our services)

BUSINESS: {business_name}
CATEGORY: {category}
WEBSITE URL: {url}
WEBSITE CONTENT:
{text}

OUR SERVICES: AI Automation Systems, Website Development, Small Scale Chat Apps with Supabase & AI, Business Problem Solving & Automation

Return valid JSON:
{{
    "what_they_do": "brief description",
    "pain_points": ["pain1", "pain2"],
    "how_we_help": "specific suggestion for this business",
    "lead_score": 0-100,
    "analysis_summary": "2-3 sentence summary"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
        return json.loads(result_text)
    except Exception as e:
        print(f"[Lead Scraper] Website analysis error: {e}")
        return {"analysis": "Analysis failed", "needs": [], "lead_score": 30}


def compose_outreach(lead: dict, analysis: dict, user_name: str = "Anasopie") -> dict:
    """
    Compose a personalized outreach message for a lead based on
    their business and website analysis.
    """
    prompt = f"""You are composing a cold outreach email on behalf of {user_name}, an AI Automation Engineer & Web Developer.

LEAD:
- Business: {lead.get('business_name', '?')}
- Category: {lead.get('category', '?')}
- What they do: {analysis.get('what_they_do', '?')}
- Pain points: {json.dumps(analysis.get('pain_points', []))}
- How we can help: {analysis.get('how_we_help', '?')}

OUR SERVICES:
- AI Automation Systems (workflow automation, AI agents, chatbots)
- Website Development (modern, fast, conversion-optimized)
- Chat Apps with Supabase & AI integration
- Business Process Automation & Problem Solving

RULES:
1. Keep it SHORT (under 150 words)
2. Open with something specific about THEIR business (show you did research)
3. Mention ONE specific way you can help them (based on the analysis)
4. No pushy sales talk. Be professional, friendly, and genuine
5. End with a soft CTA (e.g., "Would you be open to a quick chat?")
6. Sign off as: Best, {user_name}

Return valid JSON:
{{
    "subject": "email subject line",
    "body": "email body",
    "service_offered": "which service is most relevant"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
        return json.loads(result_text)
    except Exception as e:
        print(f"[Lead Scraper] Compose error: {e}")
        return {
            "subject": f"Quick question about {lead.get('business_name', 'your business')}",
            "body": "Could not generate message. Please compose manually.",
            "service_offered": "General",
        }


def scrape_and_process(query: str, location: str = "", max_results: int = 20, user_id: str = "") -> dict:
    """
    Full pipeline: Scrape Google Maps -> Analyze websites -> Score leads -> Compose outreach.
    Multi-user: user_id scopes all saved data.
    """
    # Step 1: Scrape
    raw_leads = scrape_google_maps(query, location, max_results)
    if not raw_leads:
        return {"error": "No results from Google Maps", "leads_found": 0}
    if isinstance(raw_leads[0], dict) and "error" in raw_leads[0]:
        return {"error": raw_leads[0]["error"], "leads_found": 0}

    # Get user name for outreach signature
    user_name = "Anasopie"
    if user_id:
        user = db.get_user(user_id)
        if user:
            user_name = user.get("name", "Anasopie")

    saved = 0
    analyzed = 0
    messages_composed = 0

    for lead_data in raw_leads:
        if not lead_data.get("place_id"):
            continue

        # Step 2: Analyze website
        analysis = {}
        if lead_data.get("website"):
            analysis = analyze_website(
                lead_data["website"],
                lead_data["business_name"],
                lead_data.get("category", ""),
            )
            lead_data["website_analysis"] = analysis.get("analysis_summary", "")
            lead_data["business_needs"] = json.dumps(analysis.get("pain_points", []))
            lead_data["lead_score"] = analysis.get("lead_score", 30)
            analyzed += 1
        else:
            lead_data["lead_score"] = 15

        # Step 3: Save lead to Supabase (scoped to user)
        try:
            db.save_lead(user_id, lead_data)
            saved += 1
        except Exception as e:
            print(f"[Lead Scraper] Failed to save lead: {e}")
            continue

        # Step 4: Compose outreach for leads with email and decent score
        if lead_data.get("email") and lead_data.get("lead_score", 0) >= 40:
            outreach = compose_outreach(lead_data, analysis, user_name=user_name)

            # Get the lead ID from database
            try:
                db_lead = db.get_leads(user_id, limit=1)
                lead_id = db_lead[0]["id"] if db_lead else None
            except Exception:
                lead_id = None

            msg_data = {
                "lead_id": lead_id,
                "recipient_email": lead_data["email"],
                "subject": outreach.get("subject", ""),
                "body_content": outreach.get("body", ""),
                "service_offered": outreach.get("service_offered", ""),
                "status": "draft",
            }
            try:
                db.save_outreach_message(user_id, msg_data)
                messages_composed += 1
            except Exception as e:
                print(f"[Lead Scraper] Failed to save outreach: {e}")

    return {
        "leads_found": len(raw_leads),
        "leads_saved": saved,
        "websites_analyzed": analyzed,
        "messages_composed": messages_composed,
    }
