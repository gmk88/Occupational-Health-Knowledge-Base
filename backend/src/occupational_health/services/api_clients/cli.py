from __future__ import annotations

import argparse

from occupational_health.services.api_clients.service import ApiClientService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an API client and a one-time key."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--scopes", required=True, help="comma-separated scopes")
    args = parser.parse_args()
    scopes = [scope.strip() for scope in args.scopes.split(",") if scope.strip()]
    client, key = ApiClientService().create_client(args.name, scopes)
    print(f"client_id: {client['id']}")
    print(f"api_key (shown once): {key}")


if __name__ == "__main__":
    main()
