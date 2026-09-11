#!/usr/bin/env python
"""Command-line migration runner entrypoint for production deployments."""

from __future__ import annotations

import argparse
import os
import sys

from agentlens.config import AgentLensSettings
from agentlens.logging import configure_logging
from agentlens.storage.migration_runner import downgrade_migrations, run_migrations


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentLens database migration runner")
    parser.add_argument(
        "action",
        choices=["upgrade", "downgrade"],
        default="upgrade",
        nargs="?",
        help="Action to perform (default: upgrade)",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Advisory lock acquisition timeout in seconds (default: 60.0)",
    )
    args = parser.parse_args()

    configure_logging(log_level="INFO", json_format=True)

    db_url = os.environ.get("AGENTLENS_DATABASE_URL")
    if not db_url:
        try:
            settings = AgentLensSettings.load_from_env()
            db_url = settings.database.url
        except Exception:
            db_url = "postgresql+psycopg://agentlens:agentlens@127.0.0.1:55432/agentlens"

    if args.action == "upgrade":
        run_migrations(db_url, target_revision=args.revision, timeout_seconds=args.timeout)
    elif args.action == "downgrade":
        downgrade_migrations(db_url, target_revision=args.revision)

    return 0


if __name__ == "__main__":
    sys.exit(main())
