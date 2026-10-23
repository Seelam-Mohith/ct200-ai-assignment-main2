"""Match nodes of a new version to the previous version.
1. exact path (number + heading, incl. ancestors)  -> same logical node
2. fuzzy heading (difflib >= 0.85) among still-unmatched old nodes, preferring
   the same parent logical id  -> survives renumbering
Known failure modes: split/merged sections, a heading reworded a lot, and two
sibling sections with near-identical headings (could be swapped)."""
import difflib, uuid

def match(prev: list[dict], new: list) -> dict:
    """prev: dicts with path, heading, logical_id, parent_logical. new: parser Nodes.
    Returns {new.path: (logical_id, method)}."""
    by_path = {p["path"]: p for p in prev}
    used, out = set(), {}
    for n in new:
        p = by_path.get(n.path)
        if p and p["logical_id"] not in used:
            used.add(p["logical_id"]); out[n.path] = (p["logical_id"], "path")
    for n in new:                                   # fuzzy pass
        if n.path in out: continue
        parent_l = out.get(n.parent.path, (None,))[0] if n.parent and n.parent.path else None
        cands = [p for p in prev if p["logical_id"] not in used]
        best, score = None, 0.0
        for p in cands:
            s = difflib.SequenceMatcher(None, n.heading.lower(), p["heading"].lower()).ratio()
            if p["parent_logical"] == parent_l: s += 0.05
            if s > score: best, score = p, s
        if best and score >= 0.85:
            used.add(best["logical_id"]); out[n.path] = (best["logical_id"], "fuzzy")
        else:
            out[n.path] = (uuid.uuid4().hex[:12], "new")
    return out
