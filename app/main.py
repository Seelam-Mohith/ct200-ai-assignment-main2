import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import *
from .parser import parse
from .versioning import match

app = FastAPI(title="CT-200 manual API")
init_db()

def db():
    with SessionLocal() as s: yield s

def latest_version(s, name=None) -> Version:
    v = s.scalars(select(Version).order_by(Version.id.desc())).first()
    if not v: raise HTTPException(404, "nothing ingested yet")
    return v

def get_version(s, number: int | None) -> Version:
    if number is None: return latest_version(s)
    v = s.scalars(select(Version).where(Version.number == number)).first()
    if not v: raise HTTPException(404, f"version {number} not found")
    return v

def node_out(n: Node, children=None, full=True):
    d = dict(id=n.id, version_id=n.version_id, logical_id=n.logical_id, number=n.number,
             heading=n.heading, level=n.level, path=n.path, parent_id=n.parent_id,
             hash=n.hash, warnings=n.warnings, match_method=n.match_method)
    if full: d["body"] = n.body
    if children is not None: d["children"] = [node_out(c, full=False) for c in children]
    return d

# ---------- ingestion ----------
class IngestIn(BaseModel):
    document: str = "ct200"
    pdf_path: str            # must live under data/

@app.post("/ingest")
def ingest(body: IngestIn, s: Session = Depends(db)):
    path = os.path.normpath(body.pdf_path)
    if not path.startswith("data" + os.sep) or not os.path.isfile(path):
        raise HTTPException(400, "pdf_path must be an existing file under data/")
    title, root, nodes = parse(path)
    doc = s.scalars(select(Document).where(Document.name == body.document)).first()
    if not doc: doc = Document(name=body.document); s.add(doc); s.flush()
    prev_v = s.scalars(select(Version).where(Version.document_id == doc.id).order_by(Version.number.desc())).first()
    prev = []
    if prev_v:
        rows = s.scalars(select(Node).where(Node.version_id == prev_v.id)).all()
        lid = {r.id: r.logical_id for r in rows}
        prev = [dict(path=r.path, heading=r.heading, logical_id=r.logical_id,
                     parent_logical=lid.get(r.parent_id)) for r in rows]
    m = match(prev, nodes)
    v = Version(document_id=doc.id, number=(prev_v.number + 1) if prev_v else 1, title=title)
    s.add(v); s.flush()
    ids = {}
    for n in nodes:                         # parents always precede children in doc order
        logical, method = m[n.path]
        row = Node(version_id=v.id, logical_id=logical, number=n.number, heading=n.heading,
                   level=n.level, path=n.path, page=n.page, body=n.body, hash=n.hash,
                   warnings=n.warnings, match_method=method,
                   parent_id=ids.get(id(n.parent)))
        s.add(row); s.flush(); ids[id(n)] = row.id
    s.commit()
    prev_hash = {}
    if prev_v:
        prev_hash = {r.logical_id: r.hash for r in s.scalars(select(Node).where(Node.version_id == prev_v.id))}
    rows = s.scalars(select(Node).where(Node.version_id == v.id)).all()
    return dict(version=v.number, nodes=len(rows),
                new=[r.number for r in rows if r.match_method == "new" and prev_v],
                changed=[r.number for r in rows if r.logical_id in prev_hash and prev_hash[r.logical_id] != r.hash],
                fuzzy_matched=[r.number for r in rows if r.match_method == "fuzzy"],
                warnings={r.number: r.warnings for r in rows if r.warnings})
