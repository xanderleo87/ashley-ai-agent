"""
Job source scrapers - 7 sources.
RemoteOK, Arbeitnow, LinkedIn, Greenhouse, Lever, Adzuna, OnlineJobs.ph.
"""

import aiohttp
import asyncio
import re
import logging
import feedparser
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
from bs4 import BeautifulSoup

from .models import Job
from .headers import get_api_headers, get_random_browser_headers, add_random_delay
from .rate_limiter import rate_limiters
from .jsonld import extract_job_posting

logger = logging.getLogger(__name__)


# ═══════════════════════════ RemoteOK ═══════════════════════════

class RemoteOKSource:
    name = "remoteok"
    JSON_URL = "https://remoteok.com/api"

    def __init__(self):
        self._limiter = rate_limiters.get_limiter(self.name, 2.0, burst=2)

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        try:
            all_jobs = await self._fetch_jobs()
            filtered = self._filter(all_jobs, keywords)
            return filtered[:limit]
        except Exception as e:
            logger.error(f"RemoteOK error: {e}")
            return []

    async def _fetch_jobs(self) -> list[Job]:
        async with self._limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.JSON_URL, headers=get_api_headers()) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return self._parse(data[1:] if len(data) > 1 else [])

    def _parse(self, items: list[dict]) -> list[Job]:
        jobs = []
        for item in items:
            try:
                eid = str(item.get("id", ""))
                if not eid:
                    continue
                salary = None
                if item.get("salary_min") or item.get("salary_max"):
                    mn, mx = item.get("salary_min", ""), item.get("salary_max", "")
                    if mn and mx: salary = f"${mn} - ${mx}"
                    elif mn: salary = f"From ${mn}"
                    elif mx: salary = f"Up to ${mx}"

                posted_date = None
                if item.get("date"):
                    try:
                        if isinstance(item["date"], (int, float)):
                            posted_date = datetime.fromtimestamp(item["date"])
                        else:
                            posted_date = datetime.fromisoformat(str(item["date"]))
                    except (ValueError, TypeError):
                        pass

                location = "Remote"
                if item.get("location"):
                    location = f"Remote - {item['location']}"

                desc_parts = []
                if item.get("description"): desc_parts.append(item["description"])
                if item.get("tags"): desc_parts.append(f"Tags: {', '.join(item['tags'])}")

                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=item.get("company", "Unknown"),
                    title=item.get("position", "Unknown Position"),
                    location=location, salary=salary,
                    description="\n\n".join(desc_parts),
                    application_link=item.get("url", f"https://remoteok.com/l/{eid}"),
                    posted_date=posted_date,
                ))
            except Exception:
                continue
        return jobs

    def _filter(self, jobs, keywords):
        if not keywords: return jobs
        kw_lower = [k.lower() for k in keywords]
        return [j for j in jobs if any(k in f"{j.title} {j.description} {j.company}".lower() for k in kw_lower)]


# ═══════════════════════════ Arbeitnow ═══════════════════════════

class ArbeitnowSource:
    name = "arbeitnow"
    BASE_URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self):
        self._limiter = rate_limiters.get_limiter(self.name, 1.0, burst=3)

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        try:
            all_jobs = await self._fetch(1)
            filtered = self._filter(all_jobs, keywords)
            if location:
                filtered = [j for j in filtered if location.lower() in j.location.lower()]
            return filtered[:limit]
        except Exception as e:
            logger.error(f"Arbeitnow error: {e}")
            return []

    async def _fetch(self, page=1) -> list[Job]:
        url = f"{self.BASE_URL}?page={page}"
        async with self._limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=get_api_headers()) as resp:
                    if resp.status != 200: return []
                    data = await resp.json()
                    jobs = self._parse(data.get("data", []))
                    if page < 3 and data.get("links", {}).get("next"):
                        jobs.extend(await self._fetch(page + 1))
                    return jobs

    def _parse(self, items):
        jobs = []
        for item in items:
            try:
                eid = str(item.get("slug", ""))
                if not eid: continue
                posted_date = None
                if item.get("created_at"):
                    try: posted_date = datetime.fromtimestamp(item["created_at"])
                    except: pass
                location = item.get("location", "")
                if item.get("remote"): location = f"Remote - {location}" if location else "Remote"
                tags = item.get("tags", [])
                desc = item.get("description", "")
                if tags: desc = f"Tags: {', '.join(tags)}\n\n{desc}"
                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=item.get("company_name", "Unknown"),
                    title=item.get("title", "Unknown"), location=location, salary=None,
                    description=desc, application_link=item.get("url", ""),
                    posted_date=posted_date,
                ))
            except: continue
        return jobs

    def _filter(self, jobs, keywords):
        if not keywords: return jobs
        kw_lower = [k.lower() for k in keywords]
        return [j for j in jobs if any(k in f"{j.title} {j.description} {j.company}".lower() for k in kw_lower)]


