from occupational_health.services.retrieval.service import RetrievalService


class _Settings:
    recall_candidates = 50
    rrf_k = 60
    max_query_characters = 512
    max_top_k = 5


def _keys(condition_filter) -> list[str]:
    return [condition.key for condition in condition_filter.must]


def test_auto_scenario_ids_are_not_hard_filtered() -> None:
    service = RetrievalService(_Settings())
    result = service._build_filter({"scenario_ids": ["scene-1"]})
    keys = _keys(result)
    assert "category_id" not in keys
    assert "lifecycle_status" in keys


def test_include_replaced_disables_status_filter() -> None:
    service = RetrievalService(_Settings())
    result = service._build_filter({"include_replaced": True})
    assert "lifecycle_status" not in _keys(result)
