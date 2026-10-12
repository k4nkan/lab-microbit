import csv
import hashlib
import io
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from .database import DATA_DIR, connect, decode_row, init_db

EXPORT_DIR = DATA_DIR / "exports"
SESSIONS_EXPORT_DIR = EXPORT_DIR / "sessions"
UNASSIGNED_EXPORT_DIR = EXPORT_DIR / "unassigned"
LOGGER_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
# The logger's own "stop" lands a few seconds after the problem site finishes.
SESSION_END_GRACE = timedelta(seconds=60)
# The Edit Logger polls every 5 s; missing two polls means it is not open.
LOGGER_STALE_AFTER = timedelta(seconds=12)
# Single-PC setup: one Edit Logger reports here, kept in memory only.
logger_status: dict[str, Any] = {"last_seen": None, "logging": False, "logger_session_id": None, "unsent": 0}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def valid_iso(value: str) -> str:
    if parse_iso(value) is None:
        raise ValueError("ISO 8601形式の時刻を指定してください")
    return value


class SessionCreate(BaseModel):
    participant_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{0,40}$")


class ProgressUpdate(BaseModel):
    task_id: str | None = None
    step_id: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)


class EventIn(BaseModel):
    event_id: UUID
    participant_id: str
    session_id: str
    task_id: str | None = None
    step_id: str | None = None
    event_type: str
    client_timestamp: str
    elapsed_ms: int = Field(ge=0)
    task_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    _timestamp = field_validator("client_timestamp")(valid_iso)


class EventBatch(BaseModel):
    events: list[EventIn] = Field(max_length=500)


class LoggerImport(BaseModel):
    participant_id: str
    experiment_session_id: str
    logger_session_id: str | None = None
    logger_data: list[dict[str, Any]] | dict[str, Any]


class LiveLoggerBatch(BaseModel):
    events: list[dict[str, Any]] = Field(max_length=2000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="micro:bit Research API", lifespan=lifespan)
origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080,http://localhost:3232").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


def require_session(db, session_id: str):
    row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "セッションが見つかりません")
    return row


def current_session(db):
    return db.execute(
        "SELECT * FROM sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()


def export_name_for(session) -> str:
    if session["export_name"]:
        return session["export_name"]
    started = parse_iso(session["started_at"]) or datetime.now(timezone.utc)
    return f"{started.astimezone():%Y%m%d-%H%M%S}_{session['participant_id']}"


def session_export_dir(db, session) -> Path:
    name = export_name_for(session)
    if not session["export_name"]:
        db.execute("UPDATE sessions SET export_name=? WHERE session_id=?", (name, session["session_id"]))
    return SESSIONS_EXPORT_DIR / name


def event_dict(row) -> dict[str, Any]:
    item = decode_row(row)
    item["metadata"] = item.pop("metadata")
    return item


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, items: list[Any]) -> None:
    if not items:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for item in items:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def session_summary(db, session) -> dict[str, Any]:
    folder = session_export_dir(db, session)
    return {
        "session_id": session["session_id"],
        "participant_id": session["participant_id"],
        "started_at": session["started_at"],
        "completed_at": session["completed_at"],
        "status": session["status"],
        "export_dir": str(folder.relative_to(DATA_DIR.parent)),
    }


def write_session_snapshot(session_id: str) -> Path:
    """Write the complete, human-readable JSON files for one experiment session."""
    with connect() as db:
        session = require_session(db, session_id)
        folder = session_export_dir(db, session)
        problem, logger, merged = merged_events(db, session_id)
        summary = session_summary(db, session)
    summary["problem_event_count"] = len(problem)
    summary["makecode_event_count"] = len(logger)
    summary["snapshot_at"] = utc_now()
    write_json(folder / "session.json", summary)
    write_json(folder / "problem-events.json", problem)
    write_json(folder / "makecode-events.json", [item["original"] for item in logger])
    write_json(folder / "merged.json", merged)
    return folder


@app.get("/api/health")
def health():
    return {"status": "ok", "server_timestamp": utc_now()}


