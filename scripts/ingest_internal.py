import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.internal_rag.ingest import ingest  # noqa: E402
from src.internal_rag.vector_store import collection_stats  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest internal documents into the local Chroma store.")
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help="Source name (repeatable). Defaults to ['wiki']. Available: wiki",
    )
    parser.add_argument("--reset", action="store_true", help="Drop the whole collection before ingesting")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only sync documents modified after the last successful sync",
    )
    parser.add_argument("--stats", action="store_true", help="Only print current collection stats")
    args = parser.parse_args()

    if args.stats:
        print(json.dumps(collection_stats(), indent=2))
        return

    sources = args.source or ["wiki"]
    print(f"Ingesting sources: {sources} (reset={args.reset}, incremental={args.incremental})")
    stats = ingest(sources=sources, reset=args.reset, incremental=args.incremental)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print("\nCollection stats:", json.dumps(collection_stats(), indent=2))


if __name__ == "__main__":
    main()
