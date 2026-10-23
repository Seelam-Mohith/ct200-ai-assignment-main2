import re
NUM = re.compile(r"\d+(?:\.\d+)?")

def numbers(t: str) -> list[str]: return sorted(NUM.findall(t))

def classify(old_body: str, old_hash: str, cur_body: str | None, cur_hash: str | None) -> dict:
    if cur_hash is None: return {"status": "source_removed", "severity": "critical"}
    if cur_hash == old_hash: return {"status": "fresh", "severity": "none"}
    if numbers(old_body) != numbers(cur_body):
        return {"status": "stale", "severity": "critical",
                "reason": "numeric values changed",
                "numbers_before": numbers(old_body), "numbers_after": numbers(cur_body)}
    return {"status": "stale", "severity": "minor",
            "reason": "wording changed, numbers identical (NOT verified semantically: "
                      "a negation or unit change would also land here)"}

def worst(items: list[dict]) -> str:
    order = {"none": 0, "minor": 1, "critical": 2}
    return max((i["severity"] for i in items), key=order.get, default="none")
