from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import requests

UA = {
    "User-Agent": "AthulJobMatcher/1.0 (+personal job digest; contact athul290@gmail.com)"
}
TIMEOUT = 25


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # RemoteOK uses unix seconds
        try:
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    # ISO-ish
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        pass
    from dateutil import parser as date_parser

    try:
        dt = date_parser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def _norm_job(
    *,
    source: str,
    job_id: str,
    title: str,
    company: str,
    location: str,
    url: str,
    description: str,
    posted_at: Any,
) -> dict[str, Any]:
    posted = _parse_dt(posted_at)
    return {
        "source": source,
        "id": f"{source}:{job_id}",
        "title": (title or "").strip(),
        "company": (company or "").strip() or "Unknown",
        "location": (location or "").strip() or "Unknown",
        "url": (url or "").strip(),
        "description": re.sub(r"\s+", " ", (description or "").strip())[:4000],
        "posted_at": posted.isoformat() if posted else "",
        "posted_dt": posted,
    }


def _location_ok(
    job: dict[str, Any],
    locations: list[str],
    include_remote_uae: bool,
    allow_worldwide_stack: bool = True,
) -> bool:
    loc = (job.get("location") or "").lower()
    title = (job.get("title") or "").lower()
    blob = f"{loc} {title} {job.get('description','')}".lower()

    excluded = (
        "united states",
        "usa",
        "u.s.",
        "canada",
        "latam",
        "brazil",
        "germany",
        "israel",
        "united kingdom",
        "london",
        "new york",
        "san francisco",
        "california",
        "australia",
        "anz",
    )
    uae_markers = (
        "uae",
        "dubai",
        "abu dhabi",
        "abudhabi",
        "united arab emirates",
        "sharjah",
    )
    has_uae = any(m in blob for m in uae_markers) or any(
        loc_name.lower() in blob for loc_name in locations
    )
    if has_uae:
        return True

    # explicit non-UAE country in location → drop
    if any(x in loc for x in excluded):
        return False

    stack_title = any(
        k in title
        for k in ("react native", "react", "mobile", "full stack", "frontend", "javascript", "typescript")
    )

    if include_remote_uae:
        region = any(w in blob for w in ("mena", "middle east", "gcc", "romena", "gulf"))
        if region:
            return True
        if allow_worldwide_stack and stack_title and any(
            w in loc for w in ("worldwide", "anywhere", "remote", "utc", "emea", "europe", "asia", "africa")
        ):
            return True
        if allow_worldwide_stack and stack_title and loc in ("", "unknown", "remote"):
            return True
    return False


def _within_hours(job: dict[str, Any], max_age_hours: int) -> bool:
    posted = job.get("posted_dt")
    if not posted:
        # keep undated jobs but mark them; runner can filter softer
        job["age_unknown"] = True
        return True
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
        job["posted_dt"] = posted
    age_h = (_now() - posted.astimezone(timezone.utc)).total_seconds() / 3600.0
    job["age_hours"] = round(age_h, 1)
    return age_h <= max_age_hours


