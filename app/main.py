import difflib, hashlib, os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from . import store
from .llm import generate
from .models import *
from .parser import parse
from .staleness import classify, worst, numbers
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

# ---------- browse ----------
@app.get("/versions")
def versions(s: Session = Depends(db)):
    return [dict(number=v.number, id=v.id, created=v.created) for v in s.scalars(select(Version))]

@app.get("/sections")
def sections(version: int | None = None, s: Session = Depends(db)):
    v = get_version(s, version)
    rows = s.scalars(select(Node).where(Node.version_id == v.id, Node.parent_id.is_(None)).order_by(Node.id)).all()
    return dict(version=v.number, sections=[node_out(r, full=False) for r in rows])

@app.get("/nodes/{node_id}")
def get_node(node_id: int, s: Session = Depends(db)):
    n = s.get(Node, node_id)
    if not n: raise HTTPException(404)
    kids = s.scalars(select(Node).where(Node.parent_id == n.id).order_by(Node.id)).all()
    return node_out(n, kids)

@app.get("/search")
def search(q: str, version: int | None = None, s: Session = Depends(db)):
    v = get_version(s, version); like = f"%{q}%"
    rows = s.scalars(select(Node).where(Node.version_id == v.id,
            or_(Node.heading.ilike(like), Node.body.ilike(like))).order_by(Node.id)).all()
    return dict(version=v.number, results=[node_out(r, full=False) for r in rows])

def _summ(old: str, new: str):
    d = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
         if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return dict(lines_removed=[l[1:] for l in d if l[0] == "-"][:5],
                lines_added=[l[1:] for l in d if l[0] == "+"][:5],
                numbers_before=numbers(old), numbers_after=numbers(new))

@app.get("/nodes/{node_id}/changes")
def changes(node_id: int, s: Session = Depends(db)):
    n = s.get(Node, node_id)
    if not n: raise HTTPException(404)
    hist = s.execute(select(Node, Version.number).join(Version, Version.id == Node.version_id)
                     .where(Node.logical_id == n.logical_id).order_by(Version.number)).all()
    out, prev = [], None
    for node, vn in hist:
        e = dict(version=vn, node_id=node.id, hash=node.hash, changed_from_previous=False)
        if prev and prev.hash != node.hash:
            e.update(changed_from_previous=True, diff=_summ(prev.body, node.body))
        out.append(e); prev = node
    return dict(logical_id=n.logical_id, changed_ever=any(e["changed_from_previous"] for e in out), versions=out)

# ---------- selections ----------
class SelIn(BaseModel):
    name: str
    node_ids: list[int]

@app.post("/selections", status_code=201)
def create_sel(b: SelIn, s: Session = Depends(db)):
    if not b.node_ids: raise HTTPException(422, "empty selection")
    for i in set(b.node_ids):
        if not s.get(Node, i): raise HTTPException(404, f"node {i} not found")
    sel = Selection(name=b.name, items=[SelectionItem(node_id=i) for i in sorted(set(b.node_ids))])
    s.add(sel); s.commit()
    return dict(id=sel.id, name=sel.name, node_ids=sorted(set(b.node_ids)))

def _sel_nodes(s, sid):
    sel = s.get(Selection, sid)
    if not sel: raise HTTPException(404, "selection not found")
    return sel, [s.get(Node, it.node_id) for it in sel.items]

# ---------- generation ----------
def _key(nodes): return hashlib.sha256("|".join(sorted(n.hash for n in nodes)).encode()).hexdigest()

@app.post("/selections/{sid}/generate")
def gen(sid: int, force: bool = False, s: Session = Depends(db)):
    """Policy: same selection content (same set of node hashes) => return the stored
    successful generation; no LLM call. ?force=true creates a new one. Failed
    generations never block a retry."""
    sel, nodes = _sel_nodes(s, sid)
    key = _key(nodes)
    if not force:
        for g in store.all_docs():
            if g["selection_id"] == sid and g["content_key"] == key and g["status"] == "ok":
                return _view(s, g) | {"reused": True}
    text = "\n\n".join(f"[{n.number}] {n.heading}\n{n.body}" for n in nodes)
    result, log = generate(text, {n.number for n in nodes})
    g = dict(selection_id=sid, content_key=key, attempts=log,
             status="ok" if result else "failed",
             test_cases=[t.model_dump() for t in result.test_cases] if result else [],
             sources=[dict(node_id=n.id, logical_id=n.logical_id, number=n.number,
                           hash=n.hash, body_snapshot=n.body) for n in nodes])
    store.save(g)
    return _view(s, g) | {"reused": False}

def _view(s: Session, g: dict) -> dict:
    """Retrieval-time staleness: compare each source's hash with the LATEST version's
    node that shares its logical_id."""
    lv = latest_version(s)
    per = {}
    for src in g["sources"]:
        cur = s.scalars(select(Node).where(Node.version_id == lv.id, Node.logical_id == src["logical_id"])).first()
        per[src["number"]] = classify(src["body_snapshot"], src["hash"], cur.body if cur else None,
                                      cur.hash if cur else None) | {"current_node_id": cur.id if cur else None}
    tcs = []
    for tc in g["test_cases"]:
        refs = [per[x] for x in tc["source_sections"] if x in per] or list(per.values())
        sev = worst(refs)
        tcs.append(tc | {"staleness": "fresh" if sev == "none" else "stale", "severity": sev})
    return dict(id=g["id"], selection_id=g["selection_id"], status=g["status"], attempts=g["attempts"],
                overall_severity=worst(list(per.values())), source_status=per, test_cases=tcs,
                latest_version=lv.number)

@app.get("/selections/{sid}/testcases")
def sel_tc(sid: int, s: Session = Depends(db)):
    _sel_nodes(s, sid)
    return [_view(s, g) for g in store.all_docs() if g["selection_id"] == sid]

@app.get("/nodes/{node_id}/testcases")
def node_tc(node_id: int, s: Session = Depends(db)):
    n = s.get(Node, node_id)
    if not n: raise HTTPException(404)
    return [_view(s, g) for g in store.all_docs()
            if any(x["logical_id"] == n.logical_id for x in g["sources"])]
