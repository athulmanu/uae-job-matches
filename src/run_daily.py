#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import all_target_roles, load_config  # noqa: E402
from fetchers import collect_jobs, uae_apis_configured  # noqa: E402
from groq_rank import groq_enabled, refine_with_groq  # noqa: E402
from matcher import rank_jobs  # noqa: E402
from sheets import push_google_sheet  # noqa: E402
from writers import write_csv, write_excel, write_json  # noqa: E402


def search_queries(roles: list[str]) -> list[str]:
    # Compact high-signal queries for APIs
    seeds = [
        "React Native",
        "React Native Developer",
        "Senior React Native",
        "Mobile Application Developer",
        "React Native Engineer",
        "Full Stack JavaScript",
        "React Node Developer",
        "MERN Stack",
        "Mobile Software Engineer Dubai",
        "React Native Abu Dhabi",
        "React Native Banking",
        "Frontend Engineer Banking",
    ]
    # add a few exact primary roles
    for r in roles[:8]:
        if r not in seeds:
            seeds.append(r)
    return seeds


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily UAE job matcher for Athul")
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--max-age-hours", type=int, default=None)
    parser.add_argument("--no-sheets", action="store_true", help="Skip Google Sheets push")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    if args.min_score is not None:
        cfg["min_score"] = args.min_score
    if args.max_age_hours is not None:
        cfg["max_age_hours"] = args.max_age_hours

    roles = all_target_roles(cfg)
    queries = search_queries(roles)

    apis = uae_apis_configured()
    print(f"[{datetime.now(timezone.utc).isoformat()}] Fetching jobs…")
    print(
        f"  Sources — Career boards: {apis.get('career_boards')} | "
        f"JSearch: {apis['jsearch']} | Jooble: {apis['jooble']}"
    )
    raw = collect_jobs(cfg, queries)
    print(f"  Raw candidates after location/age filters: {len(raw)}")
    # Lower keyword gate when Groq will re-rank (catch more UAE eng roles)
    keyword_min = float(cfg.get("min_score") or 35)
    rank_cfg = dict(cfg)
    if groq_enabled():
        keyword_min = min(keyword_min, 20.0)
        rank_cfg["min_score"] = keyword_min
        rank_cfg["groq_passthrough"] = True
        print(f"  Groq: enabled ({__import__('os').environ.get('GROQ_MODEL', 'openai/gpt-oss-20b')}) — prefilter min={keyword_min}")
    else:
        print("  Groq: disabled (set GROQ_API_KEY)")
    matched = rank_jobs(raw, rank_cfg, roles)
    print(f"  After keyword match: {len(matched)}")
    if groq_enabled() and matched:
        matched = refine_with_groq(
            matched, cfg, roles, min_score=float(cfg.get("min_score") or 35)
        )
        print(f"  After Groq refine: {len(matched)}")
    print(f"  Final matches (min {cfg.get('min_score')}): {len(matched)}")

    out_cfg = cfg.get("output") or {}
    excel_path = ROOT / out_cfg.get("excel", "output/daily_jobs.xlsx")
    csv_path = ROOT / out_cfg.get("csv", "output/daily_jobs.csv")
    json_path = ROOT / out_cfg.get("json", "output/daily_jobs.json")

    if args.dry_run:
        print(json.dumps(matched[:5], indent=2))
        return 0

    write_excel(matched, excel_path, out_cfg.get("sheet_name", "Daily Matches"))
    write_csv(matched, csv_path)
    write_json(
        matched,
        json_path,
        meta={
            "locations": cfg.get("locations"),
            "max_age_hours": cfg.get("max_age_hours"),
            "min_score": cfg.get("min_score"),
            "role_count": len(roles),
            "uae_apis": apis,
            "groq": groq_enabled(),
            "groq_model": __import__("os").environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
            if groq_enabled()
            else None,
            "needs_api_keys": False,
            "message": (
                "Career boards + Groq ranking."
                if groq_enabled()
                else "Career boards only. Add GROQ_API_KEY for smarter ranking."
            ),
        },
    )

    # Copy JSON into dashboard for GitHub Pages
    dash_data = ROOT / "dashboard" / "jobs.json"
    dash_data.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(json_path, dash_data)

    sheet_url = None
    if not args.no_sheets:
        try:
            sheet_url = push_google_sheet(matched)
        except Exception as exc:  # noqa: BLE001 — surface config issues clearly
            print(f"  Google Sheets push skipped/failed: {exc}")

    print(f"  Excel: {excel_path}")
    print(f"  CSV:   {csv_path}")
    print(f"  JSON:  {json_path}")
    print(f"  Dashboard data: {dash_data}")
    if sheet_url:
        print(f"  Google Sheet: {sheet_url}")
    else:
        print("  Google Sheet: not configured (set GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_SHEET_ID)")

    # brief console preview
    for j in matched[:10]:
        print(
            f"  • {j['match_score']:>5} | {j['resume_id']:>2} | {j['title'][:48]} @ {j['company'][:20]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
