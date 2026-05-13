from typing import TypedDict


class ResearchState(TypedDict, total=False):
    topic: str
    research_notes: str
    draft: str
    feedback: str
    final_output: str
    revision_count: int
    approved: bool
