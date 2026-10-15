"""Fuzzy deduplication for job listings."""

import hashlib
import re
from difflib import SequenceMatcher


def normalize_company(name: str) -> str:
    name = name.lower().strip()
    suffixes = [
        r'\s*(,?\s*inc\.?|,?\s*llc\.?|,?\s*ltd\.?|,?\s*gmbh|,?\s*ag|,?\s*corp\.?|,?\s*co\.?)',
        r'\s*(,?\s*limited|,?\s*incorporated|,?\s*corporation)',
        r'\s*\.com\b',
        r'\s*\(.*?\)\s*$',
    ]
    for pattern in suffixes:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    replacements = {
        r'\bsr\.?\b': 'senior', r'\bjr\.?\b': 'junior',
        r'\bswe\b': 'software engineer', r'\bsde\b': 'software development engineer',
        r'\bml\b': 'machine learning', r'\bai\b': 'artificial intelligence',
        r'\bfe\b': 'frontend', r'\bbe\b': 'backend',
        r'\bdev\b': 'developer', r'\beng\.?\b': 'engineer',
    }
    for pattern, replacement in replacements.items():
        title = re.sub(pattern, replacement, title)
    title = re.sub(r'\b[IVX]+\b|\bL\d\b|\blevel\s*\d\b', '', title)
    title = re.sub(r'[^a-z0-9\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def content_hash(company: str, title: str, description: str = "") -> str:
    content = f"{normalize_company(company)}|{normalize_title(title)}"
    if description:
        norm = re.sub(r'[^a-z0-9\s]', '', description[:500].lower().strip())
        content += f"|{norm}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def is_duplicate(company_a, title_a, company_b, title_b):
    nc_a, nc_b = normalize_company(company_a), normalize_company(company_b)
    nt_a, nt_b = normalize_title(title_a), normalize_title(title_b)
    if nc_a == nc_b and nt_a == nt_b:
        return True
    return (SequenceMatcher(None, nc_a, nc_b).ratio() >= 0.75 and
            SequenceMatcher(None, nt_a, nt_b).ratio() >= 0.80)


def deduplicate_jobs(jobs: list) -> list:
    if not jobs:
        return []

    seen_exact = {}
    unique_indices = []
    for i, job in enumerate(jobs):
        key = f"{normalize_company(job.company)}|{normalize_title(job.title)}"
        if key not in seen_exact:
            seen_exact[key] = i
            unique_indices.append(i)

    buckets = {}
    for idx in unique_indices:
        bucket_key = normalize_company(jobs[idx].company).split()[0] if normalize_company(jobs[idx].company) else "_"
        buckets.setdefault(bucket_key, []).append(idx)

    final_indices = set()
    removed = set()
    for bucket_key, indices in buckets.items():
        for i, idx_a in enumerate(indices):
            if idx_a in removed:
                continue
            final_indices.add(idx_a)
            for idx_b in indices[i + 1:]:
                if idx_b in removed:
                    continue
                if is_duplicate(jobs[idx_a].company, jobs[idx_a].title,
                                jobs[idx_b].company, jobs[idx_b].title):
                    removed.add(idx_b)

    return [jobs[i] for i in sorted(final_indices)]
