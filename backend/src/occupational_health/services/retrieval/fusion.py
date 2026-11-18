from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    chunk_id: str
    score: float
    rank: int


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    for index, ranked in enumerate(ranked_lists):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            sources.setdefault(chunk_id, set()).add(index)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
