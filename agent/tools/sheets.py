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
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    class_id = normalise_class_id(class_id)
    ws = gc_spreadsheet.worksheet("progress")
    records = ws.get_all_records()

    return [r for r in records if r.get("class_id") == class_id]


def _get_assignments(spreadsheet_id: str, class_id: str):
    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    class_id = normalise_class_id(class_id)
    ws = gc_spreadsheet.worksheet("assignments")
    records = ws.get_all_records()

    return [r for r in records if r.get("class_id") == class_id]


# ---------------------------
# TOOLS
# ---------------------------

@tool
def class_info(spreadsheet_id: str, class_id: str) -> list:
    """Returns the class info of a given class"""
    # gc_spreadsheet = gc.open_by_key(spreadsheet_id)

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

    gc_spreadsheet = gc.open_by_key(spreadsheet_id)

    class_id = normalise_class_id(class_id)

    ws_progress = gc_spreadsheet.worksheet("progress")
    ws_classes = gc_spreadsheet.worksheet("classes")
    ws_curriculum = gc_spreadsheet.worksheet("curriculum")

    progress_records = ws_progress.get_all_records()
    class_records = ws_classes.get_all_records()
    curriculum_records = ws_curriculum.get_all_records()

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

    return f"Updated {class_id}: {updates}"


@tool
def update_assignment(spreadsheet_id: str, class_id: str, updates: dict):
    """Updates an assignment of a given class"""
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

    return f"Updated assignment {class_id}: {updates}"