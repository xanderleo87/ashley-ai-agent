"""
Job Search tools - Ashley can query job listings, applications,
and provide career insights. Multi-user: scoped by user_id.
"""

import json
from openai import OpenAI
import config
import database as db

client = OpenAI(api_key=config.OPENAI_API_KEY)


def job_search_stats(user_id: str) -> str:
    """Get job search overview stats."""
    try:
        stats = db.get_job_stats(user_id)
        sources = stats.get("sources", {})
        src_parts = [f"{k}: {v}" for k, v in sorted(sources.items(), key=lambda x: -x[1])]

        return json.dumps({
            "message": "Job search stats retrieved.",
            "total_active_jobs": stats["total_jobs"],
            "total_applications": stats["total_applications"],
            "pending_review": stats["pending"],
            "approved": stats["approved"],
            "sent": stats["sent"],
            "avg_match_score": stats["avg_score"],
            "jobs_by_source": ", ".join(src_parts) if src_parts else "No jobs yet",
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def job_search_browse(user_id: str, keyword: str = "", source: str = "", limit: str = "10") -> str:
    """Browse job listings with optional keyword and source filter."""
    try:
        lim = min(int(limit), 20)
    except ValueError:
        lim = 10

    try:
        if keyword:
            jobs = db.get_jobs_by_keyword(user_id, keyword, limit=lim)
        elif source:
            jobs = db.get_jobs(user_id, source=source, limit=lim)
        else:
            jobs = db.get_jobs(user_id, limit=lim)

        if not jobs:
            return json.dumps({"message": "No jobs found matching your criteria.", "jobs": []})

        formatted = []
        for j in jobs:
            formatted.append({
                "title": j.get("title", "?"),
                "company": j.get("company", "?"),
                "location": j.get("location", ""),
                "salary": j.get("salary", ""),
                "source": j.get("source", ""),
                "link": j.get("application_link", ""),
            })

        return json.dumps({
            "message": f"Found {len(formatted)} job(s).",
            "jobs": formatted,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def job_search_applications(user_id: str, status: str = "") -> str:
    """Get job applications with optional status filter."""
    try:
        apps = db.get_job_applications(user_id, status=status if status else None, limit=15)

        if not apps:
            return json.dumps({"message": "No applications found.", "applications": []})

        formatted = []
        for a in apps:
            job = a.get("jobs", {}) or {}
            formatted.append({
                "title": job.get("title", "?"),
                "company": job.get("company", "?"),
                "score": a.get("match_score", 0),
                "status": a.get("status", "?"),
                "summary": a.get("summary", "")[:150],
                "link": job.get("application_link", ""),
            })

        return json.dumps({
            "message": f"Found {len(formatted)} application(s).",
            "applications": formatted,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def job_search_top_matches(user_id: str, limit: str = "5") -> str:
    """Get top job matches by AI score."""
    try:
        lim = min(int(limit), 10)
    except ValueError:
        lim = 5

    try:
        matches = db.get_top_job_matches(user_id, limit=lim)

        if not matches:
            return json.dumps({"message": "No matches found. Run job analysis first.", "matches": []})

        formatted = []
        for m in matches:
            job = m.get("jobs", {}) or {}
            formatted.append({
                "title": job.get("title", "?"),
                "company": job.get("company", "?"),
                "score": m.get("match_score", 0),
                "status": m.get("status", "?"),
                "summary": m.get("summary", "")[:200],
                "link": job.get("application_link", ""),
            })

        return json.dumps({
            "message": f"Top {len(formatted)} job matches.",
            "matches": formatted,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def job_search_scan(user_id: str, keywords: str = "", max_per_source: str = "30") -> str:
    """Scan all job sources for new listings and save to database."""
    try:
        from job_scanner import run_job_scan

        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
        try:
            mps = min(int(max_per_source), 50)
        except ValueError:
            mps = 30

        result = run_job_scan(keywords=kw_list, max_per_source=mps, user_id=user_id)

        sources = result.get("sources", {})
        src_parts = [f"{k}: {v}" for k, v in sorted(sources.items(), key=lambda x: -x[1])]

        return json.dumps({
            "message": f"Job scan complete! Scraped {result['total_scraped']} jobs, saved {result['total_saved']} new to database.",
            "total_scraped": result["total_scraped"],
            "total_saved": result["total_saved"],
            "keywords_used": result.get("keywords", []),
            "jobs_by_source": ", ".join(src_parts) if src_parts else "No results",
        })
    except Exception as e:
        return json.dumps({"error": f"Job scan failed: {str(e)}"})


def job_search_analyze(user_id: str, min_score: str = "50", max_jobs: str = "20") -> str:
    """Analyze unprocessed jobs against CV and create application drafts."""
    try:
        from job_scanner import run_job_analysis

        try:
            ms = max(0, min(100, int(min_score)))
        except ValueError:
            ms = 50
        try:
            mj = min(int(max_jobs), 50)
        except ValueError:
            mj = 20

        result = run_job_analysis(min_score=ms, max_jobs=mj, user_id=user_id)

        if "error" in result:
            return json.dumps(result)

        return json.dumps({
            "message": f"Analysis complete! Analyzed {result.get('jobs_analyzed', 0)} jobs, created {result.get('applications_created', 0)} applications (min score: {ms}).",
            **result,
        })
    except Exception as e:
        return json.dumps({"error": f"Job analysis failed: {str(e)}"})


def job_search_career_advice(user_id: str, question: str) -> str:
    """Ashley reasons about your job search and gives career advice."""
    context_parts = []

    try:
        stats = db.get_job_stats(user_id)
        context_parts.append(f"JOB STATS: {json.dumps(stats)}")
    except Exception:
        pass

    try:
        top = db.get_top_job_matches(user_id, limit=5)
        top_summary = []
        for m in top:
            job = m.get("jobs", {}) or {}
            top_summary.append({
                "title": job.get("title", "?"),
                "company": job.get("company", "?"),
                "score": m.get("match_score", 0),
                "status": m.get("status", "?"),
            })
        context_parts.append(f"TOP MATCHES: {json.dumps(top_summary)}")
    except Exception:
        pass

    try:
        cv = db.get_cv(user_id)
        if cv:
            context_parts.append(f"CV SUMMARY (first 1500 chars): {cv[:1500]}")
    except Exception:
        pass

    context = "\n".join(context_parts)

    # Get user name
    user = db.get_user(user_id)
    user_name = user.get("name", "Boss") if user else "Boss"

    prompt = f"""You are Ashley, an elite AI career advisor for {user_name}.
Use the job search data below to answer the question with specific, actionable advice.
Reference actual job titles, companies, and scores from the data.

DATA:
{context}

QUESTION: {question}

Give clear, specific career advice. Be concise but thorough."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5,
        )
        answer = response.choices[0].message.content.strip()
        return json.dumps({"advice": answer})
    except Exception as e:
        return json.dumps({"error": f"Career advice failed: {str(e)}"})