# ═══════════════════════════ LinkedIn ═══════════════════════════

class LinkedInSource:
    name = "linkedin"
    BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def __init__(self):
        self._limiter = rate_limiters.get_limiter(self.name, 3.0, burst=2)

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        jobs = []
        query = " ".join(keywords)
        try:
            pages = min((limit + 24) // 25, 4)
            for page in range(pages):
                page_jobs = await self._fetch(query, location, page * 25)
                if not page_jobs: break
                jobs.extend(page_jobs)
                if len(jobs) >= limit: break
            return jobs[:limit]
        except Exception as e:
            logger.error(f"LinkedIn error: {e}")
            return jobs

    async def _fetch(self, query, location, start=0):
        params = {"keywords": query, "start": start, "f_TPR": "r604800", "position": 1, "pageNum": 0}
        if location: params["location"] = location
        url = f"{self.BASE_URL}?{urlencode(params)}"
        headers = get_random_browser_headers(referer="https://www.linkedin.com/jobs/search/")

        async with self._limiter:
            await asyncio.sleep(add_random_delay())
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200: return []
                    html = await resp.text()
                    jsonld_jobs = self._try_jsonld(html)
                    if jsonld_jobs: return jsonld_jobs
                    return self._parse_html(html)

    def _try_jsonld(self, html):
        try:
            posting = extract_job_posting(html)
            if posting and posting.get("title"):
                eid = posting.get("application_link", "").split("-")[-1] or "jsonld"
                salary = None
                if posting.get("salary_min") or posting.get("salary_max"):
                    parts = []
                    if posting["salary_min"]: parts.append(str(posting["salary_min"]))
                    if posting["salary_max"]: parts.append(str(posting["salary_max"]))
                    salary = " - ".join(parts)
                return [Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=posting.get("company", "Unknown"), title=posting["title"],
                    location=posting.get("location", ""), salary=salary,
                    description=posting.get("description", ""),
                    application_link=posting.get("application_link", ""),
                    posted_date=posting.get("posted_date"),
                )]
        except: pass
        return []

    def _parse_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_="base-card") or soup.find_all("li")
        jobs = []
        for card in cards:
            try:
                title_el = card.find("h3", class_="base-search-card__title") or card.find("h3")
                if not title_el: continue
                title = title_el.get_text(strip=True)
                if not title: continue

                company_el = card.find("h4", class_="base-search-card__subtitle") or card.find("a", class_="hidden-nested-link")
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                location_el = card.find("span", class_="job-search-card__location")
                location = location_el.get_text(strip=True) if location_el else ""

                link_el = card.find("a", class_="base-card__full-link") or card.find("a", href=True)
                app_link, eid = "", ""
                if link_el and link_el.get("href"):
                    app_link = link_el["href"].split("?")[0]
                    id_match = re.search(r'/view/[^/]*-(\d+)', app_link) or re.search(r'(\d{8,})', app_link)
                    eid = id_match.group(1) if id_match else ""
                if not eid:
                    eid = card.get("data-entity-urn", "").split(":")[-1]
                if not eid: continue

                posted_date = None
                time_el = card.find("time")
                if time_el and time_el.get("datetime"):
                    try: posted_date = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
                    except: pass

                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=company, title=title, location=location, salary=None,
                    description="", application_link=app_link, posted_date=posted_date,
                ))
            except: continue
        return jobs


