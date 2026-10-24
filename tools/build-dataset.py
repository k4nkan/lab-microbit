#!/usr/bin/env python3
"""Bundle one experiment session from the research DB into an analysis folder.

Usage:
  python3 tools/build-dataset.py                 # latest completed session
  python3 tools/build-dataset.py P-5165          # by participant ID, export name or session ID
  python3 tools/build-dataset.py --all           # every session

Output: microbit-research-website/backend/data/datasets/<開始日時>_<参加者ID>/
Only the standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "microbit-research-website" / "backend" / "data"
DB_PATH = DATA_DIR / "research.db"
OUT_DIR = DATA_DIR / "datasets"

SENSOR_KEYS = ["accelerationX", "accelerationY", "accelerationZ", "lightLevel", "temperature",
               "buttonA", "buttonB", "logoTouch", "soundLevel", "compassHeading"]
# Same columns as the Edit Logger's "Export CSV", so tools/*-analytics.py can read it.
LOGGER_CSV_HEADERS = ["at", "localDate", "timeZone", "sessionStartedAt", "sessionId", "type", "elapsedMs",
                      "source", "sim", "files", "totalBlocks", "contentHash", "mainTs", "mainBlocks", "runId",
                      "bootAt", "runningContentHash", "runAnchorSource", "blockChanges", *SENSOR_KEYS, "detail"]


BLOCKLY_NS = "{https://developers.google.com/blockly/xml}"
LOOP_TYPES = {"controls_repeat_ext", "controls_whileUntil", "controls_simple_for", "controls_for_of",
              "pxt_controls_for", "pxt_controls_for_of", "device_while"}


def code_metrics(blocks_xml: str) -> dict:
    """Code metrics after Makihara et al. (2022), adapted to MakeCode.

    BLN: placed blocks (shadow literals excluded); LOB: blocks per running script;
    CCN: 1 + branches and loops per script; scripts: event/forever/on-start handlers
    (stands in for SPN, as micro:bit programs have no sprites); dead: blocks MakeCode
    disabled because they are not attached to any handler.
    """
    empty = {"bln": 0, "scripts": 0, "executed_blocks": 0, "dead_blocks": 0, "lob_avg": 0, "ccn_avg": 0,
             "ccn_max": 0, "variables": 0, "script_types": ""}
    try:
        root = ET.fromstring(blocks_xml) if blocks_xml else None
    except ET.ParseError:
        return empty
    if root is None:
        return empty
    tag = lambda el: el.tag.replace(BLOCKLY_NS, "")
    blocks = [el for el in root.iter() if tag(el) == "block"]
    dead = [el for el in blocks if el.get("disabled-reasons") or el.get("disabled") == "true"]
    scripts = [el for el in root if tag(el) == "block" and not (el.get("disabled-reasons") or el.get("disabled") == "true")]
    sizes, ccns = [], []
    for script in scripts:
        inner = [el for el in script.iter() if tag(el) == "block"]
        sizes.append(len(inner))
        branches = 0
        for el in inner:
            if el.get("type") == "controls_if":
                mutation = next((m for m in el if tag(m) == "mutation"), None)
                branches += 1 + int(mutation.get("elseif", 0)) if mutation is not None else 1
            elif el.get("type") in LOOP_TYPES:
                branches += 1
        ccns.append(1 + branches)
    variables = next((el for el in root if tag(el) == "variables"), None)
    return {
        "bln": len(blocks), "scripts": len(scripts), "executed_blocks": sum(sizes), "dead_blocks": len(dead),
        "lob_avg": round(sum(sizes) / len(sizes), 2) if sizes else 0,
        "ccn_avg": round(sum(ccns) / len(ccns), 2) if ccns else 0, "ccn_max": max(ccns, default=0),
        "variables": len(variables) if variables is not None else 0,
        "script_types": " ".join(sorted(script.get("type", "") for script in scripts)),
    }


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def local(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if value else ""


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def select_sessions(db, key: str | None, all_sessions: bool):
    if all_sessions:
        return db.execute("SELECT * FROM sessions ORDER BY started_at").fetchall()
    if key:
        rows = db.execute(
            "SELECT * FROM sessions WHERE session_id=? OR participant_id=? OR export_name=? ORDER BY started_at",
            (key, key, key),
        ).fetchall()
        if not rows:
            raise SystemExit(f"No session matches {key!r}")
        return rows
    row = db.execute("SELECT * FROM sessions WHERE status='completed' ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:
        raise SystemExit("No completed session yet")
    return [row]


class StepClock:
    """Which problem-site step the participant was on at a given time."""

    def __init__(self, problem_events: list[dict]):
        self.times: list[datetime] = []
        self.steps: list[tuple[str, str]] = []
        for event in problem_events:
            at = parse_time(event["client_timestamp"])
            if event["event_type"] == "step_viewed" and event["step_id"]:
                self._add(at, event["task_id"] or "", event["step_id"])
            elif event["event_type"] == "task_started" and event["task_id"] in ("arrange", "free-creation"):
                self._add(at, "arrange", "arrange")
            elif event["event_type"] == "task_completed" and event["step_id"] == "G7":
                self._add(at, "arrange", "arrange")
            elif event["event_type"] == "session_completed":
                self._add(at, "", "finished")

    def _add(self, at, task_id, step_id):
        self.times.append(at)
        self.steps.append((task_id, step_id))

    def at(self, when: datetime | None) -> tuple[str, str]:
        if when is None:
            return "", ""
        index = bisect_right(self.times, when) - 1
        return self.steps[index] if index >= 0 else ("", "before_tasks")


def build(db, session, out_root: Path) -> Path:
    session_id = session["session_id"]
    name = session["export_name"] or f"{parse_time(session['started_at']).astimezone():%Y%m%d-%H%M%S}_{session['participant_id']}"
    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    (out / "code").mkdir(parents=True)
    (out / "raw").mkdir()
    started = parse_time(session["started_at"])
    t_sec = lambda when: round((when - started).total_seconds(), 3) if when else ""

    problem = []
    for row in db.execute("SELECT * FROM problem_events WHERE session_id=? ORDER BY client_timestamp", (session_id,)):
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        problem.append(item)
    makecode = [json.loads(row["original_json"]) for row in db.execute(
        "SELECT original_json FROM live_logger_events WHERE experiment_session_id=? ORDER BY event_timestamp, rowid",
        (session_id,))]
    makecode += [json.loads(row["original_json"]) for row in db.execute(
        """SELECT e.original_json FROM imported_logger_events e JOIN imported_logger_sessions s
        ON s.id=e.imported_session_id WHERE s.experiment_session_id=? ORDER BY e.event_timestamp""", (session_id,))]
    makecode.sort(key=lambda event: parse_time(event.get("at")) or started)
    clock = StepClock(problem)

    write_json(out / "raw" / "problem-events.json", problem)
    write_json(out / "raw" / "makecode-events.json", makecode)

    # problem_events.csv
    problem_rows = [{
        "time_local": local(parse_time(e["client_timestamp"])), "t_sec": t_sec(parse_time(e["client_timestamp"])),
        "event_type": e["event_type"], "task_id": e["task_id"] or "", "step_id": e["step_id"] or "",
        "metadata": json.dumps(e["metadata"], ensure_ascii=False), "event_id": e["event_id"],
    } for e in problem]
    write_csv(out / "problem_events.csv", problem_rows,
              ["time_local", "t_sec", "event_type", "task_id", "step_id", "metadata", "event_id"])

    # code snapshots, unique code files, block changes
    snapshots, type_changes, code_files = [], [], {}
    previous_types: dict[str, int] = {}
    for event in makecode:
        if event["type"] not in ("start", "change"):
            continue
        at = parse_time(event["at"])
        step = clock.at(at)
        index = len(snapshots) + 1
        content_hash = event.get("contentHash", "")
        if content_hash not in code_files:
            stem = f"{len(code_files) + 1:04d}_{at.astimezone():%H%M%S}_{content_hash}"
            (out / "code" / f"{stem}.ts").write_text(event.get("mainTs", ""), encoding="utf-8")
            (out / "code" / f"{stem}.blocks.xml").write_text(event.get("mainBlocks", ""), encoding="utf-8")
            code_files[content_hash] = f"code/{stem}.ts"
        # The logger's blockChanges match blocks by document position and are unreliable
        # (MakeCode saves no block IDs), so changes are counted per block type instead.
        types = event.get("blockTypes") or {}
        added = removed = 0
        for block_type in sorted(set(types) | set(previous_types)):
            delta = types.get(block_type, 0) - previous_types.get(block_type, 0)
            if delta:
                type_changes.append({"snapshot_index": index, "time_local": local(at), "t_sec": t_sec(at),
                                     "task_id": step[0], "step_id": step[1], "block_type": block_type,
                                     "delta": delta})
                added += max(delta, 0)
                removed += max(-delta, 0)
        previous_types = types
        metrics = code_metrics(event.get("mainBlocks", ""))
        snapshots.append({
            "snapshot_index": index, "time_local": local(at), "t_sec": t_sec(at), "type": event["type"],
            "phase": event.get("phase", ""), "task_id": step[0], "step_id": step[1],
            "content_hash": content_hash, **metrics,
            "blocks_incl_shadows": event.get("totalBlocks", ""), "ts_lines": event.get("mainTs", "").count("\n"),
            "added_blocks": added, "removed_blocks": removed, "code_file": code_files[content_hash],
        })
    write_csv(out / "code_snapshots.csv", snapshots, list(snapshots[0]) if snapshots else ["snapshot_index"])
    write_csv(out / "block_type_changes.csv", type_changes,
              ["snapshot_index", "time_local", "t_sec", "task_id", "step_id", "block_type", "delta"])

    # sensors.csv and runs.csv
    sensors = []
    for event in makecode:
        if event["type"] != "sensor":
            continue
        at = parse_time(event["at"])
        step = clock.at(at)
        ax, ay, az = (event.get(k) or 0 for k in ("accelerationX", "accelerationY", "accelerationZ"))
        sensors.append({
            "time_local": local(at), "t_sec": t_sec(at), "phase": event.get("phase", ""),
            "task_id": step[0], "step_id": step[1], "run_id": event.get("runId", ""),
            "running_content_hash": event.get("runningContentHash", ""), "device_elapsed_ms": event.get("elapsedMs", ""),
            **{key: event.get(key, "") for key in SENSOR_KEYS},
            "acceleration_magnitude": round(math.sqrt(ax * ax + ay * ay + az * az)),
            "skipped_samples": event.get("skippedSamples", ""), "sim": event.get("sim", ""),
        })
    write_csv(out / "sensors.csv", sensors,
              ["time_local", "t_sec", "phase", "task_id", "step_id", "run_id", "running_content_hash",
               "device_elapsed_ms", *SENSOR_KEYS, "acceleration_magnitude", "skipped_samples", "sim"])

    boots = [e for e in makecode if e["type"] == "boot"]
    end_of_log = parse_time(makecode[-1]["at"]) if makecode else None
    runs = []
    for index, boot in enumerate(boots):
        at = parse_time(boot["at"])
        until = parse_time(boots[index + 1]["at"]) if index + 1 < len(boots) else end_of_log
        samples = [s for s in sensors if s["run_id"] == boot.get("runId")]
        step = clock.at(at)
        runs.append({
            "run_index": index + 1, "boot_time_local": local(at), "t_sec": t_sec(at),
            "task_id": step[0], "step_id": step[1], "run_id": boot.get("runId", ""), "sim": boot.get("sim", ""),
            "running_content_hash": boot.get("runningContentHash", ""),
            "code_file": code_files.get(boot.get("runningContentHash", ""), ""),
            "duration_sec": round((until - at).total_seconds(), 1) if until else "",
            "sensor_samples": len(samples),
            "skipped_samples": sum(s["skipped_samples"] or 0 for s in samples),
            "max_acceleration_magnitude": max((s["acceleration_magnitude"] for s in samples), default=""),
            "button_a_samples": sum(1 for s in samples if s["buttonA"]),
            "button_b_samples": sum(1 for s in samples if s["buttonB"]),
        })
    write_csv(out / "runs.csv", runs, list(runs[0]) if runs else ["run_index"])

    # steps.csv: one row per step with time spent and activity inside it
    order = list(dict.fromkeys(step for _, step in clock.steps))
    step_rows = []
    for step_id in order:
        intervals = []
        for i, (_, sid) in enumerate(clock.steps):
            if sid == step_id:
                end = clock.times[i + 1] if i + 1 < len(clock.times) else parse_time(session["completed_at"]) or end_of_log
                intervals.append((clock.times[i], end))
        inside = lambda when: when and any(a <= when < b for a, b in intervals if b)
        step_problem = [e for e in problem if e["step_id"] == step_id or (step_id == "arrange" and e["task_id"] in ("arrange", "free-creation"))]
        step_code = [s for s in snapshots if s["step_id"] == step_id]
        step_rows.append({
            "step_id": step_id, "task_id": next((t for t, s in clock.steps if s == step_id), ""),
            "first_viewed_local": local(intervals[0][0]), "visits": len(intervals),
            "time_on_step_sec": round(sum((b - a).total_seconds() for a, b in intervals if b), 1),
            "result": "completed" if any(e["event_type"] == "step_completed" and e["step_id"] == step_id for e in problem)
            else "skipped" if any(e["event_type"] == "step_skipped" and e["step_id"] == step_id for e in problem) else "",
            "hints_opened": sum(1 for e in step_problem if e["event_type"] in ("hint_opened", "arrange_hint_opened")),
            "answers_opened": sum(1 for e in step_problem if e["event_type"] == "answer_opened"),
            "code_changes": sum(1 for s in step_code if s["type"] == "change"),
            "blocks_at_end": step_code[-1]["bln"] if step_code else "",
            "blocks_added": sum(s["added_blocks"] for s in step_code),
            "blocks_removed": sum(s["removed_blocks"] for s in step_code),
            "boots": sum(1 for b in boots if inside(parse_time(b["at"]))),
            "sensor_samples": sum(1 for s in sensors if s["step_id"] == step_id),
        })
    write_csv(out / "steps.csv", step_rows, list(step_rows[0]) if step_rows else ["step_id"])

    # metrics_per_minute.csv: CRABER-style 1-minute series (state at the end of each minute)
    minutes = []
    end_time = parse_time(session["completed_at"]) or end_of_log or started
    total_minutes = math.ceil((end_time - started).total_seconds() / 60)
    for minute in range(total_minutes):
        lo, hi = minute * 60, (minute + 1) * 60
        upto = [s for s in snapshots if s["t_sec"] < hi]
        current = upto[-1] if upto else None
        within = lambda rows, key="t_sec": [r for r in rows if lo <= r[key] < hi]
        step = clock.at(started + timedelta(seconds=min(hi, (end_time - started).total_seconds())))
        minutes.append({
            "minute": minute + 1, "task_id": step[0], "step_id": step[1],
            **{key: current[key] if current else 0 for key in
               ("bln", "scripts", "executed_blocks", "dead_blocks", "lob_avg", "ccn_avg", "ccn_max", "variables")},
            "edits": len(within(snapshots)), "blocks_added": sum(s["added_blocks"] for s in within(snapshots)),
            "blocks_removed": sum(s["removed_blocks"] for s in within(snapshots)),
            "boots": sum(1 for r in runs if lo <= r["t_sec"] < hi),
            "sensor_samples": len(within(sensors)),
            "hints_opened": sum(1 for e in problem_rows if lo <= e["t_sec"] < hi and e["event_type"].endswith("hint_opened")),
            "answers_opened": sum(1 for e in problem_rows if lo <= e["t_sec"] < hi and e["event_type"] == "answer_opened"),
        })
    write_csv(out / "metrics_per_minute.csv", minutes, list(minutes[0]) if minutes else ["minute"])

    # timeline.csv: both sources in one light-weight, time-ordered table
    timeline = [{
        "time": parse_time(e["client_timestamp"]), "source": "problem_site", "event_type": e["event_type"],
        "phase": "", "task_id": e["task_id"] or "", "step_id": e["step_id"] or "",
        "detail": json.dumps(e["metadata"], ensure_ascii=False) if e["metadata"] else "",
    } for e in problem]
    snapshot_by_time = {s["time_local"]: s for s in snapshots}
    for e in makecode:
        at = parse_time(e["at"])
        step = clock.at(at)
        if e["type"] == "sensor":
            detail = f"ax={e.get('accelerationX')} ay={e.get('accelerationY')} az={e.get('accelerationZ')} A={e.get('buttonA')} B={e.get('buttonB')}"
        elif e["type"] in ("start", "change"):
            s = snapshot_by_time.get(local(at), {})
            detail = f"BLN={s.get('bln', '')} +{s.get('added_blocks', '')}/-{s.get('removed_blocks', '')} file={s.get('code_file', '')}"
        elif e["type"] == "boot":
            detail = f"run={e.get('runId')} code={code_files.get(e.get('runningContentHash', ''), '')}"
        else:
            detail = ""
        timeline.append({"time": at, "source": "makecode", "event_type": e["type"], "phase": e.get("phase", ""),
                         "task_id": step[0], "step_id": step[1], "detail": detail})
    timeline.sort(key=lambda row: row["time"] or started)
    for row in timeline:
        row["time_local"], row["t_sec"] = local(row["time"]), t_sec(row["time"])
    write_csv(out / "timeline.csv", timeline,
              ["time_local", "t_sec", "source", "event_type", "phase", "task_id", "step_id", "detail"])

    # Edit-Logger-compatible CSV for tools/block-analytics.py and tools/sensor-analytics.py
    logger_rows = []
    for e in makecode:
        row = {key: e.get(key, "") for key in LOGGER_CSV_HEADERS}
        row["files"] = " ".join(e.get("files") or [])
        row["blockChanges"] = json.dumps(e["blockChanges"], ensure_ascii=False) if e.get("blockChanges") else ""
        logger_rows.append(row)
    write_csv(out / "makecode-logger.csv", logger_rows, LOGGER_CSV_HEADERS)

    sensor_gaps = []
    for a, b in zip(sensors, sensors[1:]):
        if b["t_sec"] - a["t_sec"] > 60:
            sensor_gaps.append({"from": a["time_local"], "to": b["time_local"], "seconds": round(b["t_sec"] - a["t_sec"])})
    summary = {
        "participant_id": session["participant_id"], "session_id": session_id, "status": session["status"],
        "started_local": local(started), "completed_local": local(parse_time(session["completed_at"])),
        "duration_min": round((parse_time(session["completed_at"]) - started).total_seconds() / 60, 1) if session["completed_at"] else None,
        "task_versions": sorted({e["task_version"] for e in problem}),
        "problem_events": len(problem), "makecode_events": len(makecode),
        "makecode_event_types": dict(Counter(e["type"] for e in makecode)),
        "makecode_by_phase": dict(Counter(f"{e['type']}:{e.get('phase', '')}" for e in makecode)),
        "logger_sessions": sorted({e.get("sessionId", "") for e in makecode}),
        "code_snapshots": len(snapshots), "unique_code_versions": len(code_files), "runs": len(runs),
        "sensor_samples": len(sensors), "sensor_samples_skipped_as_idle": sum(s["skipped_samples"] or 0 for s in sensors),
        "sensor_gaps_over_60s": sensor_gaps,
        "steps_completed": [r["step_id"] for r in step_rows if r["result"] == "completed"],
        "generated_at": local(datetime.now(timezone.utc)),
    }
    write_json(out / "summary.json", summary)
    write_json(out / "raw" / "session.json", dict(session))
    (out / "README.md").write_text(readme(summary), encoding="utf-8")
    return out


def readme(summary: dict) -> str:
    return f"""# 実験データ {summary['participant_id']}

