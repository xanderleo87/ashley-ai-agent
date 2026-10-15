"""
Main job scanner - runs all 6 sources, deduplicates, saves to Supabase.
Ported from job_search_assistant to work within Ashley AI Agent.
"""

import asyncio
import logging
from datetime import datetime

import config
import database as db
from .models import Job
from .sources import (
    RemoteOKSource, ArbeitnowSource, LinkedInSource,
    GreenhouseSource, LeverSource, AdzunaSource, OnlineJobsPhSource,
)
from .dedup import deduplicate_jobs, content_hash
from .salary_parser import parse_salary

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "AI automation", "workflow automation", "N8N", "LLM",
    "AI engineer", "machine learning", "AI ops", "prompt engineering",
]


async def _scan_all_sources(
    keywords: list[str],
    max_per_source: int = 30,
    adzuna_app_id: str = "",
    adzuna_api_key: str = "",
    locations: list[str] = None,
) -> list[Job]:
    """Async function that searches all 6 sources."""
    all_jobs = []
    locations = locations or ["US", "UK"]

    # RemoteOK
    logger.info("Scanning RemoteOK...")
    try:
        jobs = await RemoteOKSource().search(keywords, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"RemoteOK: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"RemoteOK failed: {e}")

    # Arbeitnow
    logger.info("Scanning Arbeitnow...")
    try:
        jobs = await ArbeitnowSource().search(keywords, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"Arbeitnow: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"Arbeitnow failed: {e}")

    # LinkedIn
    logger.info("Scanning LinkedIn...")
    try:
        jobs = await LinkedInSource().search(keywords, location=locations[0] if locations else None, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"LinkedIn: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"LinkedIn failed: {e}")

    # Greenhouse ATS
    logger.info("Scanning Greenhouse ATS...")
    try:
        jobs = await GreenhouseSource().search(keywords, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"Greenhouse: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"Greenhouse failed: {e}")

    # Lever ATS
    logger.info("Scanning Lever ATS...")
    try:
        jobs = await LeverSource().search(keywords, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"Lever: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"Lever failed: {e}")

    # Adzuna (if configured)
    if adzuna_app_id and adzuna_api_key:
        logger.info("Scanning Adzuna...")
        try:
            adzuna = AdzunaSource(app_id=adzuna_app_id, api_key=adzuna_api_key)
            jobs = await adzuna.search_all_countries(keywords, locations, limit_per_country=max_per_source // max(len(locations), 1))
            all_jobs.extend(jobs)
            logger.info(f"Adzuna: {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Adzuna failed: {e}")
    else:
        logger.info("Adzuna not configured, skipping")

    # OnlineJobs.ph
    logger.info("Scanning OnlineJobs.ph...")
    try:
        jobs = await OnlineJobsPhSource().search(keywords, limit=max_per_source)
        all_jobs.extend(jobs)
        logger.info(f"OnlineJobs.ph: {len(jobs)} jobs")
    except Exception as e:
        logger.error(f"OnlineJobs.ph failed: {e}")

    return all_jobs


def _save_jobs_to_supabase(jobs: list[Job], user_id: str = "") -> int:
    """Save jobs to Supabase with dedup, salary parsing, and content hashing."""
    jobs = deduplicate_jobs(jobs)
    inserted = 0
    now = datetime.utcnow().isoformat()

    for job in jobs:
        try:
            salary_min, salary_max, salary_currency = None, None, "USD"
            if job.salary:
                parsed = parse_salary(job.salary)
                salary_min = parsed.min_annual
                salary_max = parsed.max_annual
                salary_currency = parsed.currency

            job_hash = content_hash(job.company, job.title, job.description)

            data = {
                "id": job.id,
                "source": job.source,
                "external_id": job.external_id,
                "company": job.company,
                "title": job.title,
                "location": job.location or "",
                "salary": job.salary,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_currency": salary_currency,
                "description": (job.description or "")[:10000],
                "application_link": job.application_link,
                "posted_date": job.posted_date.isoformat() if job.posted_date else None,
                "created_at": job.created_at.isoformat(),
                "last_seen_at": now,
                "content_hash": job_hash,
                "is_expired": False,
                "user_id": user_id,
            }

            db.supabase.table("jobs").upsert(data, on_conflict="id").execute()
            inserted += 1

        except Exception as e:
            logger.error(f"Error saving job {job.id}: {e}")

    return inserted


def run_job_scan(
    keywords: list[str] = None,
    max_per_source: int = 30,
    locations: list[str] = None,
    user_id: str = "",
) -> dict:
    """
    Run a full job scan across all 6 sources.
    Multi-user: saves jobs scoped to user_id.
    """
    keywords = keywords or DEFAULT_KEYWORDS
    locations = locations or ["US", "UK"]

    import os
    adzuna_app_id = os.getenv("ADZUNA_APP_ID", "")
    adzuna_api_key = os.getenv("ADZUNA_API_KEY", "")

    logger.info(f"Starting job scan for user {user_id} with keywords: {keywords}")

    loop = asyncio.new_event_loop()
    try:
        all_jobs = loop.run_until_complete(
            _scan_all_sources(
                keywords=keywords,
                max_per_source=max_per_source,
                adzuna_app_id=adzuna_app_id,
                adzuna_api_key=adzuna_api_key,
                locations=locations,
            )
        )
    finally:
        loop.close()

    total_scraped = len(all_jobs)
    logger.info(f"Total scraped: {total_scraped} jobs")

    inserted = _save_jobs_to_supabase(all_jobs, user_id=user_id)
    logger.info(f"Saved {inserted} jobs to database")

    source_counts = {}
    for job in all_jobs:
        source_counts[job.source] = source_counts.get(job.source, 0) + 1

    return {
        "total_scraped": total_scraped,
        "total_saved": inserted,
        "sources": source_counts,
        "keywords": keywords,
    }


def run_job_analysis(min_score: int = 50, max_jobs: int = 20, user_id: str = "") -> dict:
    """
    Analyze unprocessed jobs against CV using AI.
    Multi-user: scoped to user_id.
    """
    from openai import OpenAI
    import json

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    cv_content = db.get_cv(user_id)
    if not cv_content:
        return {"error": "No CV found. Please upload a CV first."}

    # Get jobs without applications for this user
    apps_result = db.supabase.table("applications").select("job_id").eq("user_id", user_id).execute()
    applied_ids = {a["job_id"] for a in (apps_result.data or [])}

    jobs_result = db.supabase.table("jobs").select("*").eq(
        "is_expired", False
    ).eq("user_id", user_id).order("created_at", desc=True).limit(max_jobs * 2).execute()

    unprocessed = [j for j in (jobs_result.data or []) if j["id"] not in applied_ids][:max_jobs]

    if not unprocessed:
        return {"message": "No new jobs to analyze.", "applications_created": 0}

    applications_created = 0

    for job in unprocessed:
        try:
            job_text = f"Title: {job['title']}\nCompany: {job['company']}\nLocation: {job.get('location', '')}\n"
            if job.get('salary'): job_text += f"Salary: {job['salary']}\n"
            job_text += f"\nDescription:\n{(job.get('description', ''))[:3000]}"

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a job matching expert. Analyze this job against the candidate's CV. Respond in JSON only: {\"summary\": \"...\", \"match_score\": 0-100, \"draft_email\": \"...\", \"recommendation\": \"Apply|Maybe|Skip\"}"},
                    {"role": "user", "content": f"JOB:\n{job_text}\n\nCV:\n{cv_content[:3000]}"}
                ],
                max_tokens=1000,
                temperature=0.3,
            )

            text = response.choices[0].message.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                analysis = json.loads(text[start:end])
            else:
                continue

            score = int(analysis.get("match_score", 0))
            if score >= min_score:
                db.supabase.table("applications").upsert({
                    "job_id": job["id"],
                    "user_id": user_id,
                    "match_score": score,
                    "summary": analysis.get("summary", ""),
                    "draft_email": analysis.get("draft_email", ""),
                    "status": "pending",
                    "created_at": datetime.utcnow().isoformat(),
                }, on_conflict="job_id").execute()
                applications_created += 1

        except Exception as e:
            logger.error(f"Error analyzing job {job.get('id')}: {e}")

    return {
        "jobs_analyzed": len(unprocessed),
        "applications_created": applications_created,
        "min_score": min_score,
    }
