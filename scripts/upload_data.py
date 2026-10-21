"""
upload_schedule.py

Reads schedule_parsed.json and writes it to the 'schedule' tab
of the Google Sheet, creating the tab if it doesn't exist.

Usage:
    python upload_schedule.py

Expects:
    - credentials.json in the same directory
    - schedule_parsed.json in the same directory (output of parse_schedule.py)
    - SPREADSHEET_ID set below
"""

import json
import gspread
from pathlib import Path
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1nUhN2vGokOp2iGCkbGKT6aJT4_Ufzn6u-riS-ML_hyE"
SHEET_NAME = "schedule"
JSON_PATH = Path("schedule_parsed.json")
CREDENTIALS_PATH = Path("credentials.json")

COLUMNS = ["month", "week", "day", "time_start", "time_end",
           "class_id", "teacher", "note", "version"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# ─────────────────────────────────────────────────────────────────────────────


def get_or_create_sheet(spreadsheet, name: str):
    """Return the worksheet with the given name, creating it if needed."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Tab '{name}' not found — creating it.")
        return spreadsheet.add_worksheet(title=name, rows=2000, cols=len(COLUMNS))


def main():
    if not JSON_PATH.exists():
        print(f"Error: {JSON_PATH} not found. Run parse_schedule.py first.")
        return

    # Load JSON
    with open(JSON_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    if not rows:
        print("No rows to upload.")
        return

    print(f"Loaded {len(rows)} rows from {JSON_PATH}.")

    # Auth
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # Get or create the schedule tab
    ws = get_or_create_sheet(spreadsheet, SHEET_NAME)

    # Clear existing content
    ws.clear()
    print(f"Cleared existing content from '{SHEET_NAME}' tab.")

    # Build data: header row + data rows
    header = COLUMNS
    data = [header]
    for row in rows:
        data.append([str(row.get(col, "")) for col in COLUMNS])

    # Upload in one batch call — much faster than row-by-row
    ws.update(range_name="A1", values=data)

    print(f"Uploaded {len(rows)} rows + header to '{SHEET_NAME}' tab.")
    print("Done.")


if __name__ == "__main__":
    main()