# Anonymized Fixtures

This folder contains **entirely fictional** sample data, shaped to match the
real schema used by the teaching assistant agent. No real student, teacher,
or school data appears anywhere in this repository.

These files exist so the project's structure and parsing logic can be
understood and tested without any real data:

- `classes_sample.csv` — sample `classes` tab rows
- `progress_sample.csv` — sample `progress` tab rows
- `variations_sample.csv` — sample `variations` tab rows, as would be
  extracted from schedule-change emails
- `schedule_sample.json` — sample output of the schedule docx parser
- `sample_email_2.eml` — a fictional bilingual (Italian/English) email,
  written to mirror the structure and ambiguity of real schedule-change
  notifications, used to test the email parsing and extraction logic

Class IDs, teacher names, and dates in these files are all invented and do
not correspond to any real person, class, or institution.
