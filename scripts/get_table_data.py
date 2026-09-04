"""Print the rows of a given table in the local dev database.

Usage (from the project root):
    uv run python scripts/get_table_data.py tenants
    uv run python scripts/get_table_data.py tenants --limit 50
    uv run python scripts/get_table_data.py tenants --test   # target the test DB instead
    uv run python scripts/get_table_data.py --list           # list all table names
"""

import argparse
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.core.config import get_settings  # noqa: E402


def _connect(database_url: str) -> psycopg.Connection:
    # psycopg needs a plain postgresql:// URL, not SQLAlchemy's +psycopg dialect suffix.
    return psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://"))


def list_tables(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY 1")
        return [row[0] for row in cur.fetchall()]


def _table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
            (table_name,),
        )
        return cur.fetchone() is not None


def print_table(conn: psycopg.Connection, table_name: str, limit: int) -> None:
    if not _table_exists(conn, table_name):
        print(f"No such table '{table_name}'. Available tables:")
        for name in list_tables(conn):
            print(f"  {name}")
        sys.exit(1)

    with conn.cursor() as cur:
        # table_name is validated against information_schema above, so this
        # interpolation can't be used for injection -- psycopg can't
        # parameterize identifiers, only values.
        cur.execute(f'SELECT * FROM "{table_name}" LIMIT %s', (limit,))
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    if not rows:
        print(f"'{table_name}' is empty.")
        return

    widths = [max(len(col), *(len(str(row[i])) for row in rows)) for i, col in enumerate(columns)]
    header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    print(header)
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row)))
    print(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''}{' -- limit reached, more may exist' if len(rows) == limit else ''})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("table_name", nargs="?", help="Name of the table to print")
    parser.add_argument("--limit", type=int, default=100, help="Max rows to print (default: 100)")
    parser.add_argument("--test", action="store_true", help="Target the test database instead of the dev database")
    parser.add_argument("--list", action="store_true", help="List all table names and exit")
    args = parser.parse_args()

    if not args.list and not args.table_name:
        parser.error("table_name is required unless --list is given")

    settings = get_settings()
    database_url = settings.test_database_url if args.test else settings.database_url

    conn = _connect(database_url)
    try:
        if args.list:
            for name in list_tables(conn):
                print(name)
        else:
            print_table(conn, args.table_name, args.limit)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
