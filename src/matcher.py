from __future__ import annotations

import re
from typing import Any


def _blob(job: dict[str, Any]) -> str:
    return f"{job.get('title','')} {job.get('description','')} {job.get('company','')}".lower()


STOP_TITLE = {
    "the",
    "and",
    "for",
    "with",
    "app",
    "apps",
    "application",
    "applications",
    "software",
    "engineer",
    "developer",
    "development",
    "senior",
    "junior",
    "mid",
}


def best_role_match(job: dict[str, Any], roles: list[str]) -> tuple[str, float]:
    title = (job.get("title") or "").lower()
    best_role = ""
    best = 0.0
    for role in roles:
        role_l = role.lower().replace("–", "-").replace("/", " ")
        # meaningful tokens only (drop generic engineer/developer words)
        role_tokens = [
            t
            for t in re.split(r"[^a-z0-9+.#]+", role_l)
            if len(t) > 2 and t not in STOP_TITLE
        ]
        if not role_tokens:
            continue
        hits = sum(1 for t in role_tokens if t in title)
        score = hits / len(role_tokens)
        core = role_l.split("-")[0].strip()
        if core and len(core) > 8 and core in title:
            score += 0.25
        if "react native" in role_l and "react native" in title:
            score += 0.55
        if "full stack" in role_l and ("full stack" in title or "fullstack" in title):
            score += 0.35
        if "mern" in role_l and "mern" in title:
            score += 0.4
        if "mobile" in role_l and "mobile" in title:
            score += 0.25
        if score > best:
            best = score
            best_role = role
    return best_role, min(best, 1.0)


def is_relevant_title(job: dict[str, Any]) -> bool:
    title = (job.get("title") or "").lower()
    # hard reject non-IC / wrong tracks
    reject = (
        "product manager",
        "account executive",
        "customer success",
        "sales",
        "recruiter",
        "devops only",
        "machine learning",
        "ml engineer",
        "data scientist",
        "partnerships manager",
        "engineering manager",
        "security software",
        "storage",
        "new grad",
    )
    if any(r in title for r in reject):
        return False
    accept = (
        "react native",
        "react.js",
        "reactjs",
        "react ",
        "mobile",
        "ios",
        "android",
        "full stack",
        "fullstack",
        "front end",
        "frontend",
        "node.js",
        "nodejs",
        "javascript",
        "typescript",
        "mern",
        "next.js",
    )
    return any(a in title for a in accept)


def skill_score(job: dict[str, Any], weights: dict[str, float]) -> tuple[float, list[str]]:
    text = _blob(job)
    earned = 0.0
    max_possible = sum(float(v) for v in weights.values()) or 1.0
    matched: list[str] = []
    for skill, weight in weights.items():
        if skill.lower() in text:
            earned += float(weight)
            matched.append(skill)
    return (earned / max_possible) * 100.0, matched


def pick_resume(job: dict[str, Any], cfg: dict[str, Any]) -> dict[str, str]:
    text = _blob(job)
    signals = [s.lower() for s in cfg.get("resume_six_plus_signals", [])]
    use_six = any(s in text for s in signals)
    # years asked in JD
    if re.search(r"\b([6-9]|1[0-5])\+?\s*\+?\s*years?\b", text):
        use_six = True
    if re.search(r"\b(3|4|5)\+?\s*years?\b", text) and not use_six:
        use_six = False
    key = "six_plus" if use_six else "five_plus"
    resume = cfg["resumes"][key]
    return {
        "resume_id": resume["id"],
        "resume_label": resume["label"],
        "resume_path": resume["path"],
    }


def score_job(job: dict[str, Any], cfg: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    if not is_relevant_title(job):
        out = {**job, "match_score": 0.0, "matched_role": "", "matched_skills": "", "why_match": "Filtered: title not RN/mobile/fullstack JS"}
        out.pop("posted_dt", None)
        out.update({"resume_id": "", "resume_label": "", "resume_path": "", "apply_status": "skipped"})
        return out

    role, role_frac = best_role_match(job, roles)
    sk, matched_skills = skill_score(job, cfg.get("skills_weights") or {})
    # require some skill signal for mobile/RN stack
    text = _blob(job)
    stack_hit = any(
        k in text
        for k in ("react native", "react", "typescript", "node.js", "nodejs", "mobile", "next.js")
    )
    if not stack_hit:
        role_frac *= 0.2
    # combine: role fit 55%, skills 45%
    total = round(role_frac * 55.0 + (sk / 100.0) * 45.0, 1)

    # location boost
    loc = f"{job.get('location','')} {_blob(job)}".lower()
    if any(x in loc for x in ("dubai", "abu dhabi", "abudhabi", "uae", "united arab")):
        total = min(100.0, total + 8.0)

    why_parts = []
    if role:
        why_parts.append(f"Closest target role: {role}")
    if matched_skills:
        why_parts.append("Skills: " + ", ".join(matched_skills[:8]))
    if job.get("age_hours") is not None:
        why_parts.append(f"Posted ~{job['age_hours']}h ago")
    elif job.get("age_unknown"):
        why_parts.append("Post date unknown (kept)")

    resume = pick_resume(job, cfg)
    out = {**job, **resume}
    out.pop("posted_dt", None)
    out["match_score"] = total
    out["matched_role"] = role
    out["matched_skills"] = ", ".join(matched_skills)
    out["why_match"] = "; ".join(why_parts)
    out["apply_status"] = "pending"  # pending | apply | skipped | applied
    return out


def rank_jobs(jobs: list[dict[str, Any]], cfg: dict[str, Any], roles: list[str]) -> list[dict[str, Any]]:
    min_score = float(cfg.get("min_score") or 55)
    scored = [score_job(j, cfg, roles) for j in jobs]
    scored = [j for j in scored if j["match_score"] >= min_score]
    scored.sort(key=lambda j: (-j["match_score"], j.get("posted_at") or ""))
    return scored
