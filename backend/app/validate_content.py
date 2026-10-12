"""Validate the bundled content locally; optionally compare it with the database."""

import argparse
import json

from sqlalchemy import inspect

from app.content_quality import (
    content_counts,
    validate_content_quality,
    validate_seeded_records,
)
from app.db import SessionLocal
from app.seed_content import load_content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-db",
        action="store_true",
        help="also verify the content has been seeded and belongs to the expected course",
    )
    args = parser.parse_args()
    content = load_content()
    validate_content_quality(content)
    report = content_counts(content)
    if args.check_db:
        with SessionLocal() as db:
            if not inspect(db.get_bind()).has_table("courses"):
                parser.error("database schema is missing; apply migrations first")
            validate_seeded_records(db, content)
        report["database"] = "matches authored content"
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
