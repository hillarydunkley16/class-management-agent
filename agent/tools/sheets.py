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
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

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
    class_id = normalise_class_id(class_id)
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
    Returns what a class should do next: either where to resume an
    in-progress lesson, or the next lesson in the curriculum if the
    previous one was completed.

    If this is being called right after update_progress in the same turn,
    pass override_status and override_last_slide with the values you just
    wrote, so this tool doesn't depend on re-reading the Sheet (which may
    not yet reflect the write due to call ordering/timing).
    """
    class_id = normalise_class_id(class_id)
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)
    ws_curriculum = gc_spreadsheet.worksheet("curriculum")
    ws_progress = gc_spreadsheet.worksheet("progress")
    ws_classes = gc_spreadsheet.worksheet("classes")

    progress_records = ws_progress.get_all_records()
    
    class_progress = next(
        (r for r in progress_records if r.get("class_id") == class_id),
        None
    )
    if class_progress is None:
        return f"No progress record found for {class_id}"

    # Use overrides if provided, otherwise fall back to what was read from the Sheet
    status = override_status if override_status is not None else class_progress.get("status")
    last_slide = override_last_slide if override_last_slide is not None else class_progress.get("last_slide")
    lesson_number = class_progress.get("lesson_number")

    # Need the class's level to pick the right curriculum variant
    class_records = ws_classes.get_all_records()
    class_info = next(
        (r for r in class_records if r.get("class_id") == class_id),
        None
    )
    level = class_info.get("level") if class_info else None

    curriculum_records = ws_curriculum.get_all_records()

    def get_lesson(lesson_num):
        """Find the curriculum row for a lesson, matching level or 'all'."""
        candidates = [
            r for r in curriculum_records
            if int(r.get("lesson_number")) == lesson_num
            and (r.get("level", "").strip().lower() in ("all", (level or "").lower()))
        ]
        return candidates[0] if candidates else None

    if status == "in_progress":
        lesson = get_lesson(int(lesson_number))
        if lesson is None:
            return f"Lesson {lesson_number} not found in curriculum for level {level}"
        return {
            "action": "resume",
            "class_id": class_id,
            "level": level,
            "lesson_number": lesson_number,
            "topic": lesson.get("topic"),
            "last_slide": last_slide,
            "slides_url": lesson.get("slides_url"),
            "instruction": f"Resume lesson {lesson_number} ({lesson.get('topic')}) from slide {last_slide}"
        }

    elif status == "completed":
        next_lesson_number = int(lesson_number) + 1
        lesson = get_lesson(next_lesson_number)
        if lesson is None:
            return "Finished all lessons in curriculum"
        return {
            "action": "start_new",
            "class_id": class_id,
            "level": level,
            "lesson_number": next_lesson_number,
            "topic": lesson.get("topic"),
            "slides_url": lesson.get("slides_url"),
            "instruction": f"Start lesson {next_lesson_number} ({lesson.get('topic')})"
        }

    else:
        return f"Unrecognized status '{status}' for {class_id}"
# @tool 
# def get_lesson_progress(class_id: str, spreadsheet_id: str): 
#     """Evaluate how far the teacher is in the lesson
#         Go to curriculum and get lesson_number, status
#         If status is in_progress get last_slide 
#         Go to curriculum and find the lesson number, get url 
#         Parse url using google slides api 
#         Get total number of slides and calculate percentage progress in the lesson (i.e. slide 9 of 12 means you are 75% finished with the lesson)
#     """
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



