import anthropic

from research_agent.state import ResearchState

MODEL = "claude-opus-4-7"
MAX_REVISIONS = 3

_client = anthropic.Anthropic()


def _extract_text(response: anthropic.types.Message) -> str:
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(parts).strip()


RESEARCHER_SYSTEM = (
    "You are a research analyst. Given a topic, produce structured notes with:\n"
    "- 5-8 key facts or findings (each one a single bullet)\n"
    "- 2-3 open questions worth deeper investigation\n"
    "- A short list of useful angles for an article on the topic\n"
    "Be concrete. No fluff, no preamble."
)


def researcher(state: ResearchState) -> dict:
    response = _client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=RESEARCHER_SYSTEM,
        messages=[{"role": "user", "content": f"Topic: {state['topic']}"}],
    )
    return {"research_notes": _extract_text(response)}


WRITER_SYSTEM = (
    "You are a writer producing clear, well-structured articles. "
    "Use the supplied research notes as your source of truth. "
    "If reviewer feedback is included, address every point. "
    "Output 400-600 words. No preamble - start with the article itself."
)


def writer(state: ResearchState) -> dict:
    feedback = state.get("feedback")
    revision = state.get("revision_count", 0)
    user_content = (
        f"Topic: {state['topic']}\n\n"
        f"Research notes:\n{state['research_notes']}"
    )
    if feedback and revision > 0:
        user_content += f"\n\nReviewer feedback to address:\n{feedback}"

    response = _client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=WRITER_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    return {
        "draft": _extract_text(response),
        "revision_count": revision + 1,
    }


REVIEWER_SYSTEM = (
    "You are a strict editor. Evaluate the draft against the research notes for "
    "accuracy, clarity, structure, and completeness. Respond in exactly this format:\n\n"
    "VERDICT: APPROVE\n"
    "or\n"
    "VERDICT: REVISE\n"
    "FEEDBACK:\n"
    "- <specific, actionable point>\n"
    "- <specific, actionable point>\n\n"
    "Approve only if the draft is publishable as-is. Otherwise REVISE with concrete fixes."
)


def reviewer(state: ResearchState) -> dict:
    user_content = (
        f"Topic: {state['topic']}\n\n"
        f"Research notes:\n{state['research_notes']}\n\n"
        f"Draft:\n{state['draft']}"
    )
    response = _client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=REVIEWER_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text = _extract_text(response)
    approved = text.upper().startswith("VERDICT: APPROVE")
    update: ResearchState = {"feedback": text, "approved": approved}
    if approved or state.get("revision_count", 0) >= MAX_REVISIONS:
        update["final_output"] = state["draft"]
    return update


def route_after_review(state: ResearchState) -> str:
    if state.get("approved") or state.get("revision_count", 0) >= MAX_REVISIONS:
        return "end"
    return "writer"
