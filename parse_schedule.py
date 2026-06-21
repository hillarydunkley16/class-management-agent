"""
parse_schedule.py

Parses Hillary's schedule docx files into a list of structured rows,
ready to be written to the 'schedule' tab of the Google Sheet.

Usage:
    python parse_schedule.py path/to/schedule.docx
    python parse_schedule.py path/to/schedules/   # parse all docx in a folder

Output schema per row:
    month | week | day | time_start | time_end | class_id | teacher | note | version

version is 'original' or 'updated' — when a month has both a base schedule and a
_NEW replacement, the agent should prefer 'updated' rows for overlapping weeks.
"""

import re
import sys
import json
from pathlib import Path
from docx import Document

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]

MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
          "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]

# Time slot pattern e.g. "8-9", "10-11"
TIME_PATTERN = re.compile(r"^(\d+)-(\d+)$")

# Class cell pattern e.g. "2C ETI/MAF\n(Gallo)" or "3DTEC\n(Galli)"
# Teacher is in parentheses, class id is everything before
CLASS_PATTERN = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$", re.DOTALL)


def extract_month(path: Path) -> str:
    """Extract month from filename e.g. 'HILLARY_SCHEDULE FEBRUARY.docx' -> 'February'"""
    name = path.stem.upper()
    for month in MONTHS:
        if month in name:
            return month.capitalize()
    return "unknown"


def extract_version(path: Path) -> str:
    """Return 'updated' if filename contains _NEW, otherwise 'original'."""
    return "updated" if "NEW" in path.stem.upper() else "original"


# For months where the docx has no week headers, expand into these weeks.
# Add entries here if other months need the same treatment.
MONTH_WEEKS = {
    "November": ["3rd-7th Nov", "10th-14th Nov", "17th-21st Nov", "24th-28th Nov"],
}


def clean(text: str) -> str:
    """Strip whitespace and normalise internal spaces."""
    return " ".join(text.split())


def normalise_class_id(class_id: str) -> str:
    """
    Insert a space between the class code and department suffix where missing.
    e.g. '2ELSE' -> '2E LSE', '1BLSS' -> '1B LSS', '2CETI/MAF' -> '2C ETI/MAF'
    Leaves already-spaced IDs like '2C ETI/MAF' unchanged.
    """
    # Match digit(s) + single letter + department (2+ letters, optionally /letters)
    return re.sub(r"^(\d+)([A-Z])([A-Z]{2,}(?:/[A-Z]+)?)$", r"\1\2 \3", class_id)


def parse_cell(raw: str):
    """
    Parse a table cell into (class_id, teacher, note).
    Returns (None, None, note) for non-class cells.
    """
    text = clean(raw)

    if not text or text == "***":
        return None, None, "prep"

    if text == "OFF":
        return None, None, "off"

    if text == "HOLIDAY":
        return None, None, "holiday"

    if text.lower().startswith("meeting"):
        return None, None, text

    match = CLASS_PATTERN.match(text)
    if match:
        class_id = normalise_class_id(clean(match.group(1)))
        teacher = clean(match.group(2))
        return class_id, teacher, None

    # Fallback: treat whole cell as a note
    return None, None, text


def parse_week_header(text: str) -> str:
    """
    Extract the week date range from a paragraph like:
    'HILLARY DUNKLEY'S SCHEDULE – DECEMBER week 1st-5th December'
    Returns e.g. 'December 1-5' or the raw text if pattern not matched.
    """
    text = clean(text)
    # Try to find "week X" pattern
    match = re.search(r"week\s+(.+?)(?:\s+\w+)?$", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: return everything after the em dash
    parts = re.split(r"[–—]", text)
    if len(parts) > 1:
        return clean(parts[-1])
    return text


def parse_document(path: Path) -> list[dict]:
    """Parse a single docx file into a list of schedule row dicts."""
    doc = Document(path)
    rows = []
    month = extract_month(path)
    version = extract_version(path)

    # Collect paragraphs and tables in document order
    # python-docx exposes them separately, so we need to walk the XML
    body = doc.element.body

    current_week = "unknown"
    table_index = 0
    para_index = 0

    # Build ordered list of (type, object)
    elements = []
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            elements.append(("para", doc.paragraphs[para_index]))
            para_index += 1
        elif tag == "tbl":
            elements.append(("table", doc.tables[table_index]))
            table_index += 1

    for elem_type, elem in elements:
        if elem_type == "para":
            text = clean(elem.text)
            if text and ("SCHEDULE" in text.upper() or "week" in text.lower()):
                current_week = parse_week_header(text)

        elif elem_type == "table":
            # First row should be day headers
            table_rows = elem.rows
            if len(table_rows) < 2:
                continue

            # Find day columns from header row
            header_cells = [clean(c.text) for c in table_rows[0].cells]
            day_cols = {}  # col_index -> day_name
            for i, h in enumerate(header_cells):
                if h.upper() in DAYS:
                    day_cols[i] = h.upper()

            if not day_cols:
                continue

            # Parse data rows
            for row in table_rows[1:]:
                cells = row.cells
                if not cells:
                    continue

                # First cell is the time slot
                time_text = clean(cells[0].text)
                time_match = TIME_PATTERN.match(time_text)
                if not time_match:
                    continue

                time_start = int(time_match.group(1))
                time_end = int(time_match.group(2))

                for col_idx, day in day_cols.items():
                    if col_idx >= len(cells):
                        continue
                    cell_text = cells[col_idx].text
                    class_id, teacher, note = parse_cell(cell_text)

                    # If week is unknown and month has a fixed expansion, emit
                    # one row per known week instead of a single "unknown" row.
                    weeks_to_emit = (
                        MONTH_WEEKS[month]
                        if current_week == "unknown" and month in MONTH_WEEKS
                        else [current_week]
                    )

                    for week in weeks_to_emit:
                        rows.append({
                            "month": month,
                            "week": week,
                            "day": day,
                            "time_start": time_start,
                            "time_end": time_end,
                            "class_id": class_id or "",
                            "teacher": teacher or "",
                            "note": note or "",
                            "version": version,
                        })

    return rows


def parse_path(target: str) -> list[dict]:
    """Parse a single docx file or all docx files in a folder."""
    p = Path(target)
    all_rows = []

    if p.is_dir():
        files = sorted(p.glob("*.docx"))
        if not files:
            print(f"No .docx files found in {p}")
            return []
        for f in files:
            print(f"Parsing {f.name}...")
            all_rows.extend(parse_document(f))
    elif p.is_file():
        print(f"Parsing {p.name}...")
        all_rows = parse_document(p)
    else:
        print(f"Path not found: {target}")

    return all_rows


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_schedule.py <path_to_docx_or_folder>")
        sys.exit(1)

    rows = parse_path(sys.argv[1])

    if not rows:
        print("No rows extracted.")
        return

    # Print summary
    classes_found = set(r["class_id"] for r in rows if r["class_id"])
    print(f"\nExtracted {len(rows)} rows across {len(classes_found)} classes.")
    print(f"Classes found: {sorted(classes_found)}\n")

    # Print first 10 rows as a preview
    print("Preview (first 10 rows):")
    for r in rows[:10]:
        print(r)

    # Save full output as JSON for inspection
    out_path = Path("schedule_parsed.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\nFull output saved to {out_path}")

    print("\nColumn order for Google Sheet:")
    print("month | week | day | time_start | time_end | class_id | teacher | note | version")


if __name__ == "__main__":
    main()