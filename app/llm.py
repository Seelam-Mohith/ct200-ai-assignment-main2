from pydantic import BaseModel, Field

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
