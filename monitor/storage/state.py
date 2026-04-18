from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from monitor.models import Snapshot


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    overall_summary TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dimension_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    dimension_name TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    dimension_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def ensure_parent(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_db(db_path: str) -> None:
    ensure_parent(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


def store_snapshot(db_path: str, snapshot: Snapshot) -> None:
    payload = snapshot.as_dict()
    with sqlite3.connect(db_path) as conn:
        dimension_event_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE dimension_name != 'monitor'"
        ).fetchone()[0]
        previous_states = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                """
                SELECT ds.dimension_name, ds.status, ds.summary
                FROM dimension_states ds
                JOIN snapshots s ON s.id = ds.snapshot_id
                WHERE s.id = (SELECT MAX(id) FROM snapshots)
                """
            ).fetchall()
        }
        cursor = conn.execute(
            "INSERT INTO snapshots (collected_at, overall_status, overall_summary, payload_json) VALUES (?, ?, ?, ?)",
            (
                payload["updated_at"],
                snapshot.overall_status,
                snapshot.overall_summary,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        snapshot_id = cursor.lastrowid
        for name, state in snapshot.dimensions.items():
            conn.execute(
                "INSERT INTO dimension_states (snapshot_id, dimension_name, status, summary, details_json) VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    name,
                    state.status,
                    state.summary,
                    json.dumps(state.details, ensure_ascii=False),
                ),
            )
            previous = previous_states.get(name)
            if previous is None:
                conn.execute(
                    "INSERT INTO events (created_at, dimension_name, severity, message) VALUES (?, ?, ?, ?)",
                    (
                        payload["updated_at"],
                        name,
                        state.status,
                        f"{name} initialized as {state.status}: {state.summary}",
                    ),
                )
            elif dimension_event_count == 0:
                conn.execute(
                    "INSERT INTO events (created_at, dimension_name, severity, message) VALUES (?, ?, ?, ?)",
                    (
                        payload["updated_at"],
                        name,
                        state.status,
                        f"{name} baseline {state.status}: {state.summary}",
                    ),
                )
            elif previous[0] != state.status or previous[1] != state.summary:
                if previous[0] != state.status:
                    message = f"{name} changed from {previous[0]} to {state.status}: {state.summary}"
                else:
                    message = f"{name} updated: {state.summary}"
                conn.execute(
                    "INSERT INTO events (created_at, dimension_name, severity, message) VALUES (?, ?, ?, ?)",
                    (
                        payload["updated_at"],
                        name,
                        state.status,
                        message,
                    ),
                )
        for message in snapshot.warnings:
            conn.execute(
                "INSERT INTO events (created_at, dimension_name, severity, message) VALUES (?, ?, ?, ?)",
                (payload["updated_at"], "monitor", "warn", message),
            )
        for message in snapshot.errors:
            conn.execute(
                "INSERT INTO events (created_at, dimension_name, severity, message) VALUES (?, ?, ?, ?)",
                (payload["updated_at"], "monitor", "error", message),
            )


def write_latest_state(state_path: str, snapshot: Snapshot) -> None:
    ensure_parent(state_path)
    temp_path = f"{state_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(snapshot.as_dict(), handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, state_path)


def load_latest_state(state_path: str) -> dict | None:
    path = Path(state_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_recent_events(db_path: str, limit: int = 10) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT created_at, dimension_name, severity, message
            FROM events
            WHERE dimension_name != 'monitor'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """
                SELECT created_at, dimension_name, severity, message
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [
        {
            "created_at": row[0],
            "dimension_name": row[1],
            "severity": row[2],
            "message": row[3],
        }
        for row in rows
    ]