- 実施: {summary['started_local']} 〜 {summary['completed_local']}（{summary['duration_min']}分）
- 教材バージョン: {', '.join(summary['task_versions'])}
- 問題サイトのイベント: {summary['problem_events']}件 / MakeCodeのイベント: {summary['makecode_events']}件
- コードのスナップショット: {summary['code_snapshots']}件（異なるコード {summary['unique_code_versions']}種類） / 実行（書き込み・リセット）: {summary['runs']}回
- センサー: {summary['sensor_samples']}件（静止中として省略 {summary['sensor_samples_skipped_as_idle']}件）
- 60秒以上センサーが途切れた区間: {len(summary['sensor_gaps_over_60s'])}件（`summary.json` を参照）

時刻はすべてPCのローカル時刻、`t_sec` は実験開始からの秒数です。MakeCode側のイベントには、その時点で問題サイトに表示していたステップ（`task_id` / `step_id`）を付けています。
CSVはExcelで文字化けしないよう、BOM付きUTF-8で保存しています。

| ファイル | 1行の単位 | 内容 |
|---|---|---|
| `timeline.csv` | イベント | 問題サイトとMakeCodeを時刻順に統合した一覧。まずはこれを見る |
| `steps.csv` | ステップ | 滞在時間、訪問回数、完了・スキップ、ヒント・解答、そのステップ中のコード変更・書き込み・センサー数 |
| `problem_events.csv` | 問題サイトのイベント | 画面遷移、ヒント・解答、完了報告など |
| `metrics_per_minute.csv` | 1分 | 各分の終わりのコード指標と、その1分間の編集・追加/削除ブロック・書き込み・センサー・ヒント数。推移グラフ用 |
| `code_snapshots.csv` | コードの保存 | コード指標（下記）、追加・削除されたブロック数、`code/` 内のファイル |
| `block_type_changes.csv` | 保存1回×ブロック種類 | どの種類のブロックが何個増えた・減ったか |
| `runs.csv` | 書き込み・リセット1回 | 動いていたコード、実行時間、センサー数、ボタン操作 |
| `sensors.csv` | センサー値 | 加速度・明るさ・ボタンなど（`phase`: `running`=書き込み後、`editing`=書き換え中で実機は前のコード） |
| `code/` | コードの版 | 各版の `main.ts` と `main.blocks`（`NNNN_時刻_ハッシュ`） |
| `makecode-logger.csv` | MakeCodeのイベント | Edit LoggerのExport CSVと同じ形式。`tools/block-analytics.py` / `tools/sensor-analytics.py` で読める |
| `raw/` | — | DBから取り出した元データ（JSON） |
| `summary.json` | — | 上記の集計値 |

