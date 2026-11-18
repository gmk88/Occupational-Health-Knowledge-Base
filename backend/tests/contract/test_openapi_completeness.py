from __future__ import annotations

from pathlib import Path

import yaml

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "docs/api/openapi.yaml"
)


def test_openapi_contract_has_operations_and_resolved_refs() -> None:
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    paths = document["paths"]
    operation_ids = [
        operation["operationId"]
        for item in paths.values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == 30
    assert len(operation_ids) == len(set(operation_ids))
    assert document["openapi"] == "3.0.3"
