"""Load micro:bit experiment datasets as pandas DataFrames.

Datasets are built by ``tools/build-dataset.py`` into
``microbit-research-website/backend/data/datasets/<開始日時>_<参加者ID>/``.

    import mblog
    ds = mblog.load("P-5165")        # participant ID or folder name; latest when omitted
    ds.steps                         # one row per step
    mblog.plot_blocks(ds)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT / "microbit-research-website" / "backend" / "data" / "datasets"

STEP_LABELS = {
    "before_tasks": "開始前", "T1": "準備", "T2": "アイコン表示", "T3": "ボタン", "T4": "動作確認",
    "G1": "ボール表示", "G2": "左右に動かす", "G3": "上下に動かす", "G4": "ゴール表示", "G5": "ゴール判定",
    "G6": "やり直し", "G7": "実機で遊ぶ", "arrange": "自由アレンジ", "finished": "終了",
}
HELP_EVENTS = ("hint_opened", "answer_opened", "arrange_hint_opened")


def use_japanese_font() -> str | None:
    """Pick the first installed Japanese font so labels do not render as boxes."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", "Noto Sans JP",
                 "Yu Gothic", "IPAexGothic", "Meiryo"):
        if name in installed:
            plt.rcParams["font.family"] = name
            return name
    return None


use_japanese_font()


