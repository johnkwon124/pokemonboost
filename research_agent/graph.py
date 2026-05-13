from langgraph.graph import END, START, StateGraph

from research_agent.agents import researcher, reviewer, route_after_review, writer
from research_agent.state import ResearchState


def build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("researcher", researcher)
    graph.add_node("writer", writer)
    graph.add_node("reviewer", reviewer)

    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"writer": "writer", "end": END},
    )

    return graph.compile()