# ═══════════════════════════ Greenhouse ═══════════════════════════

DEFAULT_GREENHOUSE_COMPANIES = [
    "airbnb", "cloudflare", "datadog", "discord", "figma", "hashicorp",
    "hubspot", "notion", "openai", "plaid", "reddit", "scale", "snyk",
    "sourcegraph", "stripe", "twilio", "vercel", "watershed",
]


class GreenhouseSource:
    name = "greenhouse"
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, companies=None):
        self._limiter = rate_limiters.get_limiter(self.name, 1.0, burst=3)
        self.companies = companies or DEFAULT_GREENHOUSE_COMPANIES

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        all_jobs = []
        tasks = [self._fetch_company(c) for c in self.companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception): continue
            all_jobs.extend(result)

        filtered = self._filter(all_jobs, keywords)
        if location:
            filtered = [j for j in filtered if location.lower() in j.location.lower()]
        logger.info(f"Greenhouse: Found {len(filtered[:limit])} matching jobs")
        return filtered[:limit]

    async def _fetch_company(self, company):
        url = f"{self.API_BASE}/{company}/jobs"
        async with self._limiter:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params={"content": "true"},
                                           headers=get_api_headers(),
                                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200: return []
                        data = await resp.json()
                        return self._parse(data.get("jobs", []), company)
            except: return []

    def _parse(self, items, board_company):
        jobs = []
        for item in items:
            try:
                eid = str(item.get("id", ""))
                if not eid: continue
                loc_data = item.get("location", {})
                location = loc_data.get("name", "") if isinstance(loc_data, dict) else str(loc_data)
                desc = ""
                content = item.get("content", "")
                if content:
                    desc = BeautifulSoup(content, "html.parser").get_text(separator="\n", strip=True)
                posted_date = None
                updated_at = item.get("updated_at", "") or item.get("created_at", "")
                if updated_at:
                    try: posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    except: pass
                company_name = board_company.replace("-", " ").title()
                depts = item.get("departments", [])
                dept_names = [d.get("name", "") for d in depts if d.get("name")]
                if dept_names: desc = f"Department: {', '.join(dept_names)}\n\n{desc}"

                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=company_name, title=item.get("title", "Unknown"),
                    location=location, salary=None, description=desc,
                    application_link=item.get("absolute_url", f"https://boards.greenhouse.io/{board_company}/jobs/{eid}"),
                    posted_date=posted_date,
                ))
            except: continue
        return jobs

    def _filter(self, jobs, keywords):
        if not keywords: return jobs
        kw_lower = [k.lower() for k in keywords]
        return [j for j in jobs if any(k in f"{j.title} {j.description} {j.company}".lower() for k in kw_lower)]


# ═══════════════════════════ Lever ═══════════════════════════

DEFAULT_LEVER_COMPANIES = [
    "Netflix", "anthropic", "anduril", "cohere", "databricks", "deel",
    "faire", "flexport", "netlify", "replit", "retool", "rippling",
    "samsara", "temporal", "weights-and-biases",
]


