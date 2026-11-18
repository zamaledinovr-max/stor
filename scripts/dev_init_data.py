"""Generate a signed Mini App initData string for local browser testing.

The server still verifies the HMAC signature, so this is not an auth bypass: it
uses the real Telegram algorithm with your development bot token.

Usage (PowerShell):
    $env:TELEGRAM_BOT_TOKEN="123456:ABC..."; python scripts/dev_init_data.py --user-id 123456789

Paste the printed value into the browser console of the Mini App page:
    localStorage.setItem("dev_init_data", "<value>"); location.reload();
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode


def build_init_data(
    bot_token: str,
    user_id: int,
    *,
    username: str = "dev_user",
    first_name: str = "Dev",
    auth_date: int | None = None,
    ttl_seconds: int | None = None,
) -> str:
    timestamp = auth_date if auth_date is not None else int(time.time())
    if ttl_seconds is not None:
        timestamp = int(time.time()) - ttl_seconds
    user = {
        "id": user_id,
        "first_name": first_name,
        "username": username,
        "language_code": "ru",
    }
    fields = {
        "auth_date": str(timestamp),
        "query_id": f"AAH{user_id}",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--user-id", type=int, default=100000001)
    parser.add_argument("--username", default="dev_user")
    parser.add_argument("--first-name", default="Dev")
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=None,
        help="Generate auth_date in the past (for expiry tests)",
    )
    args = parser.parse_args()

    if not args.token:
        parser.error("Set TELEGRAM_BOT_TOKEN or pass --token")

    init_data = build_init_data(
        args.token,
        args.user_id,
        username=args.username,
        first_name=args.first_name,
        ttl_seconds=args.ttl_seconds,
    )
    print(init_data)
    print()
    print("Browser console snippet:")
    print(f'localStorage.setItem("dev_init_data", "{init_data}"); location.reload();')


if __name__ == "__main__":
    main()
