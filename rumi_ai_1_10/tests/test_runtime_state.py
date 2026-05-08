from __future__ import annotations

from core_runtime.runtime_state import (
    append_jsonl,
    atomic_write_json,
    read_tail_jsonl,
    run_migrations,
    sqlite_wal_connection,
)


def test_atomic_write_json_and_jsonl_tail(tmp_path):
    json_path = tmp_path / "state" / "data.json"
    atomic_write_json(json_path, {"b": 2, "a": 1})
    assert '"a": 1' in json_path.read_text(encoding="utf-8")

    jsonl_path = tmp_path / "events.jsonl"
    for index in range(5):
        append_jsonl(jsonl_path, {"index": index})

    assert [row["index"] for row in read_tail_jsonl(jsonl_path, 2)] == [3, 4]


def test_sqlite_wal_connection_and_migrations(tmp_path):
    db_path = tmp_path / "state.db"
    conn = sqlite_wal_connection(db_path)

    def migrate(connection):
        connection.execute("CREATE TABLE sample(id TEXT PRIMARY KEY)")

    run_migrations(conn, [(1, migrate)])
    run_migrations(conn, [(1, migrate)])
    conn.execute("INSERT INTO sample(id) VALUES ('ok')")

    rows = conn.execute("SELECT id FROM sample").fetchall()
    assert rows[0]["id"] == "ok"
