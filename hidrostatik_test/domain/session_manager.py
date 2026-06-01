from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Timer
from typing import Any

from .time_series import TimeSeriesStore


@dataclass
class TestSession:
    id: str = ""
    name: str = "Yeni Oturum"
    created_at: str = ""
    updated_at: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, object]] = field(default_factory=list)
    time_series: dict[str, object] = field(default_factory=dict)
    wizard_state: dict[str, object] | None = None
    geometry_segments: list[dict[str, object]] = field(default_factory=list)
    notes: str = ""
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TestSession:
        cleaned_data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**cleaned_data)


SESSIONS_DIR = Path.home() / ".hidrostatik_test" / "sessions"
INDEX_FILE = SESSIONS_DIR / "index.json"
AUTO_SAVE_INTERVAL_S = 60


class SessionManager:
    def __init__(
        self,
        sessions_dir: Path | None = None,
        use_db: bool = False,
        db_path: Path | None = None,
    ) -> None:
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.sessions_dir / "index.json"
        
        self.use_db = use_db
        self._db: Any | None = None
        self._sessions: dict[str, TestSession] = {}
        self._active_session_id: str | None = None
        self._auto_save_timer: Timer | None = None

        if use_db:
            from ..services.database import DatabaseManager
            self._db = DatabaseManager(db_path=db_path)

        if self._db:
            self._load_from_db()
        else:
            self._load_index()

    # --- Core Operations ---

    def create_session(self, name: str = "Yeni Oturum") -> TestSession:
        if self._active_session_id:
            self._save_active_session()
        session = TestSession(name=name)
        self._sessions[session.id] = session
        self._active_session_id = session.id
        self._save_active_session()
        self._save_index()
        self._start_auto_save()
        return session

    def switch_session(self, session_id: str) -> TestSession:
        if self._active_session_id and self._active_session_id != session_id:
            self._save_active_session()
        
        if self._db:
            session = self._load_session_from_db(session_id)
        else:
            session = self._load_session_from_disk(session_id)
            
        self._sessions[session_id] = session
        self._active_session_id = session_id
        self._start_auto_save()
        return session

    def close_session(self, session_id: str) -> None:
        if session_id == self._active_session_id:
            self._save_active_session()
            self._active_session_id = None
            self._stop_auto_save()
        self._sessions.pop(session_id, None)
        self._save_index()

    def delete_session(self, session_id: str) -> None:
        self.close_session(session_id)
        if self._db:
            self._db.delete_session(session_id)
        else:
            session_path = self._session_path(session_id)
            if session_path.exists():
                session_path.unlink()

    def list_sessions(self) -> list[dict[str, str]]:
        if self._db:
            db_sessions = self._db.list_sessions()
            sessions = []
            for s in db_sessions:
                sessions.append({
                    "id": s["id"],
                    "name": s["name"],
                    "created_at": s["created_at"],
                    "updated_at": s["updated_at"],
                    "is_active": s["id"] == self._active_session_id,
                })
            return sorted(sessions, key=lambda s: s["updated_at"], reverse=True)
            
        sessions = []
        for sid, session in self._sessions.items():
            sessions.append({
                "id": sid,
                "name": session.name,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "is_active": sid == self._active_session_id,
            })
        return sorted(sessions, key=lambda s: s["updated_at"], reverse=True)

    # --- Data Access ---

    def get_active_session(self) -> TestSession | None:
        if self._active_session_id:
            return self._sessions.get(self._active_session_id)
        return None

    def update_inputs(self, inputs: dict[str, str]) -> None:
        session = self.get_active_session()
        if session:
            session.inputs = inputs
            session.updated_at = datetime.now(timezone.utc).isoformat()
            # Also update segments from snapshot if present
            if "geometry_segments" in inputs:
                session.geometry_segments = inputs["geometry_segments"]
            self._save_active_session()

    def add_result(self, result: dict[str, object]) -> None:
        session = self.get_active_session()
        if session:
            session.results.append(result)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_active_session()

    def update_wizard_state(self, state: dict[str, object]) -> None:
        session = self.get_active_session()
        if session:
            session.wizard_state = state
            session.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_active_session()

    # --- Persistence ---

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _save_session_to_disk(self, session: TestSession) -> None:
        path = self._session_path(session.id)
        path.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_session_from_disk(self, session_id: str) -> TestSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return TestSession.from_dict(data)

    def _save_active_session(self) -> None:
        session = self.get_active_session()
        if not session:
            return
        if self._db:
            # Reconstruct and save to DB
            self._db.save_session(
                session_id=session.id,
                name=session.name,
                notes=session.notes,
                inputs=session.inputs,
                wizard_state=session.wizard_state,
            )
        else:
            self._save_session_to_disk(session)

    def _save_index(self) -> None:
        if self._db:
            return
        index = []
        for session in self._sessions.values():
            index.append({
                "id": session.id,
                "name": session.name,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })
        self.index_file.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_index(self) -> None:
        if not self.index_file.exists():
            return
        try:
            index = json.loads(self.index_file.read_text(encoding="utf-8"))
            for entry in index:
                try:
                    session = self._load_session_from_disk(entry["id"])
                    self._sessions[session.id] = session
                except (FileNotFoundError, json.JSONDecodeError):
                    continue
        except (json.JSONDecodeError, OSError):
            pass

    def _load_from_db(self) -> None:
        if not self._db:
            return
        db_sessions = self._db.list_sessions()
        for s_info in db_sessions:
            sid = s_info["id"]
            try:
                session = self._load_session_from_db(sid)
                self._sessions[sid] = session
            except Exception:
                continue

    def _load_session_from_db(self, session_id: str) -> TestSession:
        if not self._db:
            raise ValueError("No database manager initialized")
        s_row = self._db.get_session(session_id)
        if not s_row:
            raise FileNotFoundError(f"Session not found in DB: {session_id}")
        
        # Parse inputs and wizard state
        inputs = {}
        if s_row.get("inputs_json"):
            try:
                inputs = json.loads(s_row["inputs_json"])
            except Exception:
                pass
                
        wizard_state = None
        if s_row.get("wizard_state_json"):
            try:
                wizard_state = json.loads(s_row["wizard_state_json"])
            except Exception:
                pass

        # Load time series
        time_series_data = {"records": []}
        try:
            records = self._db.get_time_series(session_id)
            for r in records:
                time_series_data["records"].append({
                    "timestamp": r["timestamp"],
                    "pressure_bar": r["pressure_bar"],
                    "temperature_c": r["temperature_c"],
                    "volume_m3": r["volume_m3"],
                    "notes": r["notes"]
                })
        except Exception:
            pass

        # Load test entries to results
        results = []
        try:
            entries = self._db.get_session_entries(session_id)
            for e in entries:
                results.append(e["result_json"])
        except Exception:
            pass

        return TestSession(
            id=s_row["id"],
            name=s_row["name"],
            created_at=s_row["created_at"],
            updated_at=s_row["updated_at"],
            notes=s_row.get("notes") or "",
            inputs=inputs,
            wizard_state=wizard_state,
            results=results,
            time_series=time_series_data,
        )

    # --- Auto-save ---

    def _start_auto_save(self) -> None:
        self._stop_auto_save()
        self._auto_save_timer = Timer(AUTO_SAVE_INTERVAL_S, self._auto_save_tick)
        self._auto_save_timer.daemon = True
        self._auto_save_timer.start()

    def _stop_auto_save(self) -> None:
        if self._auto_save_timer:
            self._auto_save_timer.cancel()
            self._auto_save_timer = None

    def _auto_save_tick(self) -> None:
        self._save_active_session()
        self._start_auto_save()

    # --- Startup ---

    def restore_last_session(self) -> TestSession | None:
        sessions = self.list_sessions()
        if not sessions:
            return self.create_session("Varsayilan Oturum")
        latest = sessions[0]
        return self.switch_session(latest["id"])
