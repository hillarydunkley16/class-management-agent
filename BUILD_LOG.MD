# Build Log

Working notes from early in the project, kept as-is for anyone interested
in the real-time problem-solving rather than the polished version.

## Phase one: organizing data into something an LLM can easily query

Previously, schedule information was organized into docx files containing
tables. Schedule variations were communicated via email.

* First needed to anonymize docx and emails — done with scripts
* Second, needed to parse docx files into JSON — done with an AI-generated
  script
* Third, upload parsed data to Google Sheets — also done with an
  AI-generated script
* First tested the LLM's ability to edit Google Sheets through a
  `google_sheets.ipynb` notebook. This was successful.

The `schedule` tab has columns for `month`, `week`, `day`, `time_start`,
`time_end`, `class_id`, `teacher`, `note`, and `version`.

The `variations` tab has columns for `date`, `class_id`, `change_type`,
`detail`, and `source_email`.

## Early problem: token usage

Answering a basic question about the schedule was using up way too many
tokens. Instead of having one generic `read_sheet` tool — which reads the
entire sheet and burns tokens on irrelevant rows — the fix was building
specific tools/helper functions scoped to each tab:

```
get_class_info(class_id)
get_progress(class_id)
get_assignments(class_id)
get_schedule_for_day(date)
find_variations(date)
```

(These evolved further over the course of the project — see the final
tool set in `agent/tools/sheets.py`.)

## Early problem: date-to-schedule-row mapping

At one point, the LLM couldn't reliably get the classes for a specific day
based on the Google Sheet structure. Two options were on the table:

* Restructure the Google Sheet so each individual day is accounted for, or
* Have the LLM figure out which calendar day belongs to which row/day-of-week

The second approach won out — see `date_to_week_range()` in
`agent/tools/sheets.py`, which infers the correct week range from the
sheet's existing week labels rather than requiring a rigid one-row-per-day
schema.
