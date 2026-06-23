import gspread
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool
from datetime import datetime
import calendar
import re
from langgraph.types import interrupt
import streamlit as st
from agent.tools.helpers import date_to_week_range, normalise_class_id
import re
from datetime import datetime, date
from agent.tools.class_lookup import ClassIndex, canonicalize_class_id
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
_class_index_cache = {}
def get_class_index(gc_spreadsheet):
    key = gc_spreadsheet.id

    if key in _class_index_cache:
        return _class_index_cache[key]

    ws = gc_spreadsheet.worksheet("classes")
    class_list = [row[0] for row in ws.get_all_values()[1:] if row]

    index = ClassIndex(class_list)
    _class_index_cache[key] = index

    return index
# Authorize gspread
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)
gc = gspread.authorize(credentials)  
def normalise_class_id(class_id: str) -> str:
    """
    Insert a space between the class code and department suffix where missing.
    e.g. '2ELSE' -> '2E LSE', '1BLSS' -> '1B LSS', '2CETI/MAF' -> '2C ETI/MAF'
    Leaves already-spaced IDs like '2C ETI/MAF' unchanged.
    """
    return re.sub(r"^(\d+)([A-Z])([A-Z]{2,}(?:/[A-Z]+)?)$", r"\1\2 \3", class_id.strip())

def date_to_week_range(query_date: date, schedule_rows: list[dict]) -> tuple[str, str] | None:
    """
    Infer which (month, week) range a date falls in by parsing the week
    labels that already exist in the schedule data.
    """
    month_name = query_date.strftime("%B")
    day_num = query_date.day

    # Get all unique week labels for this month from the sheet
    week_labels = set(
        r["week"] for r in schedule_rows
        if r["month"] == month_name
    )

    for label in week_labels:
        # Parse start and end day numbers from labels like "8th-10th", "23rd-27th"
        numbers = re.findall(r"\d+", label)
        if len(numbers) >= 2:
            start_day, end_day = int(numbers[0]), int(numbers[1])
            if start_day <= day_num <= end_day:
                return month_name, label

    return None
# Define the scope
  
@tool
def read_sheet(spreadsheet_id: str, sheet_name: str) -> list:
    """Reads all data from a worksheet given its ID."""
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.get_all_records()


@tool
def get_variations_for_date(query_date: str, spreadsheet_id: str) -> list:
    """
    Returns variations that apply to a specific date.
    """
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    # read schedule rows
    schedule_ws = gc_spreadsheet.worksheet("schedule")
    schedule_rows = schedule_ws.get_all_records()

    d = datetime.strptime(query_date, "%Y-%m-%d").date()

    result = date_to_week_range(d, schedule_rows)

    if not result:
        return [{"error": f"No schedule data found covering {query_date}"}]

    # now read variations
    variations_ws = gc_spreadsheet.worksheet("variations")
    variation_rows = variations_ws.get_all_records()

    matches = [
        r for r in variation_rows
        if r.get("date") == query_date
    ]

    return matches
def level_matches(curriculum_level: str, class_level: str) -> bool:
    curriculum_level = str(curriculum_level).strip().lower()
    class_level = str(class_level).strip().lower()

    if curriculum_level == "all":
        return True

    levels = [
        x.strip()
        for x in curriculum_level.split("/")
    ]

    return class_level in levels

def get_curriculum_lesson(
    curriculum_records,
    lesson_number,
    class_level,
):
    for row in curriculum_records:

        try:
            row_lesson = int(row["lesson_number"])
        except Exception:
            continue

        if row_lesson != lesson_number:
            continue

        if level_matches(
            row.get("level", ""),
            class_level,
        ):
            return row

    return None
def _get_class_progress(spreadsheet_id: str,  class_id: str) -> list: 
    """Get progress for a given class in the 'progress' tab"""
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("progress")
    all_records = worksheet.get_all_records()
    class_progress = [r for r in all_records if r.get("class_id") == class_id]
    return class_progress

