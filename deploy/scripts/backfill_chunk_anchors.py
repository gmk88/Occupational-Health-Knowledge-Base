"""Rebuild text-level source anchors for all existing chunks."""

from occupational_health.services.retrieval.anchors import rebuild_all_chunk_anchors


def main() -> None:
    count = rebuild_all_chunk_anchors()
    print(f"rebuilt chunk anchors: {count}")


if __name__ == "__main__":
    main()
