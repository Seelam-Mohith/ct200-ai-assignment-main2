"""JSON-file document store for LLM output (one file per generation).
Chosen over Mongo: zero setup, output is schemaless and read-by-key only."""
import json, os, uuid
DIR = os.environ.get("STORE_DIR", "store")

def _p(i): return os.path.join(DIR, f"{i}.json")
def save(doc: dict) -> dict:
    os.makedirs(DIR, exist_ok=True)
    doc.setdefault("id", uuid.uuid4().hex[:12])
    with open(_p(doc["id"]), "w") as f: json.dump(doc, f, indent=2)
    return doc
def all_docs() -> list[dict]:
    if not os.path.isdir(DIR): return []
    return [json.load(open(os.path.join(DIR, f))) for f in sorted(os.listdir(DIR)) if f.endswith(".json")]