## コード指標（槇原ら 2022 のコードメトリクスをMakeCode向けに調整）

| 列 | 意味 |
|---|---|
| `bln` | BLN：置かれているブロックの総数（数値などのシャドウは除く。つながっていないブロックも含む） |
| `scripts` | 実行されるスクリプト（最初だけ・ずっと・各イベント）の数。Scratchのスプライト数（SPN）の代わり |
| `executed_blocks` / `lob_avg` | 実行されるブロック数 / スクリプトあたりの平均（LOB） |
| `dead_blocks` | どこにもつながっておらず実行されないブロック数（試行錯誤の置き場） |
| `ccn_avg` / `ccn_max` | CCN：スクリプトごとの 1＋条件分岐＋繰り返し の平均 / 最大 |
| `added_blocks` / `removed_blocks` | 直前の保存からブロック種類ごとの個数の増減を足したもの |

ロガーの生データにある `blockChanges` は、MakeCodeがブロックIDを保存しないため文書内の順番で対応付けており、追加・削除が実際より大きく出ます。分析には上の `added_blocks` / `removed_blocks` を使ってください。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session", nargs="?", help="participant ID, export folder name or session ID")
    parser.add_argument("--all", action="store_true", help="build every session")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    for session in select_sessions(db, args.session, args.all):
        print(build(db, session, args.out))


if __name__ == "__main__":
    main()
