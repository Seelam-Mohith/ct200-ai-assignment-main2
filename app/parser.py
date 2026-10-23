"""CT-200 PDF -> hierarchy. Text-layer PDF, so PyMuPDF (no OCR needed; see APPROACH).
Heading = bold line whose text starts with a section number. Font SIZE is NOT used:
3.2 and 3.4 are bold at body size (11pt), so size-based detection would miss them.
Level comes from the number's depth (2.1.1.1 -> 4), parent from the nearest shallower
open heading, so skipped levels (2.1 -> 2.1.1.1) are parented to 2.1 and flagged."""
import hashlib, re, unicodedata
from dataclasses import dataclass, field
import pymupdf

HEAD = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
LIST = re.compile(r"^\d+\.\s")

def norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)  # ligatures ï¬/ï¬€/ï¬‚ -> fi/ff/fl
    t = t.replace("â€‘", "-").replace("â€", "-")  # non-breaking hyphen
    return re.sub(r"[ \t]+", " ", t).strip()

def content_hash(body: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", norm(body)).lower().encode()).hexdigest()

@dataclass
class Node:
    number: str; heading: str; level: int; page: int
    body_lines: list = field(default_factory=list)
    parent: "Node|None" = None
    children: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    path: str = ""
    @property
    def body(self): return "\n".join(self.body_lines).strip()
    @property
    def hash(self): return content_hash(self.body)

def _lines(doc):
    for pn, page in enumerate(doc, 1):
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                spans = l["spans"]
                text = norm("".join(s["text"] for s in spans))
                if text:
                    yield pn, text, all("Bold" in s["font"] for s in spans), spans[0]["size"], b["bbox"][0]

def parse(pdf_path: str):
    doc = pymupdf.open(pdf_path)
    root = Node("0", "<document>", 0, 1)
    stack, nodes, title, last = [root], [], [], None
    for pn, text, bold, size, _ in _lines(doc):
        m = HEAD.match(text)
        if size >= 20 and bold and not nodes:          # multi-line title
            title.append(text); continue
        if bold and m and not LIST.match(text) or (bold and m and size > 11.5):
            num, head = m.groups(); level = num.count(".") + 1
            while stack[-1].level >= level: stack.pop()
            parent = stack[-1]; n = Node(num, head, level, pn, parent=parent)
            parent.children.append(n); stack.append(n); nodes.append(n); last = n
            n.path = (parent.path + "/" if parent.path else "") + f"{num} {head}"
        elif nodes:
            nodes_cur = stack[-1]
            nodes_cur.body_lines.append(text)
    return " ".join(title), root, nodes
