"""Rotate an API client key and print the new raw key once."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sqlalchemy import select  # noqa: E402

from occupational_health.db.models.api_client import APIClient  # noqa: E402
from occupational_health.db.session import SessionLocal  # noqa: E402
from occupational_health.services.api_clients.service import ApiClientService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotate MCP/API client key")
    parser.add_argument("--client-id", help="Client UUID")
    parser.add_argument("--name", help="Client name (exact match)")
    parser.add_argument("--output", help="Write new key to this file")
    args = parser.parse_args()
    if not args.client_id and not args.name:
        parser.error("provide --client-id or --name")

    with SessionLocal() as db:
        if args.client_id:
            client_id = uuid.UUID(args.client_id)
        else:
            client = db.scalar(select(APIClient).where(APIClient.name == args.name))
            if not client:
                raise SystemExit(f"client not found: {args.name}")
            client_id = client.id

    result = ApiClientService().rotate_key(client_id)
    raw_key = result["key"]
    if args.output:
        Path(args.output).write_text(raw_key, encoding="ascii")
        print(f"rotated {client_id}; key written to {args.output}")
    else:
        print(f"rotated {client_id}")
        print(raw_key)


if __name__ == "__main__":
    main()
