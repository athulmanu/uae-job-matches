# Auto — daily UAE job matches (Athul)

Matches **Dubai / Abu Dhabi / UAE** roles against your target list, scores them, picks the **5+** or **6+** resume, and writes:

- `output/daily_jobs.xlsx` — Excel digest  
- `output/daily_jobs.csv` — import to Google Sheets  
- `dashboard/` — static site for GitHub Pages  

LinkedIn login / auto-apply is **not** used (account ban risk). You apply manually; mark rows `apply` when you want draft help in chat.

## Resume mapping

| Signal in title / JD | Resume sent |
|---|---|
| Senior / Lead / Banking / Enterprise / 6+ years | `Athul_S_Babu-_Software_Developer_6_.pdf` |
| Otherwise (mid RN / mobile) | `Athul_S_Babu-_Software_Developer_5_.pdf` |

## Local run

```bash
cd Auto
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional keys
python src/run_daily.py
```

Open `output/daily_jobs.xlsx` or `dashboard/index.html` (needs a local server if you want fetch to work):

```bash
cd dashboard && python -m http.server 5175
```

## Google Sheet

1. Create an empty Google Sheet and copy its ID from the URL.  
2. Google Cloud → create a service account → download JSON key.  
3. Share the Sheet with the service account email (**Editor**).  
4. Set in `.env` / GitHub Secrets:

- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (local: file path; GitHub: paste full JSON as a secret)

Without this, use the Excel/CSV and **File → Import** into Sheets.

## UAE coverage (no JSearch required)

Default source: **curated company career pages** in `boards.yaml` (public Greenhouse / Lever JSON) filtered to Dubai / Abu Dhabi / UAE. Works with **zero API keys**.

Optional extras (if you get them working):

| Secret | What it adds |
|--------|--------------|
| `RAPIDAPI_KEY` | Broader Google-for-Jobs style search (JSearch) |
| `JOOBLE_API_KEY` | Extra UAE aggregator |

Add company board tokens to `boards.yaml` anytime (e.g. `careem`, `deliveroo`).

## GitHub deploy (`athulmanu`)

This machine’s `gh` is currently logged into a **different / broken** account. Use **athulmanu**:

```bash
gh auth logout
gh auth login -h github.com
# choose athulmanu

cd /Users/athul/per/Auto
git init
git add .
git commit -m "feat: daily UAE job matcher and dashboard"
gh repo create athulmanu/uae-job-matches --public --source=. --remote=origin --push

# Enable Pages: Settings → Pages → Source = GitHub Actions
# Add secrets: RAPIDAPI_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON (optional)
```

Daily cron runs at **06:00 UTC (10:00 GST)** and refreshes the dashboard + Excel artifact.

## Apply trigger (human-in-the-loop)

1. In the Sheet/Excel set **Apply Status** = `apply` for chosen rows.  
2. In Cursor chat: “draft applications for rows marked apply” (paste sheet rows or the Excel).  
3. You submit on the employer site with the suggested resume file.

## Target roles

Configured in `config.yaml` — primary React Native / mobile, full stack JS, and banking/fintech variants for UAE.
