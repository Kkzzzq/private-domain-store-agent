"""Explicit one-time snapshot transfer; credentials come from the local .env."""
import argparse
import base64
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import DateTime, Date, Numeric, select, text
from app.db.base import Base
from app.db.session import engine
import app.models.tables  # noqa: F401


def encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes": base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)


def digest(rows):
    ordered = sorted(json.dumps(row, default=encode, sort_keys=True, ensure_ascii=False) for row in rows)
    return hashlib.sha256("\n".join(ordered).encode()).hexdigest()


def snapshot(path):
    tables = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            for table in Base.metadata.sorted_tables:
                tables[table.name] = [dict(row) for row in conn.execute(select(table)).mappings()]
    payload = {"tables": tables, "hashes": {name: digest(rows) for name, rows in tables.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=encode, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({name: len(rows) for name, rows in tables.items()}))


def restore(path, preserve_passwords):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload["tables"]) != set(Base.metadata.tables):
        raise RuntimeError("Snapshot and application tables differ")
    for name, rows in payload["tables"].items():
        if digest(rows) != payload["hashes"][name]:
            raise RuntimeError("Snapshot checksum mismatch: " + name)
    Base.metadata.create_all(engine)
    preserved = {}
    if preserve_passwords:
        import sqlite3
        with sqlite3.connect(f"file:{preserve_passwords}?mode=ro", uri=True) as old:
            preserved = dict(old.execute("SELECT username,password_hash FROM users"))
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if conn.execute(select(table).limit(1)).first():
                raise RuntimeError("Destination must be empty: " + table.name)
        for table in Base.metadata.sorted_tables:
            rows = payload["tables"][table.name]
            for row in rows:
                for column in table.columns:
                    value = row.get(column.name)
                    if value is not None and isinstance(column.type, DateTime):
                        row[column.name] = datetime.fromisoformat(value)
                    elif value is not None and isinstance(column.type, Date):
                        row[column.name] = date.fromisoformat(value)
                if table.name == "users" and row["username"] in preserved:
                    row["password_hash"] = preserved[row["username"]]
            if rows:
                conn.execute(table.insert(), rows)
            actual = [dict(row) for row in conn.execute(select(table)).mappings()]
            if digest(actual) != digest(rows):
                raise RuntimeError("Destination content mismatch: " + table.name)
    print(json.dumps({"verified_tables": len(payload["tables"]), "preserved_server_passwords": len(preserved),
                      "counts": {name: len(rows) for name, rows in payload["tables"].items()}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--preserve-passwords", type=Path)
    args = parser.parse_args()
    if args.action == "export":
        snapshot(args.path)
    else:
        restore(args.path, args.preserve_passwords)
