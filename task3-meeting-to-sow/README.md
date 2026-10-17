@'
# Meeting-to-SOW

A FastAPI application that analyzes meeting transcripts and generates draft Statements of Work (SOWs), with human approval and SQLite persistence.

## Features

- Extracts scope, deliverables, assumptions, exclusions, and open questions.
- Preserves source transcript text for traceability.
- Generates draft SOWs requiring human review.
- Stores SOWs in SQLite so records survive application restarts.
- Supports retrieving and approving SOWs.
- Prevents repeated approval of an already-approved SOW.
- Includes automated API tests.

## Technology Stack

- Python
- FastAPI
- SQLite
- Pydantic
- Pytest

## Setup

Create and activate a virtual environment if you do not already have one.

Install dependencies:

```bash
pip install -r requirements.txt