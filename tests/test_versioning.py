from types import SimpleNamespace as NS
from app.versioning import match
from app.staleness import classify
from app.llm import generate, parse_output
import json

def N(path, heading, parent=None): return NS(path=path, heading=heading, parent=parent)

def prev(path, heading, lid, pl=None): return dict(path=path, heading=heading, logical_id=lid, parent_logical=pl)

def test_path_match_keeps_logical_id():
    m = match([prev("3 Op/3.2 Cuff", "Cuff", "L1")], [N("3 Op/3.2 Cuff", "Cuff")])
    assert m["3 Op/3.2 Cuff"] == ("L1", "path")

def test_renumbered_section_survives_via_fuzzy():
    m = match([prev("3 Op/3.4 Auto Shutoff", "Auto Shutoff", "L9")], [N("3 Op/3.5 Auto Shutoff", "Auto Shutoff")])
    assert m["3 Op/3.5 Auto Shutoff"] == ("L9", "fuzzy")

def test_duplicate_headings_not_cross_matched():
    p = [prev("4/4.2 Error Codes", "Error Codes", "A"), prev("7/7.1 Error Codes", "Error Codes", "B")]
    m = match(p, [N("4/4.2 Error Codes", "Error Codes"), N("7/7.1 Error Codes", "Error Codes")])
    assert m["4/4.2 Error Codes"][0] == "A" and m["7/7.1 Error Codes"][0] == "B"

def test_number_change_is_critical_wording_is_minor():
    assert classify("30 mmHg steps", "h1", "40 mmHg steps", "h2")["severity"] == "critical"
    assert classify("device inflates cuff", "h1", "unit inflates cuff", "h2")["severity"] == "minor"
    assert classify("x", "h", "x", "h")["severity"] == "none"

def test_malformed_llm_output_retried_then_failed_not_returned():
    out, log = generate("[1] t", {"1"}, caller=lambda p: "sorry, here are some ideas...")
    assert out is None and len(log) == 3

def test_llm_recovers_on_retry_and_fenced_json_accepted():
    good = json.dumps({"test_cases": [dict(title="abc", source_sections=["1"], steps=["s"], expected_result="ok!") for _ in range(3)]})
    calls = iter(["not json", "```json\n" + good + "\n```"])
    out, log = generate("[1] t", {"1"}, caller=lambda p: next(calls))
    assert out and len(out.test_cases) == 3 and len(log) == 2

def test_hallucinated_section_rejected():
    bad = json.dumps({"test_cases": [dict(title="abc", source_sections=["9.9"], steps=["s"], expected_result="ok!") for _ in range(3)]})
    out, _ = generate("[1] t", {"1"}, caller=lambda p: bad)
    assert out is None
