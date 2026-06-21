Class Management AI Agent

Phase one:

Organizing data into something a LLM can easily query.

Previously schedule information was organized into docx files which contained tables

schedule variations were communicated via email

First needed to anonymize docx and emails - done with scripts

Second needed to parse docx files into json, done with an AI generated script

Third upload parsed data to google sheets, also done with AI generated script

First tested out llm's abilities to edit google sheets through Google Sheets ipynb. This was successful.

The 'schedule' tab has columns for 'month', 'week', 'day', 'time_start', 'time_end', 'class_id', 'teacher', 'note' and 'version'

The 'variations' tab has columns for 'date', 'class_id', 'change_type', 'detail', and 'source_email'

Answering a basic question about schedule is using up way too many tokens. 

Instead of having a basic read_sheet, which will read the entire sheet and use many tokens, have specific tools/helper functions that are specific to each tab 

get_class_info(class_id)
get_progress(class_id)
get_assignments(class_id)
get_schedule_for_day(date)
find_variations(date)

Right now the llm can't get the classes for a specific day based off the google sheet set up 

Either need to restructure the google sheet so each individual day is accounted for 

Or need the llm to figure out which day of the month belongs with which row/day of the week.
