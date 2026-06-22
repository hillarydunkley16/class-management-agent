import re
from datetime import datetime, date
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