def _csv(path: Path, time_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    for col in time_cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "t_sec" in df:
        df["t_min"] = df["t_sec"] / 60
    return df


@dataclass
class Dataset:
    path: Path
    summary: dict = field(repr=False)

    @property
    def name(self) -> str:
        return self.path.name

    @cached_property
    def problem(self) -> pd.DataFrame:
        df = _csv(self.path / "problem_events.csv", ("time_local",))
        if "metadata" in df:
            df["metadata"] = df["metadata"].fillna("{}").map(json.loads)
        return df

    @cached_property
    def snapshots(self) -> pd.DataFrame:
        return _csv(self.path / "code_snapshots.csv", ("time_local",))

    @cached_property
    def minutes(self) -> pd.DataFrame:
        return _csv(self.path / "metrics_per_minute.csv")

    @cached_property
    def steps(self) -> pd.DataFrame:
        df = _csv(self.path / "steps.csv", ("first_viewed_local",))
        if not df.empty:
            df["label"] = df["step_id"].map(STEP_LABELS)
            df["time_on_step_min"] = df["time_on_step_sec"] / 60
        return df

    @cached_property
    def runs(self) -> pd.DataFrame:
        return _csv(self.path / "runs.csv", ("boot_time_local",))

    @cached_property
    def sensors(self) -> pd.DataFrame:
        return _csv(self.path / "sensors.csv", ("time_local",))

    @cached_property
    def timeline(self) -> pd.DataFrame:
        return _csv(self.path / "timeline.csv", ("time_local",))

    @cached_property
    def block_type_changes(self) -> pd.DataFrame:
        return _csv(self.path / "block_type_changes.csv", ("time_local",))

    @cached_property
    def raw_makecode(self) -> list[dict]:
        return json.loads((self.path / "raw" / "makecode-events.json").read_text(encoding="utf-8"))

    def code(self, snapshot_index: int) -> str:
        """The main.ts of one code snapshot (1-based, as in code_snapshots.csv)."""
        row = self.snapshots.loc[self.snapshots["snapshot_index"] == snapshot_index].iloc[0]
        return (self.path / row["code_file"]).read_text(encoding="utf-8")

    @cached_property
    def step_bands(self) -> pd.DataFrame:
        """Time ranges (minutes) in which each problem-site step was on screen."""
        marks = []
        for _, r in self.problem.sort_values("t_sec").iterrows():
            if r["event_type"] == "step_viewed" and isinstance(r["step_id"], str):
                marks.append((r["step_id"], r["t_sec"]))
            elif r["event_type"] == "task_started" and r.get("task_id") == "arrange":
                marks.append(("arrange", r["t_sec"]))
            elif r["event_type"] == "task_completed" and r["step_id"] == "G7":
                marks.append(("arrange", r["t_sec"]))
            elif r["event_type"] == "session_completed":
                marks.append(("finished", r["t_sec"]))
        end = self.summary.get("duration_min", 0) * 60 or (marks[-1][1] if marks else 0)
        rows = []
        for i, (step, start) in enumerate(marks):
            stop = marks[i + 1][1] if i + 1 < len(marks) else end
            if step == "finished" or stop <= start:
                continue
            if rows and rows[-1]["step_id"] == step:
                rows[-1]["end_min"] = stop / 60
            else:
                rows.append({"step_id": step, "start_min": start / 60, "end_min": stop / 60})
        return pd.DataFrame(rows)


def list_datasets(root: Path = DATASETS_DIR) -> pd.DataFrame:
    rows = []
    for summary_path in sorted(root.glob("*/summary.json")):
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        rows.append({"name": summary_path.parent.name, "participant_id": s["participant_id"],
                     "started": s["started_local"], "duration_min": s["duration_min"],
                     "problem_events": s["problem_events"], "makecode_events": s["makecode_events"]})
    return pd.DataFrame(rows)


def load(key: str | None = None, root: Path = DATASETS_DIR) -> Dataset:
    """Load by participant ID, folder name or session ID; the latest dataset when omitted."""
    candidates = sorted(root.glob("*/summary.json"))
    if not candidates:
        raise FileNotFoundError(f"No dataset under {root}. Run: python3 tools/build-dataset.py --all")
    for summary_path in reversed(candidates):
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        if key is None or key in (summary_path.parent.name, s["participant_id"], s["session_id"]):
            return Dataset(summary_path.parent, s)
    raise KeyError(f"No dataset matches {key!r}: {[p.parent.name for p in candidates]}")


# ---------- derived tables ----------

def edit_run_cycles(ds: Dataset, moving_threshold_mg: float = 150) -> pd.DataFrame:
    """One row per run: edits made before it, how long it was tried, and how the board was handled."""
    snaps, sensors, runs = ds.snapshots, ds.sensors, ds.runs.sort_values("t_sec").reset_index(drop=True)
    rows, previous = [], 0.0
    for i, run in runs.iterrows():
        start = run["t_sec"]
        stop = runs.loc[i + 1, "t_sec"] if i + 1 < len(runs) else np.inf
        after = snaps[(snaps["t_sec"] >= start) & (snaps["t_sec"] < stop)]
        during = sensors[(sensors["t_sec"] >= start) & (sensors["t_sec"] < stop)]
        rows.append({
            "run_index": run["run_index"], "step_id": run["step_id"], "t_min": start / 60,
            "edits_before": int(((snaps["t_sec"] >= previous) & (snaps["t_sec"] < start)).sum()),
            "tried_for_sec": (after["t_sec"].iloc[0] - start) if len(after) else np.nan,
            "moving_samples": int(((during["acceleration_magnitude"] - 1000).abs() > moving_threshold_mg).sum()),
            "button_samples": int(((during["buttonA"] == 1) | (during["buttonB"] == 1)).sum()),
        })
        previous = start
    return pd.DataFrame(rows)


def struggle_minutes(ds: Dataset, window: int = 3, min_churn: int = 6, max_growth: int = 1) -> pd.DataFrame:
    """Minutes that look like unproductive trial and error (cf. Makihara et al. 2022):
    many blocks added/removed in the window while executed blocks barely grow and nothing is run."""
    m = ds.minutes.copy()
    m["churn"] = (m["blocks_added"] + m["blocks_removed"]).rolling(window, min_periods=1).sum()
    m["executed_growth"] = m["executed_blocks"].diff(window).fillna(m["executed_blocks"])
    m["boots_in_window"] = m["boots"].rolling(window, min_periods=1).sum()
    m["struggle"] = (m["churn"] >= min_churn) & (m["executed_growth"] <= max_growth) & (m["boots_in_window"] == 0)
    return m[["minute", "step_id", "churn", "executed_growth", "dead_blocks", "boots_in_window", "struggle"]]


# ---------- plots ----------

def _bands(ax, ds: Dataset, label: bool = True) -> None:
    for i, b in ds.step_bands.reset_index(drop=True).iterrows():
        ax.axvspan(b["start_min"], b["end_min"], color="0.5", alpha=0.12 if i % 2 else 0.05, lw=0)
        if label and b["end_min"] - b["start_min"] > 1.5:
            ax.text(b["start_min"] + 0.2, 1.01, b["step_id"].replace("arrange", "AR"), transform=ax.get_xaxis_transform(),
                    fontsize=8, color="0.35", va="bottom")


def plot_blocks(ds: Dataset, ax=None):
    """BLN / executed / unattached blocks over time, with steps, runs (▼) and help (◆)."""
    ax = ax or plt.subplots(figsize=(12, 4))[1]
    s = ds.snapshots
    _bands(ax, ds)
    ax.step(s["t_min"], s["bln"], where="post", color="0.1", lw=2, label="置いているブロック（BLN）")
    ax.step(s["t_min"], s["executed_blocks"], where="post", color="0.45", lw=1.6, label="実行されるブロック")
    ax.step(s["t_min"], s["dead_blocks"], where="post", color="0.6", lw=1.4, ls="--", label="未接続のブロック")
    top = max(s["bln"].max(), 1) * 1.08
    ax.scatter(ds.runs["t_min"], [top] * len(ds.runs), marker="v", color="0.2", s=28, label="書き込み", zorder=3)
    help_rows = ds.problem[ds.problem["event_type"].isin(HELP_EVENTS)]
    ax.scatter(help_rows["t_min"], [top * 1.05] * len(help_rows), marker="D", color="0.5", s=22, label="ヒント・解答", zorder=3)
    ax.set(xlabel="経過時間（分）", ylabel="ブロック数", ylim=(0, top * 1.12))
    ax.legend(loc="upper left", fontsize=8, ncol=5, frameon=False, bbox_to_anchor=(0, -0.15))
    ax.spines[["top", "right"]].set_visible(False)
    return ax


def plot_step_time(ds: Dataset, ax=None):
    steps = ds.steps[ds.steps["step_id"] != "finished"]
    ax = ax or plt.subplots(figsize=(8, 4.5))[1]
    longest = steps["time_on_step_min"].idxmax()
    colors = ["0.1" if i == longest else "0.75" for i in steps.index]
    ax.barh(steps["step_id"] + " " + steps["label"].fillna(""), steps["time_on_step_min"], color=colors)
    ax.invert_yaxis()
    ax.set(xlabel="滞在時間（分）")
    ax.spines[["top", "right"]].set_visible(False)
    return ax


def plot_sensors(ds: Dataset, ax=None):
    ax = ax or plt.subplots(figsize=(12, 3.5))[1]
    s = ds.sensors
    _bands(ax, ds)
    for phase, color in (("editing", "0.65"), ("running", "0.1")):
        part = s[s["phase"] == phase]
        ax.scatter(part["t_min"], part["acceleration_magnitude"], s=6, color=color, label=phase)
    ax.axhline(1000, color="0.5", lw=0.8, ls=":")
    ax.set(xlabel="経過時間（分）", ylabel="加速度の大きさ（mg）")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return ax