@app.get("/api/experiment/current")
def get_current_experiment(
    logging: bool | None = None, logger_session_id: str | None = None, unsent: int | None = None
):
    """The single experiment currently running on this PC. The MakeCode logger polls this
    and reports its own state through the query parameters."""
    if logging is not None:
        logger_status.update(
            last_seen=datetime.now(timezone.utc), logging=logging,
            logger_session_id=logger_session_id or None, unsent=unsent or 0,
        )
    with connect() as db:
        session = current_session(db)
        return {"session": session_summary(db, session) if session else None}


@app.get("/api/logger/status")
def get_logger_status():
    last_seen = logger_status["last_seen"]
    connected = bool(last_seen and datetime.now(timezone.utc) - last_seen < LOGGER_STALE_AFTER)
    return {
        "connected": connected,
        "logging": connected and logger_status["logging"],
        "unsent": logger_status["unsent"] if connected else 0,
        "logger_session_id": logger_status["logger_session_id"],
        "last_seen": last_seen.isoformat().replace("+00:00", "Z") if last_seen else None,
    }


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionCreate):
    now = utc_now()
    session_id = str(uuid4())
    participant_id = body.participant_id or f"P-{secrets.token_hex(2).upper()}"
    with connect() as db:
        # One PC runs one experiment at a time; a new start closes any session left open.
        abandoned = db.execute("SELECT session_id FROM sessions WHERE status='active'").fetchall()
        db.execute("UPDATE sessions SET status='abandoned', completed_at=? WHERE status='active'", (now,))
        db.execute("INSERT OR IGNORE INTO participants VALUES (?, ?)", (participant_id, now))
        db.execute(
            "INSERT INTO sessions(session_id, participant_id, started_at) VALUES (?, ?, ?)",
            (session_id, participant_id, now),
        )
        db.execute(
            "INSERT INTO session_progress(session_id, state_json, updated_at) VALUES (?, '{}', ?)",
            (session_id, now),
        )
        summary = session_summary(db, require_session(db, session_id))
    for row in abandoned:
        write_session_snapshot(row["session_id"])
    write_session_snapshot(session_id)
    return summary


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    with connect() as db:
        session = require_session(db, session_id)
        progress = db.execute("SELECT * FROM session_progress WHERE session_id = ?", (session_id,)).fetchone()
        return {**dict(session), "progress": decode_row(progress)}


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: str, body: ProgressUpdate):
    with connect() as db:
        require_session(db, session_id)
        db.execute(
            "UPDATE session_progress SET task_id=?, step_id=?, state_json=?, updated_at=? WHERE session_id=?",
            (body.task_id, body.step_id, json.dumps(body.state, ensure_ascii=False), utc_now(), session_id),
        )
    return {"saved": True}


