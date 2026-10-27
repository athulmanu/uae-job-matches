from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from writers import COLUMNS


def push_google_sheet(jobs: list[dict[str, Any]], spreadsheet_id: str | None = None) -> str | None:
    """Push rows to Google Sheets if credentials are configured.

    Env:
      GOOGLE_SERVICE_ACCOUNT_JSON — path to service account JSON
      GOOGLE_SHEET_ID — spreadsheet id (or pass spreadsheet_id)
    Share the sheet with the service account email as Editor.
    """
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = (spreadsheet_id or os.environ.get("GOOGLE_SHEET_ID", "")).strip()
    if not creds_path or not sheet_id:
        return None
    if not Path(creds_path).exists():
        raise FileNotFoundError(f"Service account file not found: {creds_path}")

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)

    title = "Daily Matches"
    try:
        ws = sh.worksheet(title)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=max(100, len(jobs) + 10), cols=len(COLUMNS))

    header = [h for _, h in COLUMNS]
    rows = [[job.get(k, "") for k, _ in COLUMNS] for job in jobs]
    ws.update([header] + rows, value_input_option="USER_ENTERED")
    return sh.url
