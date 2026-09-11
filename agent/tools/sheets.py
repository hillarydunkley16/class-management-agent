import gspread
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool
from datetime import datetime, date
import streamlit as st
import re

from agent.tools.helpers import date_to_week_range
# from agent.tools.class_lookup import ClassIndex

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
_sheet_cache = {}
def get_records_cached(spreadsheet_id: str, worksheet_name: str): 
    print(f"GETTING RECORDS FOR {worksheet_name}")
    key = (spreadsheet_id, worksheet_name)

    if key not in _sheet_cache: 
        print("CACHE MISS:", worksheet_name)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(worksheet_name)
        print(f"FETCHING {worksheet_name} FROM GOOGLE")
        _sheet_cache[key] = worksheet.get_all_records()
    else: 
        print("CACHE HIT: ", key)

    return _sheet_cache[key]

        

def normalise_class_id(class_id: str) -> str:
    """
    Normalize a class ID to canonical form: uppercase, with a space
    inserted between the class code and department suffix if missing.
    """
    cleaned = class_id.strip().upper()

    return re.sub(
        r"^(\d+)([A-Z])([A-Z]{2,}(?:/[A-Z]+)?)$",
        r"\1\2 \3",
        cleaned,
    )
# ---------------------------
# CLASS INDEX CACHE
# ---------------------------
# _class_index_cache = {}

# def get_class_index(gc_spreadsheet):
#     key = gc_spreadsheet.id

#     if key in _class_index_cache:
#         return _class_index_cache[key]

#     ws = gc_spreadsheet.worksheet("classes")
#     class_list = [row[0] for row in ws.get_all_values()[1:] if row]

#     index = ClassIndex(class_list)
#     _class_index_cache[key] = index
#     return index


# ---------------------------
# HELPERS (UNCHANGED LOGIC)
# ---------------------------
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


def get_curriculum_lesson(curriculum_records, lesson_number, class_level):
    for row in curriculum_records:
        try:
            if int(row["lesson_number"]) != lesson_number:
                continue
        except Exception:
            continue

        if level_matches(row.get("level", ""), class_level):
            return row

    return None


# ---------------------------
# INTERNAL SHEET FUNCTIONS
# ---------------------------



def _get_class_progress(spreadsheet_id: str, class_id: str):
   

    class_id = normalise_class_id(class_id)
    all_records = get_records_cached(
    spreadsheet_id,
    "progress",
    )
    

    return [r for r in all_records if r.get("class_id") == class_id]


def _get_assignments(spreadsheet_id: str, class_id: str):
    

    class_id = normalise_class_id(class_id)
    all_records = get_records_cached(
    spreadsheet_id,
    "assignments",
    )

    return [r for r in all_records if r.get("class_id") == class_id]


# ---------------------------
# TOOLS
# ---------------------------

@tool
def class_info(spreadsheet_id: str, class_id: str) -> list:
    """Returns the class info of a given class"""
    # gc_spreadsheet = gc.open_by_key(spreadsheet_id)
    print("TOOL CALLED: CLASS INFO")
    class_id = normalise_class_id(class_id)

    progress = _get_class_progress(spreadsheet_id, class_id)
    assignments = _get_assignments(spreadsheet_id, class_id)

    return [progress, assignments]

    
@tool
def get_next_lesson(
    class_id: str,
    spreadsheet_id: str,
    override_status: str = None,
    override_last_slide: str = None,
):
    """Gets the next lesson in a curriculum of a given class. There are 10 lessons in the curriculum. If a class level is not appropriate, still suggest a lesson."""

    print("TOOL CALLED: GET NEXT LESSON")

    class_id = normalise_class_id(class_id)

    progress_records = get_records_cached(
    spreadsheet_id,
    "progress"
)

    class_records = get_records_cached(
        spreadsheet_id,
        "classes"
    )

    curriculum_records = get_records_cached(
        spreadsheet_id,
        "curriculum"
    )

    class_progress = next(
        (r for r in progress_records if r["class_id"] == class_id),
        None
    )

    if not class_progress:
        return {"error": f"No progress found for {class_id}"}

    class_info = next(
        (r for r in class_records if r["class_id"] == class_id),
        None
    )

    if not class_info:
        return {"error": f"No class info found for {class_id}"}

    level = class_info.get("level")

    status = override_status or class_progress.get("status")
    last_slide = override_last_slide or class_progress.get("last_slide")
    lesson_number = int(class_progress.get("lesson_number"))

    # CASE 1: resume
    if status == "in_progress":
        lesson = get_curriculum_lesson(
            curriculum_records,
            lesson_number,
            level,
        )

        if not lesson:
            return {"error": f"Lesson {lesson_number} not found"}

        return {
            "action": "resume",
            "class_id": class_id,
            "lesson_number": lesson_number,
            "topic": lesson["topic"],
            "slides_url": lesson["slides_url"],
            "last_slide": last_slide,
        }

    # CASE 2: next lesson
    if status == "completed":
        next_lesson = lesson_number + 1

        max_lesson = max(int(r["lesson_number"]) for r in curriculum_records)

        if next_lesson > max_lesson:
            return {
                "action": "curriculum_complete",
                "class_id": class_id,
            }

        lesson = get_curriculum_lesson(
            curriculum_records,
            next_lesson,
            level,
        )

        if not lesson:
            return {
                "error": f"No matching lesson for level {level}"
            }

        return {
            "action": "start_new",
            "class_id": class_id,
            "lesson_number": next_lesson,
            "topic": lesson["topic"],
            "slides_url": lesson["slides_url"],
        }

    return {"error": f"Unknown status {status}"}