def save_events(events: list[EventIn]) -> tuple[int, int]:
    saved = duplicate = 0
    now = utc_now()
    appended: dict[Path, list[dict[str, Any]]] = {}
    with connect() as db:
        sessions: dict[str, Any] = {}
        for event in events:
            session = sessions.get(event.session_id) or require_session(db, event.session_id)
            sessions[event.session_id] = session
            if session["participant_id"] != event.participant_id:
                raise HTTPException(400, "参加者IDとセッションが一致しません")
            row = (
                str(event.event_id), event.participant_id, event.session_id, event.task_id,
                event.step_id, event.event_type, event.client_timestamp, now, event.elapsed_ms,
                event.task_version, json.dumps(event.metadata, ensure_ascii=False),
            )
            cursor = db.execute("INSERT OR IGNORE INTO problem_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
            if cursor.rowcount:
                saved += 1
                path = session_export_dir(db, session) / "problem-events.jsonl"
                appended.setdefault(path, []).append({**event.model_dump(mode="json"), "server_timestamp": now})
            else:
                duplicate += 1
    for path, items in appended.items():
        append_jsonl(path, items)
    return saved, duplicate


@app.post("/api/events", status_code=201)
def create_event(body: EventIn):
    saved, duplicate = save_events([body])
    return {"saved": saved, "duplicate": duplicate}


@app.post("/api/events/batch")
def create_event_batch(body: EventBatch):
    saved, duplicate = save_events(body.events)
    return {"saved": saved, "duplicate": duplicate}


def logger_event_key(event: dict[str, Any], original_json: str) -> str:
    event_id = event.get("eventId")
    if isinstance(event_id, str) and 0 < len(event_id) <= 120:
        return f"id:{event_id}"
    return hashlib.sha256(original_json.encode("utf-8")).hexdigest()


def session_window(row) -> tuple[Any, datetime | None, datetime | None]:
    completed = parse_iso(row["completed_at"])
    return row, parse_iso(row["started_at"]), completed + SESSION_END_GRACE if completed else None


@app.post("/api/logger/events/batch")
def save_live_logger_events(body: LiveLoggerBatch):
    """Store MakeCode logger events. Events are never rejected for linkage:
    each one is attached to the experiment session whose time window contains it."""
    saved = duplicate = skipped = 0
    now = utc_now()
    appended: dict[Path, list[dict[str, Any]]] = {}
    with connect() as db:
        # Newest first, so a session started right after another one wins the overlap.
        windows = [session_window(row) for row in db.execute("SELECT * FROM sessions ORDER BY started_at DESC")]
        for event in body.events:
            logger_session_id = event.get("sessionId")
            if not isinstance(logger_session_id, str) or not LOGGER_SESSION_ID.match(logger_session_id):
                skipped += 1
                continue
            at = parse_iso(event.get("at"))
            session = next(
                (row for row, start, end in windows if at and start and start <= at and (end is None or at <= end)),
                None,
            )
            original_json = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            cursor = db.execute(
                """INSERT OR IGNORE INTO live_logger_events
                (event_hash, logger_session_id, experiment_session_id, connection_id,
                 event_timestamp, event_type, received_at, original_json)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?)""",
                (logger_event_key(event, original_json), logger_session_id,
                 session["session_id"] if session else None, event.get("at"), event.get("type"), now, original_json),
            )
            if not cursor.rowcount:
                duplicate += 1
                continue
            saved += 1
            path = (
                session_export_dir(db, session) / "makecode-events.jsonl"
                if session
                else UNASSIGNED_EXPORT_DIR / f"makecode-{logger_session_id}.jsonl"
            )
            appended.setdefault(path, []).append(event)
    for path, items in appended.items():
        append_jsonl(path, items)
    return {"saved": saved, "duplicate": duplicate, "skipped": skipped}


@app.post("/api/sessions/{session_id}/finish")
def finish_session(session_id: str):
    with connect() as db:
        require_session(db, session_id)
        now = utc_now()
        db.execute(
            "UPDATE sessions SET completed_at=?, status='completed' WHERE session_id=? AND status='active'",
            (now, session_id),
        )
    folder = write_session_snapshot(session_id)
    return {"completed_at": now, "status": "completed", "export_dir": str(folder.relative_to(DATA_DIR.parent))}


@app.post("/api/sessions/{session_id}/snapshot")
def snapshot_session(session_id: str):
    folder = write_session_snapshot(session_id)
    return {"export_dir": str(folder.relative_to(DATA_DIR.parent)), "saved_at": utc_now()}


@app.get("/api/admin/sessions")
def admin_sessions():
    with connect() as db:
        rows = db.execute(
            """SELECT s.*, p.task_id, p.step_id,
            (SELECT COUNT(*) FROM problem_events e WHERE e.session_id=s.session_id) event_count,
            (SELECT COUNT(*) FROM live_logger_events l WHERE l.experiment_session_id=s.session_id) logger_event_count,
            ((SELECT COUNT(*) FROM imported_logger_sessions i WHERE i.experiment_session_id=s.session_id) +
             (SELECT COUNT(DISTINCT l.logger_session_id) FROM live_logger_events l WHERE l.experiment_session_id=s.session_id)) logger_import_count
            FROM sessions s LEFT JOIN session_progress p ON p.session_id=s.session_id
            ORDER BY s.started_at DESC"""
        ).fetchall()
        return [{**dict(row), "export_dir": session_summary(db, row)["export_dir"]} for row in rows]


def merged_events(db, session_id: str):
    problem_rows = db.execute(
        "SELECT * FROM problem_events WHERE session_id=? ORDER BY client_timestamp", (session_id,)
    ).fetchall()
    logger_rows = db.execute(
        """SELECT e.* FROM imported_logger_events e
        JOIN imported_logger_sessions s ON s.id=e.imported_session_id
        WHERE s.experiment_session_id=? ORDER BY e.event_timestamp""", (session_id,)
    ).fetchall()
    live_logger_rows = db.execute(
        """SELECT event_type, event_timestamp, original_json
        FROM live_logger_events WHERE experiment_session_id=? ORDER BY event_timestamp, rowid""",
        (session_id,),
    ).fetchall()
    session = require_session(db, session_id)
    problem = [event_dict(row) for row in problem_rows]
    logger = [decode_row(row) for row in logger_rows] + [decode_row(row) for row in live_logger_rows]
    merged = [
        {"participant_id": session["participant_id"], "experiment_session_id": session_id,
         "source": "problem_site", "timestamp": item["client_timestamp"],
         "event_type": item["event_type"], "original_event": item}
        for item in problem
    ] + [
        {"participant_id": session["participant_id"], "experiment_session_id": session_id,
         "source": "makecode_logger", "timestamp": item.get("event_timestamp"),
         "event_type": item.get("event_type"), "original_event": item["original"]}
        for item in logger
    ]
    merged.sort(key=lambda item: parse_iso(item["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc))
    return problem, logger, merged


@app.get("/api/admin/sessions/{session_id}")
def admin_session_detail(session_id: str):
    with connect() as db:
        problem, logger, merged = merged_events(db, session_id)
    return {"problem_events": problem, "logger_events": logger, "merged_events": merged}


@app.post("/api/admin/import-logger", status_code=201)
def import_logger(body: LoggerImport):
    raw_events = body.logger_data if isinstance(body.logger_data, list) else body.logger_data.get("events")
    if not isinstance(raw_events, list) or not raw_events or not all(isinstance(item, dict) for item in raw_events):
        raise HTTPException(400, "ロガーJSONはイベント配列で指定してください")
    logger_ids = sorted({str(item.get("sessionId")) for item in raw_events if item.get("sessionId")})
    if not logger_ids:
        raise HTTPException(400, "sessionIdを含むイベントがありません")
    selected = body.logger_session_id
    if selected is None and len(logger_ids) > 1:
        raise HTTPException(400, {"message": "複数のロガーセッションがあります", "logger_session_ids": logger_ids})
    selected = selected or logger_ids[0]
    if selected not in logger_ids:
        raise HTTPException(400, "指定したlogger_session_idがJSON内にありません")
    events = [item for item in raw_events if str(item.get("sessionId")) == selected]
    with connect() as db:
        session = require_session(db, body.experiment_session_id)
        if session["participant_id"] != body.participant_id:
            raise HTTPException(400, "参加者IDとセッションが一致しません")
        existing = db.execute(
            "SELECT id FROM imported_logger_sessions WHERE experiment_session_id=? AND logger_session_id=?",
            (body.experiment_session_id, selected),
        ).fetchone()
        if existing:
            raise HTTPException(409, "このロガーセッションは取り込み済みです")
        cursor = db.execute(
            """INSERT INTO imported_logger_sessions
            (experiment_session_id, participant_id, logger_session_id, imported_at, original_json)
            VALUES (?, ?, ?, ?, ?)""",
            (body.experiment_session_id, body.participant_id, selected, utc_now(), json.dumps(body.logger_data, ensure_ascii=False)),
        )
        import_id = cursor.lastrowid
        for item in events:
            db.execute(
                """INSERT INTO imported_logger_events
                (imported_session_id, logger_session_id, event_type, event_timestamp, original_json)
                VALUES (?, ?, ?, ?, ?)""",
                (import_id, selected, item.get("type"), item.get("at"), json.dumps(item, ensure_ascii=False)),
            )
    write_session_snapshot(body.experiment_session_id)
    return {"logger_session_id": selected, "event_count": len(events), "available_session_ids": logger_ids}


@app.get("/api/admin/export")
def export_logs(
    session_id: str,
    kind: Literal["problem", "logger", "merged"] = "merged",
    format: Literal["json", "csv"] = Query("json"),
):
    with connect() as db:
        problem, logger, merged = merged_events(db, session_id)
        if kind == "problem":
            data = problem
        elif kind == "logger":
            data = [item["original"] for item in logger]
        else:
            data = merged
    filename = f"{session_id}-{kind}.{format}"
    if format == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    output = io.StringIO()
    fields = sorted({key for item in data for key in item.keys()}) if data else []
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in data:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in item.items()})
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