def _get_assignments(spreadsheet_id: str, class_id: str, ): 
    """Used to fetch class-specific information in 'classes' and 'assignments' tabs'"""
    spreadsheet= gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("assignments")
    all_records = worksheet.get_all_records()
    matches = [r for r in all_records if class_id in str(r.values())]
    return matches
        
@tool 
def class_info(spreadsheet_id: str, class_id: str) -> list:
    """
    Fetches the most recent information about a specific class from progress and assignments 
    """
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    # 1. get or build index
    class_index = get_class_index(gc_spreadsheet)

    # 2. resolve messy input → canonical sheet ID
    resolved = class_index.resolve(class_id)

    if resolved is None:
        raise ValueError(f"Unknown class_id: {class_id}")

    class_id = resolved["resolved"]
    progress = _get_class_progress(spreadsheet_id, class_id) 
    assignments = _get_assignments(spreadsheet_id, class_id)
    return [progress, assignments]

@tool
def get_schedule_for_date(query_date: str, spreadsheet_id: str) -> list:
    """
    Returns the scheduled classes for a specific date (YYYY-MM-DD format).
    Infers the week range from the schedule sheet's existing week labels,
    then filters to the matching day. Prefers 'updated' version rows over
    'original' when both exist for the same week.
    """
    d = datetime.strptime(query_date, "%Y-%m-%d").date()
#     credentials = Credentials.from_service_account_info(
#     st.secrets["gcp_service_account"],
#     scopes=SCOPES
# )
#     gc = gspread.authorize(credentials)   
    # Read the full schedule tab once
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)
    ws = gc_spreadsheet.worksheet("schedule")
    schedule_rows = ws.get_all_records()

    # Infer which week range this date falls in
    result = date_to_week_range(d, schedule_rows)
    if not result:
        return [{"error": f"No schedule data found covering {query_date}"}]

    month, week = result
    day_name = d.strftime("%A").upper()

    # Filter to matching month/week/day
    matches = [
        r for r in schedule_rows
        if r["month"] == month
        and r["week"] == week
        and r["day"] == day_name
    ]

    # Prefer 'updated' rows over 'original' if both versions exist
    has_updated = any(r["version"] == "updated" for r in matches)
    if has_updated:
        matches = [r for r in matches if r["version"] == "updated"]

    # Drop prep/off slots — only return actual classes
    classes = [r for r in matches if r["class_id"]]

    return classes if classes else [{"info": f"No classes scheduled on {query_date}"}]


