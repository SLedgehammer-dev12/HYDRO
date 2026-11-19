from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

DB_DIR = Path.home() / ".hidrostatik_test"
DB_PATH = DB_DIR / "hydro.db"
SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000

# PRAGMA user_version tabanli basit migration zinciri. Anahtar hedef surumdur;
# deger o surume gecmek icin calistirilacak SQL ifadeleridir. Surum 1 temel
# semadir (CREATE TABLE IF NOT EXISTS), bu yuzden ek ifade gerekmez.
MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (),
}
# Geriye donuk uyumluluk: eski veritabanlari yalnizca schema_version tablosuyla
# surumluyordu. Migration sirasinda bu tablo da guncel tutulur.
LEGACY_SCHEMA_TABLE = "schema_version"


def _utc_now_iso() -> str:
    """UTC ISO-8601 zaman damgasi (``+00:00`` ofsetiyle)."""
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """SQLite erisim katmani.

    Ayni baglanti birden fazla thread tarafindan kullanilabilir
    (``check_same_thread=False``); tum sorgular bir ``RLock`` ile siralanir.
    Zaman damgalari UTC ISO-8601 olarak yazilir; veritabani ve dizini POSIX
    sistemlerde yalnizca sahibine aciktir (0600 / 0700).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self._lock = RLock()
        self._in_memory = str(self.db_path) == ":memory:"
        self._created_directory = False

        if not self._in_memory:
            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._created_directory = True
            else:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(
            str(self.db_path) if not self._in_memory else ":memory:",
            check_same_thread=False,
            timeout=BUSY_TIMEOUT_MS / 1000,
        )
        try:
            self.conn.row_factory = sqlite3.Row
            self.conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
            self._migrate()
            self._apply_permissions()
        except Exception:
            self.conn.close()
            raise

    # --- Schema / migrations ---

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

    def _current_schema_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version").fetchone()
        current = int(row[0]) if row and row[0] is not None else 0
        if current:
            return current
        legacy_row = self.conn.execute(f"SELECT MAX(version) FROM {LEGACY_SCHEMA_TABLE}").fetchone()
        legacy_version = int(legacy_row[0]) if legacy_row and legacy_row[0] else 0
        return legacy_version

    def _migrate(self) -> None:
        with self._lock:
            current_version = self._current_schema_version()
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Veritabani surumu ({current_version}) uygulama surumunden "
                    f"({SCHEMA_VERSION}) yeni. Uygulamayi guncelleyin."
                )
            if current_version and not self.conn.execute("PRAGMA user_version").fetchone()[0]:
                # Eski surumler yalnizca schema_version tablosunu dolduruyordu;
                # PRAGMA user_version'i ayni seviyeye getir.
                self.conn.execute(f"PRAGMA user_version={current_version}")
                self.conn.commit()
            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                statements = MIGRATIONS.get(version, ())
                try:
                    for statement in statements:
                        self.conn.execute(statement)
                    self.conn.execute(f"PRAGMA user_version={version}")
                    self.conn.execute(
                        f"""INSERT INTO {LEGACY_SCHEMA_TABLE} (version, applied_at)
                            VALUES (?, ?)
                            ON CONFLICT(version) DO UPDATE SET applied_at=excluded.applied_at""",
                        (version, _utc_now_iso()),
                    )
                    self.conn.commit()
                except sqlite3.Error:
                    self.conn.rollback()
                    raise

    def _apply_permissions(self) -> None:
        """DB dizinini 0700, dosyalarini 0600 yapar (POSIX)."""
        if os.name != "posix" or self._in_memory:
            return
        try:
            if self._created_directory or self.db_path.parent == DB_DIR:
                os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.db_path}{suffix}")
            if not candidate.exists():
                continue
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                pass

    # --- Session CRUD ---

    def save_session(
        self,
        session_id: str,
        name: str,
        notes: str = "",
        inputs: dict[str, object] | None = None,
        wizard_state: dict[str, object] | None = None,
    ) -> None:
        now = _utc_now_iso()
        inputs_str = json.dumps(inputs or {}, ensure_ascii=False)
        wizard_str = json.dumps(wizard_state or {}, ensure_ascii=False)
        with self._lock:
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
        with self._lock:
            cursor = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT id, name, created_at, updated_at, notes, inputs_json, wizard_state_json FROM sessions ORDER BY updated_at DESC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        with self._lock:
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
        now = _utc_now_iso()
        with self._lock:
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
            last_id = cursor.lastrowid
        if last_id is None:
            raise RuntimeError("Database session kaydi basarisiz.")
        return last_id

    def get_session_entries(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self.conn.execute(
                """SELECT * FROM test_entries
                   WHERE session_id = ?
                   ORDER BY evaluated_at DESC""",
                (session_id,),
            )
            raw_rows = cursor.fetchall()
        rows = []
        for row in raw_rows:
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
        with self._lock:
            cursor = self.conn.execute(
                """INSERT INTO time_series_records
                   (session_id, timestamp, pressure_bar, temperature_c, volume_m3, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, _utc_now_iso(), pressure_bar, temperature_c, volume_m3, notes),
            )
            self.conn.commit()
            last_id = cursor.lastrowid
        if last_id is None:
            raise RuntimeError("Database time series kaydi basarisiz.")
        return last_id

    def get_time_series(self, session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self.conn.execute(
                """SELECT * FROM time_series_records
                   WHERE session_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (session_id, limit),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]

    # --- Statistics ---

    def get_statistics(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        with self._lock:
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
        with self._lock:
            self.conn.close()

    # --- Diagnostics ---

    @property
    def schema_version(self) -> int:
        with self._lock:
            return int(self.conn.execute("PRAGMA user_version").fetchone()[0])


__all__ = [
    "BUSY_TIMEOUT_MS",
    "DB_DIR",
    "DB_PATH",
    "DatabaseManager",
    "MIGRATIONS",
    "SCHEMA_VERSION",
]