def fetch_remotive(queries: list[str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    urls = [
        "https://remotive.com/api/remote-jobs?category=software-dev&limit=100",
        *[f"https://remotive.com/api/remote-jobs?search={quote_plus(q)}&limit=50" for q in queries[:6]],
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            continue
        for item in data.get("jobs", []):
            jid = str(item.get("id") or item.get("url"))
            if jid in seen:
                continue
            seen.add(jid)
            jobs.append(
                _norm_job(
                    source="remotive",
                    job_id=jid,
                    title=item.get("title") or "",
                    company=item.get("company_name") or "",
                    location=item.get("candidate_required_location") or "Remote",
                    url=item.get("url") or "",
                    description=item.get("description") or "",
                    posted_at=item.get("publication_date"),
                )
            )
    return jobs


def fetch_jobicy(queries: list[str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Jobicy: tag-based; pull mobile / javascript / react tags
    tags = ["react", "javascript", "nodejs", "mobile", "software"]
    for tag in tags:
        url = f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={quote_plus(tag)}"
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            continue
        for item in data.get("jobs", []):
            jid = str(item.get("id") or item.get("url"))
            if jid in seen:
                continue
            # light query relevance
            blob = f"{item.get('jobTitle','')} {item.get('jobDescription','')}".lower()
            if queries and not any(q.lower().split()[0] in blob for q in queries[:6]):
                # still keep react/mobile-ish
                if not any(k in blob for k in ("react", "mobile", "node", "full stack", "javascript")):
                    continue
            seen.add(jid)
            jobs.append(
                _norm_job(
                    source="jobicy",
                    job_id=jid,
                    title=item.get("jobTitle") or "",
                    company=item.get("companyName") or "",
                    location=item.get("jobGeo") or "Remote",
                    url=item.get("url") or "",
                    description=item.get("jobDescription") or "",
                    posted_at=item.get("pubDate"),
                )
            )
    return jobs


def fetch_remoteok() -> list[dict[str, Any]]:
    url = "https://remoteok.com/api"
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        return []
    jobs: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
            continue
        tags = " ".join(item.get("tags") or [])
        blob = f"{item.get('position','')} {tags} {item.get('description','')}".lower()
        if not any(k in blob for k in ("react", "mobile", "react-native", "node", "javascript", "typescript", "full stack", "frontend")):
            continue
        jobs.append(
            _norm_job(
                source="remoteok",
                job_id=str(item["id"]),
                title=item.get("position") or "",
                company=item.get("company") or "",
                location=item.get("location") or "Remote",
                url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}",
                description=item.get("description") or tags,
                posted_at=item.get("date") or item.get("epoch"),
            )
        )
    return jobs


def fetch_arbeitnow(queries: list[str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for q in queries[:5]:
        url = f"https://www.arbeitnow.com/api/job-board-api?search={quote_plus(q)}"
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            continue
        for item in data.get("data", []):
            jid = str(item.get("slug") or item.get("url"))
            if jid in seen:
                continue
            seen.add(jid)
            jobs.append(
                _norm_job(
                    source="arbeitnow",
                    job_id=jid,
                    title=item.get("title") or "",
                    company=item.get("company_name") or "",
                    location=item.get("location") or "",
                    url=item.get("url") or "",
                    description=item.get("description") or "",
                    posted_at=item.get("created_at"),
                )
            )
    return jobs


def fetch_jsearch(queries: list[str], locations: list[str]) -> list[dict[str, Any]]:
    """Optional RapidAPI JSearch — best for Dubai/Abu Dhabi local postings.
    Set RAPIDAPI_KEY in env.
    """
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not key:
        return []
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    headers = {
        **UA,
        "x-rapidapi-key": key,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    }
    place_queries = []
    for role in queries[:6]:
        for city in ("Dubai", "Abu Dhabi", "UAE"):
            place_queries.append(f"{role} in {city}")
    # date_posted: today when possible; also yesterday for fuller UAE digests
    for date_posted in ("today", "yesterday"):
        for q in place_queries[:10]:
            try:
                r = requests.get(
                    "https://jsearch.p.rapidapi.com/search",
                    headers=headers,
                    params={
                        "query": q,
                        "page": "1",
                        "num_pages": "1",
                        "date_posted": date_posted,
                        "country": "ae",
                    },
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                data = r.json()
            except requests.RequestException:
                continue
            for item in data.get("data", []) or []:
                jid = str(item.get("job_id") or item.get("job_apply_link"))
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                loc_parts = [
                    item.get("job_city") or "",
                    item.get("job_state") or "",
                    item.get("job_country") or "",
                ]
                jobs.append(
                    _norm_job(
                        source="jsearch",
                        job_id=jid,
                        title=item.get("job_title") or "",
                        company=item.get("employer_name") or "",
                        location=", ".join(p for p in loc_parts if p) or "UAE",
                        url=item.get("job_apply_link") or item.get("job_google_link") or "",
                        description=item.get("job_description") or "",
                        posted_at=item.get("job_posted_at_datetime_utc")
                        or item.get("job_posted_at_timestamp"),
                    )
                )
    return jobs


def fetch_jooble(queries: list[str]) -> list[dict[str, Any]]:
    """UAE Jooble REST API — register at https://ae.jooble.org/api/about
    Set JOOBLE_API_KEY (UAE-domain key only).
    """
    key = os.environ.get("JOOBLE_API_KEY", "").strip()
    if not key:
        return []
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    endpoint = f"https://ae.jooble.org/api/{key}"
    searches = []
    for role in queries[:8]:
        for city in ("Dubai", "Abu Dhabi", "UAE"):
            searches.append((role, city))
    for keywords, location in searches[:15]:
        try:
            r = requests.post(
                endpoint,
                headers={**UA, "Content-Type": "application/json"},
                json={
                    "keywords": keywords,
                    "location": location,
                    "page": "1",
                    "ResultOnPage": "20",
                    "companysearch": "false",
                },
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            data = r.json()
        except requests.RequestException:
            continue
        for item in data.get("jobs", []) or []:
            jid = str(item.get("id") or item.get("link"))
            if not jid or jid in seen:
                continue
            seen.add(jid)
            jobs.append(
                _norm_job(
                    source="jooble",
                    job_id=jid,
                    title=item.get("title") or "",
                    company=item.get("company") or "",
                    location=item.get("location") or location,
                    url=item.get("link") or "",
                    description=item.get("snippet") or "",
                    posted_at=item.get("updated"),
                )
            )
    return jobs


def uae_apis_configured() -> dict[str, bool]:
    return {
        "jsearch": bool(os.environ.get("RAPIDAPI_KEY", "").strip()),
        "jooble": bool(os.environ.get("JOOBLE_API_KEY", "").strip()),
    }


def collect_jobs(cfg: dict[str, Any], search_queries: list[str]) -> list[dict[str, Any]]:
    locations = cfg.get("locations") or []
    max_age = int(cfg.get("max_age_hours") or 24)
    include_remote = bool(cfg.get("include_remote_uae", True))
    apis = uae_apis_configured()
    has_uae_api = apis["jsearch"] or apis["jooble"]
    if not has_uae_api:
        max_age = max(max_age, int(cfg.get("fallback_max_age_hours") or 72))

    raw: list[dict[str, Any]] = []
    # Primary: UAE-capable APIs
    raw.extend(fetch_jsearch(search_queries, locations))
    raw.extend(fetch_jooble(search_queries))

    # Global remote boards only if explicitly enabled (off by default — stops Somnio fillers)
    if cfg.get("use_global_remote_boards"):
        raw.extend(fetch_remotive(search_queries))
        raw.extend(fetch_jobicy(search_queries))
        raw.extend(fetch_remoteok())
        raw.extend(fetch_arbeitnow(search_queries))

    # de-dupe by URL/title+company
    seen: set[str] = set()
    filtered: list[dict[str, Any]] = []
    for job in raw:
        if not job.get("title") or not job.get("url"):
            continue
        key = (job["url"] or "").split("?")[0].lower()
        alt = f"{job['title'].lower()}|{job['company'].lower()}"
        if key in seen or alt in seen:
            continue
        allow_ww = bool(cfg.get("allow_worldwide_remote_stack", False))
        if not _location_ok(job, locations, include_remote, allow_ww):
            continue
        # Extra gate for remote boards: title must be stack-relevant
        if job["source"] in ("remotive", "jobicy", "remoteok", "arbeitnow"):
            title = job["title"].lower()
            if not any(
                k in title
                for k in (
                    "react native",
                    "react",
                    "mobile",
                    "full stack",
                    "fullstack",
                    "frontend",
                    "front-end",
                    "javascript",
                    "typescript",
                    "node",
                )
            ):
                continue
        if not _within_hours(job, max_age):
            continue
        seen.add(key)
        seen.add(alt)
        filtered.append(job)
    return filtered
