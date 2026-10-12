import csv
import hashlib
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from .database import DATA_DIR, connect, decode_row, init_db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def valid_iso(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ISO 8601形式の時刻を指定してください") from exc
    return value


class SessionCreate(BaseModel):
    participant_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")


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
    events: list[dict[str, Any]] = Field(max_length=10000)
    connection_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,40}$")


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


def find_active_session(db, connection_id: str):
    return db.execute(
        """SELECT session_id, participant_id, started_at FROM sessions
        WHERE participant_id=? AND status='active' ORDER BY started_at DESC LIMIT 1""",
        (connection_id,),
    ).fetchone()


def event_dict(row) -> dict[str, Any]:
    item = decode_row(row)
    item["metadata"] = item.pop("metadata")
    return item


def write_json(path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def export_problem_session(session_id: str) -> None:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM problem_events WHERE session_id=? ORDER BY client_timestamp", (session_id,)
        ).fetchall()
    write_json(DATA_DIR / "exports" / "problem-site" / f"{session_id}.json", [event_dict(row) for row in rows])


def export_live_logger_session(logger_session_id: str, connection_id: str | None = None) -> None:
    with connect() as db:
        rows = db.execute(
            "SELECT original_json FROM live_logger_events WHERE logger_session_id=? ORDER BY event_timestamp, rowid",
            (logger_session_id,),
        ).fetchall()
    write_json(
        DATA_DIR / "exports" / "makecode-logger" / (connection_id or "unlinked") / f"{logger_session_id}.json",
        [json.loads(row["original_json"]) for row in rows],
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "server_timestamp": utc_now()}


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionCreate):
    now = utc_now()
    session_id = str(uuid4())
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO participants VALUES (?, ?)", (body.participant_id, now))
        db.execute(
            "INSERT INTO sessions(session_id, participant_id, started_at) VALUES (?, ?, ?)",
            (session_id, body.participant_id, now),
        )
        db.execute(
            "INSERT INTO session_progress(session_id, state_json, updated_at) VALUES (?, '{}', ?)",
            (session_id, now),
        )
    return {"session_id": session_id, "participant_id": body.participant_id, "started_at": now, "status": "active"}


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
    session_ids: set[str] = set()
    with connect() as db:
        sessions: dict[str, Any] = {}
        for event in events:
            session_ids.add(event.session_id)
            session = sessions.get(event.session_id) or require_session(db, event.session_id)
            sessions[event.session_id] = session
            if session["participant_id"] != event.participant_id:
                raise HTTPException(400, "参加者IDとセッションが一致しません")
            cursor = db.execute(
                """INSERT OR IGNORE INTO problem_events
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(event.event_id), event.participant_id, event.session_id, event.task_id,
                    event.step_id, event.event_type, event.client_timestamp, now, event.elapsed_ms,
                    event.task_version, json.dumps(event.metadata, ensure_ascii=False),
                ),
            )
            if cursor.rowcount:
                saved += 1
            else:
                duplicate += 1
    for session_id in session_ids:
        export_problem_session(session_id)
    return saved, duplicate


@app.post("/api/events", status_code=201)
def create_event(body: EventIn):
    saved, duplicate = save_events([body])
    return {"saved": saved, "duplicate": duplicate}


@app.post("/api/events/batch")
def create_event_batch(body: EventBatch):
    saved, duplicate = save_events(body.events)
    return {"saved": saved, "duplicate": duplicate}


@app.post("/api/logger/events/batch")
def save_live_logger_events(body: LiveLoggerBatch):
    saved = duplicate = 0
    logger_session_ids: set[str] = set()
    experiment_session_id = None
    with connect() as db:
        if body.connection_id:
            linked_session = find_active_session(db, body.connection_id)
            if not linked_session:
                raise HTTPException(400, "接続IDに対応する実験セッションがありません")
            experiment_session_id = linked_session["session_id"]
        for event in body.events:
            logger_session_id = event.get("sessionId")
            if not isinstance(logger_session_id, str) or not logger_session_id or not logger_session_id.replace("-", "").replace("_", "").isalnum():
                raise HTTPException(400, "有効なsessionIdを含むイベントを指定してください")
            logger_session_ids.add(logger_session_id)
            original_json = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            event_hash = hashlib.sha256(original_json.encode("utf-8")).hexdigest()
            cursor = db.execute(
                """INSERT OR IGNORE INTO live_logger_events
                (event_hash, logger_session_id, experiment_session_id, connection_id,
                 event_timestamp, event_type, received_at, original_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_hash, logger_session_id, experiment_session_id, body.connection_id,
                 event.get("at"), event.get("type"), utc_now(), original_json),
            )
            if cursor.rowcount:
                saved += 1
            else:
                duplicate += 1
                if experiment_session_id:
                    db.execute(
                        """UPDATE live_logger_events
                        SET experiment_session_id=?, connection_id=? WHERE event_hash=?""",
                        (experiment_session_id, body.connection_id, event_hash),
                    )
    for logger_session_id in logger_session_ids:
        export_live_logger_session(logger_session_id, body.connection_id)
    return {"saved": saved, "duplicate": duplicate, "experiment_session_id": experiment_session_id}


@app.get("/api/logger/connections/{connection_id}")
def get_logger_connection(connection_id: str):
    with connect() as db:
        session = find_active_session(db, connection_id)
    if not session:
        raise HTTPException(404, "接続IDに対応する実験セッションがありません")
    return dict(session)


@app.post("/api/sessions/{session_id}/finish")
def finish_session(session_id: str):
    with connect() as db:
        require_session(db, session_id)
        now = utc_now()
        db.execute("UPDATE sessions SET completed_at=?, status='completed' WHERE session_id=?", (now, session_id))
    return {"completed_at": now, "status": "completed"}


@app.get("/api/admin/sessions")
def admin_sessions():
    with connect() as db:
        rows = db.execute(
            """SELECT s.*, p.task_id, p.step_id,
            (SELECT COUNT(*) FROM problem_events e WHERE e.session_id=s.session_id) event_count,
            ((SELECT COUNT(*) FROM imported_logger_sessions i WHERE i.experiment_session_id=s.session_id) +
             (SELECT COUNT(DISTINCT l.logger_session_id) FROM live_logger_events l WHERE l.experiment_session_id=s.session_id)) logger_import_count
            FROM sessions s LEFT JOIN session_progress p ON p.session_id=s.session_id
            ORDER BY s.started_at DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


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
        FROM live_logger_events WHERE experiment_session_id=? ORDER BY event_timestamp""",
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
    merged.sort(key=lambda item: item["timestamp"] or "")
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