class LeverSource:
    name = "lever"
    API_BASE = "https://api.lever.co/v0/postings"

    def __init__(self, companies=None):
        self._limiter = rate_limiters.get_limiter(self.name, 1.0, burst=3)
        self.companies = companies or DEFAULT_LEVER_COMPANIES

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        all_jobs = []
        tasks = [self._fetch_company(c) for c in self.companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception): continue
            all_jobs.extend(result)

        filtered = self._filter(all_jobs, keywords)
        if location:
            filtered = [j for j in filtered if location.lower() in j.location.lower()]
        logger.info(f"Lever: Found {len(filtered[:limit])} matching jobs")
        return filtered[:limit]

    async def _fetch_company(self, company):
        url = f"{self.API_BASE}/{company}"
        async with self._limiter:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params={"mode": "json"},
                                           headers=get_api_headers(),
                                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200: return []
                        data = await resp.json()
                        if not isinstance(data, list): return []
                        return self._parse(data, company)
            except: return []

    def _parse(self, items, board_company):
        jobs = []
        for item in items:
            try:
                eid = str(item.get("id", ""))
                if not eid: continue
                categories = item.get("categories", {})
                location = categories.get("location", "") or ""
                commitment = categories.get("commitment", "")
                team = categories.get("team", "")

                desc_parts = []
                if team: desc_parts.append(f"Team: {team}")
                if commitment: desc_parts.append(f"Commitment: {commitment}")
                if item.get("descriptionPlain"): desc_parts.insert(0, item["descriptionPlain"])
                for section in item.get("lists", []):
                    if section.get("text"): desc_parts.append(f"\n{section['text']}")
                    if section.get("content"):
                        desc_parts.append(BeautifulSoup(section["content"], "html.parser").get_text(separator="\n", strip=True))

                posted_date = None
                if item.get("createdAt"):
                    try: posted_date = datetime.fromtimestamp(item["createdAt"] / 1000)
                    except: pass

                company_name = board_company.replace("-", " ").title()
                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=company_name, title=item.get("text", "Unknown"),
                    location=location, salary=None, description="\n\n".join(desc_parts),
                    application_link=item.get("hostedUrl", "") or item.get("applyUrl", ""),
                    posted_date=posted_date,
                ))
            except: continue
        return jobs

    def _filter(self, jobs, keywords):
        if not keywords: return jobs
        kw_lower = [k.lower() for k in keywords]
        return [j for j in jobs if any(k in f"{j.title} {j.description} {j.company}".lower() for k in kw_lower)]


# ═══════════════════════════ Adzuna ═══════════════════════════

class AdzunaSource:
    name = "adzuna"
    COUNTRY_CODES = {
        "US": "us", "UK": "gb", "GB": "gb", "DE": "de", "NL": "nl",
        "AT": "at", "CH": "ch", "AU": "au", "CA": "ca", "FR": "fr",
        "IN": "in", "IT": "it", "PL": "pl", "SG": "sg",
    }
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id="", api_key=""):
        self._limiter = rate_limiters.get_limiter(self.name, 1.0, burst=5)
        self.app_id = app_id
        self.api_key = api_key

    def is_configured(self):
        return bool(self.app_id and self.api_key)

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        if not self.is_configured():
            return []
        country = self.COUNTRY_CODES.get(location.upper(), "us") if location else "us"
        try:
            return await self._fetch(country, " ".join(keywords), limit)
        except Exception as e:
            logger.error(f"Adzuna error: {e}")
            return []

    async def search_all_countries(self, keywords, countries, limit_per_country=20):
        all_jobs = []
        for country in countries:
            jobs = await self.search(keywords, country, limit_per_country)
            all_jobs.extend(jobs)
        return all_jobs

    async def _fetch(self, country, query, limit):
        params = {
            "app_id": self.app_id, "app_key": self.api_key,
            "results_per_page": min(limit, 50), "what": query,
            "content-type": "application/json",
        }
        url = f"{self.BASE_URL}/{country}/search/1?{urlencode(params)}"
        async with self._limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200: return []
                    data = await resp.json()
                    return self._parse(data.get("results", []))

    def _parse(self, results):
        jobs = []
        for item in results:
            try:
                eid = str(item.get("id", ""))
                salary = None
                if item.get("salary_min") or item.get("salary_max"):
                    mn, mx = item.get("salary_min", ""), item.get("salary_max", "")
                    if mn and mx: salary = f"{mn} - {mx}"
                    elif mn: salary = f"From {mn}"
                    elif mx: salary = f"Up to {mx}"
                loc_data = item.get("location", {})
                location = ", ".join(loc_data.get("display_name", "").split(", ")[:2])
                posted_date = None
                if item.get("created"):
                    try: posted_date = datetime.fromisoformat(item["created"].replace("Z", "+00:00"))
                    except: pass
                jobs.append(Job(
                    id=Job.generate_id(self.name, eid), source=self.name, external_id=eid,
                    company=item.get("company", {}).get("display_name", "Unknown"),
                    title=item.get("title", "Unknown"), location=location,
                    salary=salary, description=item.get("description", ""),
                    application_link=item.get("redirect_url", ""),
                    posted_date=posted_date,
                ))
            except: continue
        return jobs


