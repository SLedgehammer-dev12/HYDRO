from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DB_DIR = Path.home() / ".hidrostatik_test"
DB_PATH = DB_DIR / "hydro.db"
SCHEMA_VERSION = 1


class DatabaseManager:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        self._migrate()

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                inputs_json TEXT DEFAULT '{}',
                wizard_state_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS geometry_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                outside_diameter_mm REAL,
                wall_thickness_mm REAL,
                length_m REAL,
                highest_elevation_m REAL,
                lowest_elevation_m REAL,
                design_pressure_bar REAL,
                segments_json TEXT DEFAULT '[]',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS test_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                test_type TEXT NOT NULL CHECK(test_type IN ('air', 'pressure', 'field')),
                inputs_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                decision_status TEXT DEFAULT 'BEKLIYOR',
                decision_title TEXT DEFAULT '',
                decision_summary TEXT DEFAULT '',
                evaluated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS coefficients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                coefficient_type TEXT NOT NULL CHECK(coefficient_type IN ('air_a', 'pressure_a', 'pressure_b')),
                value REAL,
                source TEXT DEFAULT 'auto',
                backend TEXT DEFAULT '',
                FOREIGN KEY (entry_id) REFERENCES test_entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS time_series_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                pressure_bar REAL NOT NULL,
                temperature_c REAL NOT NULL,
                volume_m3 REAL,
                notes TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_test_entries_session
                ON test_entries(session_id);
            CREATE INDEX IF NOT EXISTS idx_time_series_session
                ON time_series_records(session_id);
            CREATE INDEX IF NOT EXISTS idx_time_series_timestamp
                ON time_series_records(timestamp);
        """)
        self.conn.commit()

    def _migrate(self) -> None:
        cursor = self.conn.execute(
            "SELECT MAX(version) FROM schema_version"
        )
        row = cursor.fetchone()
        current_version = row[0] if row and row[0] else 0

        if current_version < SCHEMA_VERSION:
            # Future migrations go here
            self.conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now().isoformat()),
            )
            self.conn.commit()

    # --- Session CRUD ---

    def save_session(
        self,
        session_id: str,
        name: str,
        notes: str = "",
        inputs: dict | None = None,
        wizard_state: dict | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        inputs_str = json.dumps(inputs or {}, ensure_ascii=False)
        wizard_str = json.dumps(wizard_state or {}, ensure_ascii=False)
        self.conn.execute(
            """INSERT INTO sessions (id, name, created_at, updated_at, notes, inputs_json, wizard_state_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   updated_at=excluded.updated_at,
                   notes=excluded.notes,
                   inputs_json=excluded.inputs_json,
                   wizard_state_json=excluded.wizard_state_json""",
            (session_id, name, now, now, notes, inputs_str, wizard_str),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT id, name, created_at, updated_at, notes, inputs_json, wizard_state_json FROM sessions ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()

    # --- Test Entry CRUD ---

    def add_test_entry(
        self,
        session_id: str,
        test_type: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
        decision_status: str = "BEKLIYOR",
        decision_title: str = "",
        decision_summary: str = "",
    ) -> int:
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO test_entries
               (session_id, test_type, inputs_json, result_json,
                decision_status, decision_title, decision_summary, evaluated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                test_type,
                json.dumps(inputs, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                decision_status,
                decision_title,
                decision_summary,
                now,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_session_entries(self, session_id: str) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT * FROM test_entries
               WHERE session_id = ?
               ORDER BY evaluated_at DESC""",
            (session_id,),
        )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            d["inputs_json"] = json.loads(d["inputs_json"])
            d["result_json"] = json.loads(d["result_json"])
            rows.append(d)
        return rows

    # --- Time Series CRUD ---

    def add_time_series_record(
        self,
        session_id: str,
        pressure_bar: float,
        temperature_c: float,
        volume_m3: float | None = None,
        notes: str = "",
    ) -> int:
        cursor = self.conn.execute(
            """INSERT INTO time_series_records
               (session_id, timestamp, pressure_bar, temperature_c, volume_m3, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, datetime.now().isoformat(), pressure_bar, temperature_c, volume_m3, notes),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_time_series(
        self, session_id: str, limit: int = 1000
    ) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT * FROM time_series_records
               WHERE session_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (session_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    # --- Statistics ---

    def get_statistics(self) -> dict[str, Any]:
        stats = {}
        cursor = self.conn.execute("SELECT COUNT(*) FROM test_entries")
        stats["total_tests"] = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT decision_status, COUNT(*) FROM test_entries GROUP BY decision_status"
        )
        stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

        cursor = self.conn.execute(
            "SELECT test_type, COUNT(*) FROM test_entries GROUP BY test_type"
        )
        stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        cursor = self.conn.execute("SELECT COUNT(*) FROM sessions")
        stats["total_sessions"] = cursor.fetchone()[0]

        cursor = self.conn.execute("SELECT COUNT(*) FROM time_series_records")
        stats["time_series_records"] = cursor.fetchone()[0]

        return stats

    def close(self) -> None:
        self.conn.close()
