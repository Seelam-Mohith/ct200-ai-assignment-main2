# CT-200 Manual API

A small FastAPI service that turns the CardioTrack CT-200 user manual into a
versioned section tree, lets you select sections, and generates QA test cases
from them with an LLM. When a new manual version is ingested, the API shows
which sections changed and whether existing test cases are stale.

## What it does

- Parses the PDF text layer into a section hierarchy (PyMuPDF, no OCR).
- Stores every manual version separately so old selections stay reproducible.
- Matches sections between versions by path, then by fuzzy heading.
- Generates 3-5 QA test cases from selected sections using Groq.
- Validates LLM output and retries on malformed JSON.
- Reports staleness for saved test cases after a new version is ingested.

## Project structure

    app/        FastAPI app, parser, models, version matching, LLM client
    data/       CT-200 manual v1 and v2 PDFs
    tests/      Parser, versioning, staleness and LLM tests
    APPROACH.md Design notes, trade-offs and known limits

## Requirements

- Python 3.10+
- A Groq API key (or use the offline mock provider)

## Setup

    python -m venv .venv
    .venv\Scripts\activate        # Windows
    # source .venv/bin/activate   # macOS / Linux
    pip install -r requirements.txt

Set the API key:

    set GROQ_API_KEY=your_key_here        # Windows
    export GROQ_API_KEY=your_key_here     # macOS / Linux

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `LLM_PROVIDER` | unset | Set to `mock` for offline demo/tests |
| `STORE_DIR` | `./store` | Where generated test cases are saved |

## Run

    uvicorn app.main:app --reload

Open http://localhost:8000/docs for the interactive API docs.

## Basic flow

1. Ingest the first manual:

       curl -X POST localhost:8000/ingest ^
         -H "content-type: application/json" ^
         -d "{\"pdf_path\":\"data/ct200_manual_v1.pdf\"}"

2. Find a section:

       curl "localhost:8000/search?q=Inflation&version=1"

3. Create a selection with the returned node id (for example 10):

       curl -X POST localhost:8000/selections ^
         -H "content-type: application/json" ^
         -d "{\"name\":\"inflation\",\"node_ids\":[10]}"

4. Generate test cases (later calls reuse the stored result):

       curl -X POST localhost:8000/selections/1/generate

5. Ingest the second manual and check staleness:

       curl -X POST localhost:8000/ingest ^
         -H "content-type: application/json" ^
         -d "{\"pdf_path\":\"data/ct200_manual_v2.pdf\"}"

       curl localhost:8000/selections/1/testcases

## Main endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/ingest` | Parse a PDF and create a new manual version |
| GET | `/versions` | List ingested versions |
| GET | `/sections` | List top-level sections |
| GET | `/nodes/{id}` | Get one section and its children |
| GET | `/search` | Search headings and body text |
| GET | `/nodes/{id}/changes` | Show changes across versions |
| POST | `/selections` | Create a selection of sections |
| POST | `/selections/{id}/generate` | Generate or reuse test cases |
| GET | `/selections/{id}/testcases` | List test cases with staleness |
| GET | `/nodes/{id}/testcases` | Test cases that cite a section |

## Tests

    python -m pytest -q

The LLM tests use the mock caller and do not make network requests.

## Notes

- `data/` must contain the PDFs used by the example commands.
- The staleness check is heuristic: numeric changes are critical, wording-only
  changes are minor. See `APPROACH.md` for details and limitations.