@tool
def get_next_lesson(
    class_id: str,
    spreadsheet_id: str,
    override_status: str = None,
    override_last_slide: str = None,
):
    """
    Returns the next teaching action for a class.
    """
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)
    class_index = get_class_index(gc_spreadsheet)

    # STEP 2: resolve user input → canonical class
    resolved = class_index.resolve(class_id)
    if resolved is None:
        raise ValueError(f"Unknown class: {class_id}")

    class_id = resolved["resolved"]

    ws_progress = gc_spreadsheet.worksheet("progress")
    ws_classes = gc_spreadsheet.worksheet("classes")
    ws_curriculum = gc_spreadsheet.worksheet("curriculum")

    progress_records = ws_progress.get_all_records()
    class_records = ws_classes.get_all_records()
    curriculum_records = ws_curriculum.get_all_records()

    class_progress = next(
        (
            r
            for r in progress_records
            if normalise_class_id(r.get("class_id", ""))
            == class_id
        ),
        None,
    )

    if not class_progress:
        return {
            "error": f"No progress found for {class_id}"
        }

    class_info = next(
        (
            r
            for r in class_records
            if normalise_class_id(r.get("class_id", ""))
            == class_id
        ),
        None,
    )

    if not class_info:
        return {
            "error": f"No class information found for {class_id}"
        }

    level = class_info.get("level")

    status = (
        override_status
        if override_status is not None
        else class_progress.get("status")
    )

    last_slide = (
        override_last_slide
        if override_last_slide is not None
        else class_progress.get("last_slide")
    )

    lesson_number = int(
        class_progress.get("lesson_number")
    )

    # CASE 1: Resume lesson

    if status == "in_progress":
        print("CLASS:", class_id)
        print("LEVEL:", level)
        print("STATUS:", status)
        print("LESSON:", lesson_number)
        lesson = get_curriculum_lesson(
            curriculum_records,
            lesson_number,
            level,
        )
        print("LOOKUP RESULT:", lesson)
        if not lesson:
            return {
                "error":
                f"Lesson {lesson_number} not found"
            }

        return {
            "action": "resume",
            "class_id": class_id,
            "level": level,
            "lesson_number": lesson_number,
            "topic": lesson["topic"],
            "slides_url": lesson["slides_url"],
            "last_slide": last_slide,
            "instruction":
                f"Resume lesson {lesson_number} "
                f"({lesson['topic']}) "
                f"from slide {last_slide}",
        }

    # CASE 2: Completed lesson

    if status == "completed":

        next_lesson = lesson_number + 1

        max_lesson = max(
            int(r["lesson_number"])
            for r in curriculum_records
        )

        if next_lesson > max_lesson:
            return {
                "action": "curriculum_complete",
                "class_id": class_id,
                "message":
                    "All lessons completed"
            }
        print("CLASS:", class_id)
        print("LEVEL:", level)
        print("STATUS:", status)
        print("LESSON:", lesson_number)
        lesson = get_curriculum_lesson(
            curriculum_records,
            next_lesson,
            level,
        )
        print("LOOKUP RESULT:", lesson)

        if not lesson:
            return {
                "error":
                    f"Lesson {next_lesson} exists "
                    f"but no matching level "
                    f"was found ({level})"
            }

        return {
            "action": "start_new",
            "class_id": class_id,
            "level": level,
            "lesson_number": next_lesson,
            "topic": lesson["topic"],
            "slides_url": lesson["slides_url"],
            "instruction":
                f"Start lesson {next_lesson} "
                f"({lesson['topic']})",
        }

    return {
        "error":
            f"Unknown status '{status}'"
    }
@tool 
def update_progress(class_id: str, spreadsheet_id: str, updates: dict ): 
    """
        Update progress fields for a specific class in the 'progress' sheet.

        Only fields provided in `updates` are modified.

        Allowed fields:
        - lesson_number
        - status
        - last_slide
        - date
        - notes
    """
    class_id = normalise_class_id(class_id)
    ws = gc.open_by_key(spreadsheet_id).worksheet("progress")
    rows = ws.get_all_records()
    row_index = next(
        (i for i, r in enumerate(rows, start=2)
        if r["class_id"] == class_id), 
        None
    )
    if row_index is None: 
        return f"No progress record found for class_id {class_id}"
    ALLOWED_PROGRESS_FIELDS = {
    "lesson_number",
    "status",
    "last_slide",
    "date",
    "notes",
    }
    for key in updates:
        if key not in ALLOWED_PROGRESS_FIELDS:
            raise ValueError(f"Invalid field: {key}")
    
    headers = ws.row_values(1)
    def col_index(field:str) -> int: 
        return headers.index(field) +1 
    for field, value in updates.items(): 
        col = col_index(field)
        ws.update_cell(row_index, col, value)
    return f"Progress updated for {class_id}: {updates}"   
    
@tool 
def update_assignment(spreadsheet_id: str, class_id: str, updates: dict):
    """Will update assignment sheet with new status, due_date or note""" 
    ALLOWED_PROGRESS_FIELDS = {
        "status", 
        "due_date", 
        "note"
    }
    class_id = normalise_class_id(class_id)
    ws = gc.open_by_key(spreadsheet_id).worksheet("assignments")
    rows = ws.get_all_records()
    row_index = next(
        (i for i, r in enumerate(rows, start=2)
        if r["class_id"] == class_id), 
        None
    )
    if row_index is None: 
        return f"No assignments found for class_id {class_id}"
    for key in updates: 
        if key not in ALLOWED_PROGRESS_FIELDS: 
            raise ValueError(f"Invalid field: {key}")
    headers = ws.row_values(1)
    def col_index(field:str) -> int: 
        return headers.index(field) +1 
    for field, value in updates.items(): 
        col = col_index(field)
        ws.update_cell(row_index, col, value)
    return f"Assignment updated for {class_id}: {updates}"   



