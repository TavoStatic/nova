import sqlite3
from pathlib import Path


def main() -> int:
    db_path = Path(__file__).resolve().parents[2] / "runtime" / "_internal" / "work_tree.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "select name from sqlite_master where type='table' order by name"
        ).fetchall()
    finally:
        conn.close()
    print([r[0] for r in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
