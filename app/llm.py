import json, os, re
import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

class TestCase(BaseModel):
    title: str = Field(min_length=3)
    source_sections: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=3)

class TestCaseSet(BaseModel):
    test_cases: list[TestCase] = Field(min_length=3, max_length=5)

PROMPT = """You are a QA engineer for a medical device (blood pressure monitor).
From ONLY the manual excerpts below, write 3 to 5 concrete, repeatable QA test cases.
Use exact values (pressures, times, codes) from the text; never invent values.
Each test case must cite the section number(s) it comes from in "source_sections".
Respond with JSON only, no markdown, in exactly this shape:
{{"test_cases":[{{"title":"...","source_sections":["3.2"],"steps":["..."],"expected_result":"..."}}]}}

EXCERPTS:
{text}
"""

def call_llm(prompt: str) -> str:
    if os.environ.get("LLM_PROVIDER") == "mock":
        nums = re.findall(r"^\[(\S+)\]", prompt, re.M)
        s = nums[0] if nums else "1"
        return json.dumps({"test_cases": [{"title": f"Mock case {i}", "source_sections": [s],
                "steps": ["do x"], "expected_result": "y happens"} for i in range(3)]})
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=60,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={"model": os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
              "messages": [{"role": "user", "content": prompt}], "temperature": 0.2,
              "response_format": {"type": "json_object"}})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def parse_output(raw: str) -> TestCaseSet:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    return TestCaseSet.model_validate_json(raw)

def generate(text: str, valid_sections: set[str], max_attempts: int = 3, caller=call_llm):
    """Returns (TestCaseSet|None, attempts_log). Never returns unvalidated output.
    Retries re-prompt with the validation error. After max_attempts -> None (caller
    stores a 'failed' record; we do NOT return partial/garbage test cases)."""
    log, prompt = [], PROMPT.format(text=text)
    for i in range(1, max_attempts + 1):
        try:
            raw = caller(prompt)
            out = parse_output(raw)
            bad = {s for tc in out.test_cases for s in tc.source_sections} - valid_sections
            if bad: raise ValueError(f"source_sections not in selection: {sorted(bad)}")
            log.append({"attempt": i, "ok": True}); return out, log
        except (ValidationError, ValueError, KeyError, httpx.HTTPError) as e:
            log.append({"attempt": i, "ok": False, "error": str(e)[:300]})
            prompt = PROMPT.format(text=text) + f"\nYour previous answer was invalid: {str(e)[:300]}\nReturn corrected JSON only."
    return None, log
