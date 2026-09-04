"""Reset the local dev database to a clean slate: drops everything and
re-runs all Alembic migrations from scratch. Optionally re-seeds demo data
(seed/seed.py) afterward.

Only ever targets DATABASE_URL from .env (the dev database) -- never the
test database, which pytest already resets per-run on its own.

Usage (from the project root):
    uv run python scripts/reset_db.py            # reset only
    uv run python scripts/reset_db.py --seed      # reset + seed demo data
    uv run python scripts/reset_db.py --yes       # skip the confirmation prompt
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Without this, our own print()s can get buffered and appear out of order
# relative to the (unbuffered) subprocess output from alembic/seed.py when
# stdout isn't a TTY (e.g. piped or captured).
sys.stdout.reconfigure(line_buffering=True)

from app.config import get_settings  # noqa: E402


def reset_schema(database_url: str) -> None:
    # psycopg needs a plain postgresql:// URL, not SQLAlchemy's +psycopg dialect suffix.
    conn = psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://"))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE")
            cur.execute("CREATE SCHEMA public")
    finally:
        conn.close()


def run_migrations() -> None:
    subprocess.run(
        ["uv", "run", "alembic", "-c", "database/alembic.ini", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def run_seed() -> None:
    subprocess.run(
        ["uv", "run", "python", "seed/seed.py"],
        cwd=PROJECT_ROOT,
        check=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", action="store_true", help="Re-seed demo data after resetting")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    database_url = get_settings().database_url

    print(f"This will DROP ALL DATA in: {database_url}")
    if not args.yes:
        confirm = input("Type 'reset' to continue: ")
        if confirm != "reset":
            print("Aborted.")
            return

    print("Dropping and recreating schema...")
    reset_schema(database_url)

    print("Running migrations...")
    run_migrations()

    if args.seed:
        print("Seeding demo data...")
        run_seed()

    print("Done.")


if __name__ == "__main__":
    main()
