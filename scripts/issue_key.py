"""Mint an API key for a user. There is no signup page yet.

    python scripts/issue_key.py you@example.com
    python scripts/issue_key.py you@example.com --plan pro

The raw key is printed ONCE and never stored -- only its sha256 hash goes to
the database. Copy it immediately; it cannot be recovered.
"""

import argparse
import asyncio
import sys

from callyr import config
from callyr.auth.keys import generate_key, hash_key, key_prefix
from callyr.db.client import get_client


async def issue(email: str, plan: str) -> int:
    client = await get_client()
    if client is None:
        print("error: Supabase is not configured. Check SUPABASE_URL and", file=sys.stderr)
        print("       SUPABASE_SERVICE_KEY (must be the service role key).", file=sys.stderr)
        return 1

    raw = generate_key()
    try:
        result = (
            await client.table("users")
            .insert(
                {
                    "email": email,
                    "api_key_hash": hash_key(raw),
                    "key_prefix": key_prefix(raw),
                    "plan": plan,
                }
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to an operator, not a user
        print(f"error: could not create user: {exc}", file=sys.stderr)
        return 1

    user_id = result.data[0]["id"] if result.data else "?"
    print(f"user id : {user_id}")
    print(f"email   : {email}")
    print(f"plan    : {plan}")
    print()
    print("Connector URL (paste into the AI app's MCP settings):")
    print("  https://usecue.online/mcp")
    print()
    print("Add this header in the connector settings:")
    print(f"  Authorization: Bearer {raw}")
    print()
    print("This key is shown once and is not recoverable.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a Cue API key.")
    parser.add_argument("email")
    parser.add_argument("--plan", choices=["free", "pro"], default="free")
    args = parser.parse_args()

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        print("error: SUPABASE_URL / SUPABASE_SERVICE_KEY not set.", file=sys.stderr)
        return 1

    return asyncio.run(issue(args.email, args.plan))


if __name__ == "__main__":
    raise SystemExit(main())
