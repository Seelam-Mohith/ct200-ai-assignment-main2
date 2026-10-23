from pydantic import BaseModel, Field

class TestCase(BaseModel):
    title: str = Field(min_length=3)
    source_sections: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=3)

class TestCaseSet(BaseModel):
    test_cases: list[TestCase] = Field(min_length=3, max_length=5)
