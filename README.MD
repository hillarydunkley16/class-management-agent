
# Teaching Assistant Agent

A LangGraph-based agent that tracks lesson progress across multiple classes,
so you never have to guess (or accidentally repeat) what you taught last time.

Built from a real problem: as an English teaching assistant working with
10 classes a week, each on its own pace through a shared curriculum, I kept
losing track of where I'd left off with a given class. This agent answers
one question reliably: **"What did I do last time with this class, and
what should I do today?"**

Full writeup, including the architecture decisions and the bugs that taught
me the most, is here: [link to Substack post]

## How it works

- **LangGraph** runs the agent loop: a single agent node reasons about the
  request and calls tools as needed, looping until it has enough to answer.
- **Google Sheets** is the source of truth for everything that needs to
  persist across sessions — class info, curriculum, lesson progress,
  assignments, and schedule variations. LangGraph's own checkpointing
  handles only the in-session conversational memory.
- **Bilingual email parsing** turns real, messy Italian/English schedule
  change emails into structured rows, with validation at the boundary so
  malformed or unrecognized class IDs get rejected rather than silently
  written.

## Data

All real schedule, class, and correspondence data is excluded from this
repo (see `.gitignore`). `fixtures/anonymized/` contains fictional sample
data in the same shape, so the schema and parsing logic can be understood
without any real information.

## Setup

Requires a Google Cloud service account with Sheets + Drive API access,
and an OpenAI API key. See `.env.example` for required environment
variables.

## Build log

This project's earlier working notes — including the original data
modeling decisions and a few problems solved along the way — are kept in
[`BUILD_LOG.md`](./BUILD_LOG.md) for anyone curious about the messier,
real-time version of the process.
