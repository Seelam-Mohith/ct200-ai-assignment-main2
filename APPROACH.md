# Approach document — CT-200 manual API

## 1. Parsing approach
The CT-200 PDF has a real text layer, so no OCR is needed. I used PyMuPDF (`get_text("dict")`), which gives per-span font name and size. OCR (Tesseract) would add errors on a clean text PDF; it would only be justified for scanned input (not handled, see decision log).

## 2. Hierarchy reconstruction
A line is a heading if it is **bold AND starts with a section number** (`^\d+(\.\d+)*\.?\s`). Level = number of dots + 1. Parent = nearest shallower open heading (stack). Text between headings goes to the current node's body. Tree rows store heading, level, body, parent_id, path, page and a SHA-256 content hash of the normalised body.

## 3. Irregularities found and how each is handled
| Irregularity | Handling |
|---|---|
| 3.2 / 3.4 headings are bold at body size (11pt) | Font size is not used; bold + number is. Test: `test_bold_body_size_headings_detected` |
| Skipped level 2.1 -> 2.1.1.1 | Parented to 2.1, `skipped_level` warning stored |
| 3.4 appears before 3.3 | Document order kept, `out_of_order` warning, both parented to 3 |
| Duplicate heading "Error Codes" (4.2, 7.1) | Path includes number + ancestors, so two distinct nodes with correct parents |
| Numbered list in 3.3 ("1. Normal…") looks like a heading | Not bold, so treated as body |
| Title split over 3 lines | Joined |
| Sections continuing across pages (4.3), heading at page bottom (3.1) | Page boundaries ignored; text attaches to the open node |
| Table in 4.2 | Kept as flat text in the body, flagged `table_present` (cells not structured) |
| Ligatures (ﬁ, ﬀ) and non-breaking hyphens | NFKC + hyphen normalisation before hashing, so hashes are stable |
Tests: `tests/test_parser.py` (9 tests).

## 4. What failed first / how I found it
First idea was font-size based heading detection; inspecting spans showed 3.2 and 3.4 at 11pt, so they were silently merged into the previous section's body. Found by dumping font size/name per line and comparing against the page text. Fix: bold + numbering. Validation since: parser `warnings` list and unit tests.

## 5. Data model
SQLite via SQLAlchemy: Document, Version, Node, Selection, SelectionItem. **Node rows are per version and never updated**, so a node id is already a (node, version) pin. `logical_id` links "the same section" across versions. SelectionItem references node rows, so old selections always resolve to the exact original text. LLM output is stored as one JSON file per generation (see section 8).

## 6. Version matching strategy
1. Exact `path` (ancestors + number + heading) -> same logical_id.
2. Otherwise fuzzy heading match (difflib >= 0.85) among still-unmatched old nodes, small bonus for same parent.
3. Otherwise new logical node.
Changed = same logical_id, different hash.
**Where it breaks:** a section split or merged between versions; a heavily reworded heading; two sibling sections with near-identical headings could be swapped by the fuzzy pass; a section moved under a different parent with a changed heading is treated as new.

## 7. LLM prompt, validation and retries
Prompt gives only the selected text, asks for 3–5 test cases using exact values from the text, citing source section numbers, JSON only. Output is validated with Pydantic (3–5 cases, required fields, `source_sections` must be within the selection, markdown fences stripped). On invalid output: retry up to 3 attempts total, feeding the validation error back. If still invalid, a `failed` record is stored and nothing partial is shown as test cases — wrong QA cases for a medical device are worse than none.
**Duplicate submissions:** same selection + same node hashes -> the stored successful generation is returned without an LLM call; `?force=true` makes a new one. Reason: avoids cost and non-deterministic duplicates; the content key means a changed document naturally yields a new generation.

## 8. Storage for LLM output
JSON file per generation instead of MongoDB: zero setup, access is only by id/selection, output is schemaless. Each generation stores a snapshot of the source nodes (node id, logical_id, hash, text), so it survives re-versioning.

## 9. Staleness
At retrieval, each source's stored hash is compared with the latest version's node having the same logical_id. Result per source: fresh / stale-minor / stale-critical / source_removed, rolled up per test case via its cited sections and per generation. Critical = the set of numbers in the section changed; minor = wording only.
**Limits:** it is a heuristic. A negation ("must not"), a unit change, or a changed condition with identical numbers is reported as minor. A harmless number change (e.g. a page reference) is reported critical. It compares whole sections, not the specific sentence a test case relied on.

## 10. Decision log
1. **Most likely silent wrong result:**  — a heading the parser fails to recognise is merged into the previous node's body with no error; the output looks clean but the hierarchy is wrong. Caught by the `warnings` list, the heading-count/numbering-sequence checks and parser unit tests.
2. **Simplicity over correctness:**  —  staleness compares numbers only, so a negation flips meaning but is labelled minor; this breaks first in production. Also flat-text tables and a JSON-file store without locking.
3. **Input not handled:**  —  scanned/image-only PDFs: the parser finds no text and produces an empty tree (should fail loudly); also a table cell structure and a section split across versions.

## 11. What I'd do with more time
Per-sentence/claim-level traceability instead of per-section; table extraction into rows; a semantic (LLM or NLI) check for staleness; file locking or Mongo; OCR fallback with an explicit "unsupported" error; API integration tests.
