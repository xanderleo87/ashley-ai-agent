"""JSON-LD structured data extraction for job postings."""

import json
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup


def extract_jsonld(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def extract_job_posting(html: str) -> Optional[dict]:
    blocks = extract_jsonld(html)
    for block in blocks:
        if block.get("@graph"):
            for item in block["@graph"]:
                if item.get("@type") == "JobPosting":
                    return _parse_job_posting(item)
        if block.get("@type") == "JobPosting":
            return _parse_job_posting(block)
    return None


def _parse_job_posting(data: dict) -> dict:
    result = {
        "title": data.get("title", ""),
        "description": "", "company": "", "location": "",
        "salary_min": None, "salary_max": None,
        "posted_date": None, "application_link": "",
    }

    org = data.get("hiringOrganization", {})
    if isinstance(org, dict):
        result["company"] = org.get("name", "")
    elif isinstance(org, str):
        result["company"] = org

    desc = data.get("description", "")
    if desc and "<" in desc:
        result["description"] = BeautifulSoup(desc, "html.parser").get_text(separator="\n", strip=True)
    else:
        result["description"] = desc

    location = data.get("jobLocation", {})
    if isinstance(location, dict):
        address = location.get("address", {})
        if isinstance(address, dict):
            parts = [address.get("addressLocality", ""), address.get("addressRegion", ""), address.get("addressCountry", "")]
            result["location"] = ", ".join(p for p in parts if p)

    loc_type = data.get("jobLocationType", "")
    if loc_type == "TELECOMMUTE":
        result["location"] = f"Remote - {result['location']}" if result["location"] else "Remote"

    salary = data.get("baseSalary", {})
    if isinstance(salary, dict):
        value = salary.get("value", {})
        if isinstance(value, dict):
            result["salary_min"] = value.get("minValue")
            result["salary_max"] = value.get("maxValue")

    date_str = data.get("datePosted", "")
    if date_str:
        try:
            result["posted_date"] = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    result["application_link"] = data.get("url", "")
    return result
