"""Lab 4 扩展位置。核验者用独立 messages，但共享 episode 请求/费用预算。"""
from typing import Protocol

class Verifier(Protocol):
    def review(self, *, original_task: dict, evidence: list[dict], proposal: dict) -> dict: ...
