# CT-200 manual API

FastAPI + SQLAlchemy/SQLite (tree, versions, selections) + JSON-file store (LLM output).

## Setup
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    export GROQ_API_KEY=...          # free key from console.groq.com
    # optional: LLM_MODEL (default llama-3.3-70b-versatile), STORE_DIR (default ./store)
    # LLM_PROVIDER=mock  -> offline fake LLM for demos/tests
    uvicorn app.main:app --reload

Put the PDFs in `data/` (`ct200_manual_v1.pdf`, `ct200_manual_v2.pdf`).

## Tests
    python -m pytest -q

## v1 -> v2 flow (curl)
    curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{"pdf_path":"data/ct200_manual_v1.pdf"}'
    curl "localhost:8000/search?q=Inflation&version=1"            # note node id, e.g. 10
    curl -X POST localhost:8000/selections -H 'content-type: application/json' -d '{"name":"inflation","node_ids":[10]}'
    curl -X POST localhost:8000/selections/1/generate              # 3-5 test cases; 2nd call returns stored result
    curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{"pdf_path":"data/ct200_manual_v2.pdf"}'   # response lists changed/new nodes
    curl localhost:8000/selections/1/testcases                     # now shows staleness per test case
    curl localhost:8000/nodes/10/changes                           # diff summary v1 -> v2
    curl localhost:8000/nodes/10/testcases

Other: `GET /versions`, `GET /sections?version=`, `GET /nodes/{id}`, `GET /search?q=`.
Docs UI: http://localhost:8000/docs
