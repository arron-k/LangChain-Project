from src.state import ResearchState


def hello_node(state: ResearchState) -> dict:
    topic = state.get("topic", "")
    return {"message": f"Hello, LangGraph! topic={topic}"}
