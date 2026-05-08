import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from src.graph import build_graph  # noqa: E402


def main() -> None:
    graph = build_graph(
        llm=FakeListChatModel(responses=["{}"]),
        search_fn=lambda q: [],
    )
    print("=== Mermaid ===")
    print(graph.get_graph().draw_mermaid())
    try:
        print("\n=== ASCII ===")
        print(graph.get_graph().draw_ascii())
    except ImportError:
        print("(install grandalf for ASCII: `uv add --dev grandalf`)")


if __name__ == "__main__":
    main()
