import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
DB_PATH = DATA_DIR / "research.db"


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS participants (
              participant_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              participant_id TEXT NOT NULL REFERENCES participants(participant_id),
              started_at TEXT NOT NULL,
              completed_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS session_progress (
              session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
              task_id TEXT,
              step_id TEXT,
              state_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS problem_events (
              event_id TEXT PRIMARY KEY,
              participant_id TEXT NOT NULL,
              session_id TEXT NOT NULL REFERENCES sessions(session_id),
              task_id TEXT,
              step_id TEXT,
              event_type TEXT NOT NULL,
              client_timestamp TEXT NOT NULL,
              server_timestamp TEXT NOT NULL,
              elapsed_ms INTEGER NOT NULL,
              task_version TEXT NOT NULL,
              metadata_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_problem_events_session_time
              ON problem_events(session_id, client_timestamp);
            CREATE TABLE IF NOT EXISTS imported_logger_sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              experiment_session_id TEXT NOT NULL REFERENCES sessions(session_id),
              participant_id TEXT NOT NULL,
              logger_session_id TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              original_json TEXT NOT NULL,
              UNIQUE(experiment_session_id, logger_session_id)
            );
            CREATE TABLE IF NOT EXISTS imported_logger_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              imported_session_id INTEGER NOT NULL REFERENCES imported_logger_sessions(id),
              logger_session_id TEXT NOT NULL,
              event_type TEXT,
              event_timestamp TEXT,
              original_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logger_events_session_time
              ON imported_logger_events(imported_session_id, event_timestamp);
            CREATE TABLE IF NOT EXISTS live_logger_events (
              event_hash TEXT PRIMARY KEY,
              logger_session_id TEXT NOT NULL,
              experiment_session_id TEXT,
              connection_id TEXT,
              event_timestamp TEXT,
              event_type TEXT,
              received_at TEXT NOT NULL,
              original_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_live_logger_events_session_time
              ON live_logger_events(logger_session_id, event_timestamp);
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(live_logger_events)")}
        if "experiment_session_id" not in columns:
            db.execute("ALTER TABLE live_logger_events ADD COLUMN experiment_session_id TEXT")
        if "connection_id" not in columns:
            db.execute("ALTER TABLE live_logger_events ADD COLUMN connection_id TEXT")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def decode_row(row):
    if row is None:
        return None
    result = dict(row)
    for key in ("state_json", "metadata_json", "original_json"):
        if key in result:
            result[key.removesuffix("_json")] = json.loads(result.pop(key))
    return result

