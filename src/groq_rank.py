from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Fast, cheap model on Groq
# Account-available defaults (llama-3.1 may not be enabled on every Groq key)
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")


def groq_enabled() -> bool:
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


def _profile_blurb(cfg: dict[str, Any]) -> str:
    c = cfg.get("candidate") or {}
    return (
        f"Candidate: {c.get('name')} based in {c.get('base_location')}. "
        "Target: React Native, React.js, TypeScript, Node.js, full-stack mobile/web, "
        "banking/fintech mobile preferred. Experience: 5–6+ years. "
        "Locations: Dubai, Abu Dhabi, UAE (or remote hiring UAE/MENA)."
    )


def refine_with_groq(
    jobs: list[dict[str, Any]],
    cfg: dict[str, Any],
    roles: list[str],
    *,
    min_score: float,
) -> list[dict[str, Any]]:
    """Ask Groq to re-score jobs vs Athul's profile. Skips if no key or no jobs."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key or not jobs:
        return jobs

    # Cap batch size for free-tier rate limits
    batch = jobs[:40]
    compact = []
    for i, j in enumerate(batch):
        compact.append(
            {
                "i": i,
                "title": j.get("title"),
                "company": j.get("company"),
                "location": j.get("location"),
                "snippet": (j.get("description") or "")[:600],
                "keyword_score": j.get("match_score"),
            }
        )

    system = (
        "You are a strict UAE tech recruiter assistant. "
        "Return ONLY valid JSON (no markdown). "
        "Decide if each job fits a React Native / React / Full-Stack JS mobile engineer."
    )
    user = {
        "profile": _profile_blurb(cfg),
        "target_roles_sample": roles[:12],
        "jobs": compact,
        "instructions": (
            "For each job return: i, score (0-100 fit), resume ('5+' or '6+'), "
            "keep (true/false), why (one short sentence). "
            "Reject pure sales, marketing, accounting, HR, ops without engineering. "
            "Prefer mobile/RN/React/Node/fullstack. "
            "Use 6+ resume for senior/lead/banking/enterprise."
        ),
    }

    try:
        r = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEFAULT_MODEL,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(user),
                    },
                ],
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"  Groq rank skipped: HTTP {r.status_code} {r.text[:200]}")
            return jobs
        payload = r.json()
        content = payload["choices"][0]["message"]["content"]
        # strip optional markdown fences
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"  Groq rank skipped: {exc}")
        return jobs

    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("results") or parsed.get("jobs") or parsed.get("items")
        if items is None:
            # model sometimes returns {"0": {...}, "1": {...}}
            vals = list(parsed.values())
            items = vals if vals and all(isinstance(v, dict) for v in vals) else []
    else:
        items = []
    if not isinstance(items, list):
        print("  Groq rank skipped: unexpected JSON shape")
        return jobs

    by_i: dict[int, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        by_i[idx] = item

    refined: list[dict[str, Any]] = []
    for i, job in enumerate(batch):
        g = by_i.get(i)
        if not g:
            refined.append(job)
            continue
        keep = g.get("keep", True)
        if keep is False or str(keep).lower() == "false":
            continue
        try:
            score = float(g.get("score", job.get("match_score") or 0))
        except (TypeError, ValueError):
            score = float(job.get("match_score") or 0)
        if score < min_score:
            continue
        resume = str(g.get("resume") or job.get("resume_id") or "5+").strip()
        if resume not in ("5+", "6+"):
            resume = "6+" if "senior" in (job.get("title") or "").lower() else "5+"
        key_name = "six_plus" if resume == "6+" else "five_plus"
        resume_meta = (cfg.get("resumes") or {}).get(key_name) or {}
        out = dict(job)
        out["match_score"] = round(score, 1)
        out["resume_id"] = resume
        out["resume_label"] = resume_meta.get("label") or resume
        out["resume_path"] = resume_meta.get("path") or out.get("resume_path")
        why = str(g.get("why") or "").strip()
        if why:
            out["why_match"] = f"Groq: {why}"
        out["ranked_by"] = "groq"
        refined.append(out)

    # append any jobs beyond batch unchanged
    refined.extend(jobs[len(batch) :])
    refined.sort(key=lambda j: (-float(j.get("match_score") or 0), j.get("posted_at") or ""))
    return refined


def smoke_test() -> bool:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return False
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 8,
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Groq smoke failed: {r.status_code} {r.text[:300]}")
        return False
    text = r.json()["choices"][0]["message"]["content"]
    print(f"Groq smoke OK ({DEFAULT_MODEL}): {text!r}")
    return True