@tool
def update_progress(class_id: str, spreadsheet_id: str, updates: dict):
    """Updates the progress of a given class"""
    print("CALLING TOOL: UPDATE_PROGRESS")
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)
    

    class_id = normalise_class_id(class_id)
    ws = gc_spreadsheet.worksheet("progress")
    rows = ws.get_all_records()

    

    row_index = next(
        (i for i, r in enumerate(rows, start=2)
         if r["class_id"] == class_id),
        None
    )

    if row_index is None:
        return f"No progress record for {class_id}"

    ALLOWED = {"lesson_number", "status", "last_slide", "date", "notes"}

    for k in updates:
        if k not in ALLOWED:
            raise ValueError(f"Invalid field: {k}")

    headers = ws.row_values(1)
    col_index = lambda f: headers.index(f) + 1

    for field, value in updates.items():
        ws.update_cell(row_index, col_index(field), value)
    _sheet_cache.pop((spreadsheet_id, "progress"), None)
    return f"Updated {class_id}: {updates}"
@tool 
def assignment_overview(spreadsheet_id: str):
    """Gives an overview of the assignment spreadsheet"""
    
@tool
def add_assignment(spreadsheet_id: str, class_id: str, assignment_type: str, context: str, status: str, due_date: str):
    """Adds an assignment to the assignment sheet
    class_id	lesson_number	assignment_type	context	status	due_date	note
     """
    print("CALLING TOOL: ADD ASSIGNMENT")
    gc_spreadsheet = gc.open_by_key(spreadsheet_id) 
    ws = gc_spreadsheet.worksheet("assignments")
    info = _get_class_progress(spreadsheet_id, class_id)
    
    ws.append_row([class_id, info[0].get("lesson_number"), assignment_type, context, status, due_date, ""])


@tool
def update_assignment(spreadsheet_id: str, class_id: str, updates: dict):
    """Updates an assignment of a given class"""
    print("CALLING TOOL: UPDATE ASSIGNMENT")
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    class_id = normalise_class_id(class_id)

    ws = gc_spreadsheet.worksheet("assignments")
    rows = ws.get_all_records()

    row_index = next(
        (i for i, r in enumerate(rows, start=2)
         if r["class_id"] == class_id),
        None
    )

    if row_index is None:
        return f"No assignment found for {class_id}"

    ALLOWED = {"status", "due_date", "note"}

    for k in updates:
        if k not in ALLOWED:
            raise ValueError(f"Invalid field: {k}")

    headers = ws.row_values(1)
    col_index = lambda f: headers.index(f) + 1

    for field, value in updates.items():
        ws.update_cell(row_index, col_index(field), value)
    _sheet_cache.pop((spreadsheet_id, "assignments"), None)
    return f"Updated assignment {class_id}: {updates}"
# @tool
# def get_schedule_for_date(date: date, spreadsheet_id: str):
#     """Fetches the schedule for a given date"""
#     all_records = get_records_cached(
#         spreadsheet_id, 
#         "schedule"
#     )
#     date = date_to_week_range(date, all_records)

#     return 

from datetime import datetime
from collections import defaultdict

@tool
def get_schedule_for_date(query_date: str, spreadsheet_id: str):
    """
    Returns the scheduled classes for a specific date (YYYY-MM-DD format).
    Infers the week range from the schedule sheet's existing week labels,
    then filters to the matching day. Prefers 'updated' version rows over
    'original' on a per-time-slot basis when both exist for the same week.
    """
    date_obj = datetime.strptime(query_date, "%Y-%m-%d").date()

    all_records = get_records_cached(spreadsheet_id, "schedule")

    result = date_to_week_range(date_obj, all_records)
    if not result:
        return [{"error": f"No schedule data found covering {query_date}"}]

    month, week = result
    day_name = date_obj.strftime("%A").upper()

    # Filter to matching month/week/day
    matches = [
        r for r in all_records
        if r["month"] == month
        and r["week"] == week
        and r["day"] == day_name
    ]

    # Prefer 'updated' over 'original' PER TIME SLOT, not for the whole day —
    # otherwise one updated row anywhere wipes out every other valid original row
    by_slot = defaultdict(list)
    for r in matches:
        by_slot[(r["time_start"], r["time_end"])].append(r)

    resolved = []
    for slot_rows in by_slot.values():
        updated_rows = [r for r in slot_rows if r["version"] == "updated"]
        resolved.extend(updated_rows if updated_rows else slot_rows)

    # Drop prep/off slots — only return actual classes
    classes = [r for r in resolved if r["class_id"]]

    return classes if classes else [{"info": f"No classes scheduled on {query_date}"}]