# ═══════════════════════════ OnlineJobs.ph ═══════════════════════════

class OnlineJobsPhSource:
    name = "onlinejobsph"
    BASE_URL = "https://www.onlinejobs.ph/jobseekers/jobsearch"

    def __init__(self):
        self._limiter = rate_limiters.get_limiter(self.name, 3.0, burst=2)

    async def search(self, keywords: list[str], location=None, limit=50) -> list[Job]:
        all_jobs = []
        for kw in keywords:
            if len(all_jobs) >= limit:
                break
            try:
                jobs = await self._fetch(kw, limit - len(all_jobs))
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error(f"OnlineJobs.ph error for '{kw}': {e}")
        return all_jobs[:limit]

    async def _fetch(self, keyword, limit):
        jobs = []
        pages = min(3, (limit // 30) + 1)  # 30 jobs per page, max 3 pages

        for page in range(1, pages + 1):
            if len(jobs) >= limit:
                break
            await add_random_delay()
            async with self._limiter:
                try:
                    params = {"jobkeyword": keyword, "page": page}
                    url = f"{self.BASE_URL}?{urlencode(params)}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url,
                            headers=get_random_browser_headers(),
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as resp:
                            if resp.status != 200:
                                logger.warning(f"OnlineJobs.ph returned {resp.status}")
                                break
                            html = await resp.text()
                            page_jobs = self._parse(html)
                            if not page_jobs:
                                break
                            jobs.extend(page_jobs)
                except Exception as e:
                    logger.error(f"OnlineJobs.ph page {page} error: {e}")
                    break

        return jobs[:limit]

    def _parse(self, html):
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Each job is wrapped in an <a> tag linking to /jobseekers/job/...
        job_links = soup.find_all("a", href=re.compile(r"/jobseekers/job/"))
        for link in job_links:
            try:
                href = link.get("href", "")
                if not href or "jobsearch" in href:
                    continue

                # Extract job ID from URL (last number in the slug)
                id_match = re.search(r"-(\d+)$", href)
                if not id_match:
                    id_match = re.search(r"/(\d+)$", href)
                if not id_match:
                    continue
                eid = id_match.group(1)

                # Title from h4 tag
                h4 = link.find("h4")
                if not h4:
                    continue
                title = h4.get_text(strip=True)
                # Remove badge text like "Full Time", "Part Time", "Any"
                badge = h4.find("span", class_="badge")
                job_type = badge.get_text(strip=True) if badge else ""
                if badge:
                    title = title.replace(badge.get_text(), "").strip()

                # Description
                desc_div = link.find("div", class_="desc")
                description = desc_div.get_text(strip=True) if desc_div else ""

                # Salary - in the <dd> tag inside the salary row
                salary = None
                dd_tags = link.find_all("dd")
                for dd in dd_tags:
                    text = dd.get_text(strip=True)
                    if text and text != "" and "Posted" not in text:
                        salary = text if text.lower() != "negotiable" else "Negotiable"
                        break

                # Tags/categories
                tag_div = link.find("div", class_="job-tag")
                tags = []
                if tag_div:
                    tags = [t.get_text(strip=True) for t in tag_div.find_all("a") if t.get_text(strip=True)]

                # Posted date
                posted_date = None
                em_tag = link.find("em")
                if em_tag:
                    date_text = em_tag.get_text(strip=True).replace("Posted on ", "")
                    try:
                        posted_date = datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")
                    except:
                        pass

                full_url = f"https://www.onlinejobs.ph{href}" if href.startswith("/") else href
                full_desc = description
                if tags:
                    full_desc += f"\n\nTags: {', '.join(tags)}"
                if job_type:
                    full_desc += f"\nType: {job_type}"

                jobs.append(Job(
                    id=Job.generate_id(self.name, eid),
                    source=self.name,
                    external_id=eid,
                    company="OnlineJobs.ph Employer",
                    title=title,
                    location="Philippines (Remote)",
                    salary=salary,
                    description=full_desc,
                    application_link=full_url,
                    posted_date=posted_date,
                ))
            except Exception as e:
                logger.error(f"OnlineJobs.ph parse error: {e}")
                continue

        return jobs
