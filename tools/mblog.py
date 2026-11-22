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
    "before_tasks": "開始前",
    "T1": "準備",
    "T2": "アイコン表示",
    "T3": "確認方法",
    "T4": "ボタン",
    "T5": "変数",
    "T6": "条件分岐",
    "T7": "点灯",
    "T8": "ちょうどいい傾き",
    "intro": "ゲーム説明",
    "G1": "ボール表示",
    "G2": "左右に動かす",
    "G3": "上下に動かす",
    "G4": "ゴール表示",
    "G5": "ゴール判定",
    "G6": "やり直し",
    "G7": "通して遊ぶ",
    "arrange": "自由アレンジ",
    "finished": "終了",
}
HELP_EVENTS = ("hint_opened", "answer_opened", "arrange_hint_opened")


def use_japanese_font() -> str | None:
    """Pick the first installed Japanese font so labels do not render as boxes."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in (
        "Hiragino Sans",
        "Hiragino Kaku Gothic ProN",
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "Yu Gothic",
        "IPAexGothic",
        "Meiryo",
    ):
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
            elif r["event_type"] == "task_intro_viewed":
                marks.append(("intro", r["t_sec"]))
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
        rows.append(
            {
                "name": summary_path.parent.name,
                "participant_id": s["participant_id"],
                "started": s["started_local"],
                "duration_min": s["duration_min"],
                "problem_events": s["problem_events"],
                "makecode_events": s["makecode_events"],
            }
        )
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
        rows.append(
            {
                "run_index": run["run_index"],
                "step_id": run["step_id"],
                "t_min": start / 60,
                "edits_before": int(((snaps["t_sec"] >= previous) & (snaps["t_sec"] < start)).sum()),
                "tried_for_sec": (after["t_sec"].iloc[0] - start) if len(after) else np.nan,
                "moving_samples": int(((during["acceleration_magnitude"] - 1000).abs() > moving_threshold_mg).sum()),
                "button_samples": int(((during["buttonA"] == 1) | (during["buttonB"] == 1)).sum()),
            }
        )
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


# ---------- sensing: code thresholds vs. sensor values ----------

# センサーを読む式と、sensors.csv の列。コード中の「式 比較 数字」を閾値として読む
SENSOR_EXPRESSIONS = {
    r"input\.acceleration\(Dimension\.X\)": "accelerationX",
    r"input\.acceleration\(Dimension\.Y\)": "accelerationY",
    r"input\.acceleration\(Dimension\.Z\)": "accelerationZ",
    r"input\.acceleration\(Dimension\.Strength\)": "acceleration_magnitude",
    r"input\.lightLevel\(\)": "lightLevel",
    r"input\.soundLevel\(\)": "soundLevel",
}
SENSOR_LABELS = {
    "accelerationX": "加速度 x",
    "accelerationY": "加速度 y",
    "accelerationZ": "加速度 z",
    "acceleration_magnitude": "加速度の強さ",
    "lightLevel": "明るさ",
    "soundLevel": "音の大きさ",
}
_FLIP = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "==", "!=": "!="}
_NUMBER = r"(-?\d+(?:\.\d+)?)"
_OP = r"(>=|<=|==|!=|>|<)"


def thresholds(ts: str) -> list[dict]:
    """Comparisons between a sensor reading and a number in a program, e.g. ``input.acceleration(Dimension.X) > 500``.
    Comparisons against variables are not read."""
    import re

    found = []
    for expr, column in SENSOR_EXPRESSIONS.items():
        for m in re.finditer(rf"{expr}\s*{_OP}\s*{_NUMBER}", ts):
            found.append((column, m.group(1), float(m.group(2))))
        for m in re.finditer(rf"{_NUMBER}\s*{_OP}\s*{expr}", ts):
            found.append((column, _FLIP[m.group(2)], float(m.group(1))))
    return [
        {"sensor": c, "op": op, "value": v, "condition": f"{SENSOR_LABELS[c]} {op} {v:g}"}
        for c, op, v in dict.fromkeys(found)
    ]


def _satisfies(values: pd.Series, op: str, value: float) -> pd.Series:
    return {
        ">": values > value,
        "<": values < value,
        ">=": values >= value,
        "<=": values <= value,
        "==": values == value,
        "!=": values != value,
    }[op]


def sensing_runs(ds: Dataset, always_ratio: float = 0.8) -> pd.DataFrame:
    """One row per (device run, threshold in the running code).

    - reached: 実際のセンサー値が条件を満たしたか（①閾値に届いたか）
    - gap: 一番条件に近づいた値と閾値の差。プラスなら超えた分、マイナスなら足りなかった分
    - changed: 直前の実行から新しく入った・数字が変わった条件か。changed かつ reached でなければ「直したところを試していない」（②）
    - state: 届かない / 届いた / ほぼ常に成立（reached_ratio が always_ratio 以上。置いたままでも成り立つ条件で、記号や向きの間違いが疑われる）
    - both_sides: 成り立つ時と成り立たない時の両方があったか。「明るさ > 0」のように普段は成り立つのが正しい条件では、
      ほぼ常に成立でも both_sides が True なら、成り立たない側（暗くする）も試している
    - switches: 成り立つ / 成り立たないが切り替わった回数（値が数字をまたいだ回数）
    - flipped: 直前の実行に、同じセンサー・同じ数字で不等号だけ逆の条件があったか（向きを直した）
    - label: 成立率と切り替わり回数から付けるラベル（label_run を参照）
    """
    runs = ds.runs
    if runs.empty:
        return pd.DataFrame()
    runs = runs[(runs["sim"].astype(str) != "True") & runs["code_file"].notna()].sort_values("t_sec")
    sensors = ds.sensors
    rows, previous = [], set()
    for _, run in runs.iterrows():
        conds = thresholds((ds.path / run["code_file"]).read_text(encoding="utf-8"))
        samples = sensors[sensors["run_id"] == run["run_id"]]
        keys = {(c["sensor"], c["op"], c["value"]) for c in conds}
        for c in conds:
            values = samples[c["sensor"]].dropna()
            ok = _satisfies(values, c["op"], c["value"]) if len(values) else pd.Series(dtype=bool)
            if c["op"] in (">", ">="):
                extreme = values.max() if len(values) else np.nan
                gap = extreme - c["value"]
            elif c["op"] in ("<", "<="):
                extreme = values.min() if len(values) else np.nan
                gap = c["value"] - extreme
            else:
                extreme, gap = np.nan, np.nan
            rows.append(
                {
                    "run_index": run["run_index"],
                    "t_min": run["t_sec"] / 60,
                    "step_id": run["step_id"],
                    "tried_sec": run["duration_sec"],
                    "samples": len(values),
                    **c,
                    "closest": extreme,
                    "gap": gap,
                    "reached": bool(ok.any()) if len(values) else False,
                    "reached_ratio": float(ok.mean()) if len(values) else np.nan,
                    "both_sides": bool(ok.any() and not ok.all()) if len(values) else False,
                    "changed": (c["sensor"], c["op"], c["value"]) not in previous,
                    "switches": int((ok.astype(int).diff().abs() == 1).sum()) if len(values) else 0,
                    "flipped": any(
                        k[0] == c["sensor"] and k[2] == c["value"] and k[1] == _FLIP[c["op"]] for k in previous
                    ),
                }
            )
            r = rows[-1]
            r["state"] = (
                "届かない" if not r["reached"] else "ほぼ常に成立" if r["reached_ratio"] >= always_ratio else "届いた"
            )
            r["label"] = label_run(r)
        previous = keys
    return pd.DataFrame(rows)


RUN_LABELS = {
    "境目を試せた": "#2e8b57",
    "試していない": "#b0b0b0",
    "あと少し届かない": "#e08e0b",
    "常に成立": "#c0392b",
    "ほぼ成立（要確認）": "#8e44ad",
}


def label_run(r: dict, near: float = 0.2, mostly: float = 0.5) -> str:
    """書き込み 1 回 × 条件 1 つに、成立率と切り替わり回数からラベルを付ける。

    - 一度も成り立たない: 足りなかった分が数字の near 割以内なら「あと少し届かない」、それより遠ければ「試していない」
    - ずっと成り立つ（切り替わり 0 回）: 「常に成立」（記号・向きの間違い、ありえない数字）
    - 切り替わりあり、成立率が mostly 以上: 「ほぼ成立（要確認）」（向きの間違い、または普段は成り立つのが正しい条件）
    - 切り替わりあり、成立率が mostly 未満: 「境目を試せた」
    """
    if not r["reached"]:
        return "あと少し届かない" if r["gap"] >= -near * max(abs(r["value"]), 100) else "試していない"
    if r["switches"] == 0:
        return "常に成立"
    return "ほぼ成立（要確認）" if r["reached_ratio"] >= mostly else "境目を試せた"


def plot_run_labels(ds: Dataset, changed_only: bool = False):
    """書き込み 1 回 × 条件 1 つを 1 点として、横軸に成立率、縦軸に切り替わり回数をとり、ラベルで色分けする。
    塗りつぶしは数字を変えた（新しく入った）条件、白抜きは前の書き込みから変わっていない条件。"""
    sr = sensing_runs(ds)
    if changed_only:
        sr = sr[sr["changed"]]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    rng = np.random.default_rng(0)
    for label, color in RUN_LABELS.items():
        part = sr[sr["label"] == label]
        if part.empty:
            continue
        flat = (part["switches"] == 0).to_numpy()  # 切り替わり 0 回の点は重なるので左右にもずらす
        x = part["reached_ratio"] * 100 + np.where(flat, rng.uniform(-2.5, 2.5, len(part)), 0)
        y = part["switches"] + rng.uniform(-0.25, 0.25, len(part))
        ch = part["changed"].to_numpy()
        ax.scatter(x[ch], y[ch], s=46, color=color, label=f"{label}（{len(part)}）", zorder=3)
        ax.scatter(x[~ch], y[~ch], s=46, facecolors="white", edgecolors=color, lw=1.4, zorder=3)
    ax.set_xlabel("成立率（動かしていた時間のうち、条件が成り立っていた割合 %）")
    ax.set_ylabel("切り替わり回数（成り立つ ⇄ 成り立たない）")
    ax.set_xlim(-4, 104)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=9, frameon=False, loc="upper right")
    fig.tight_layout()
    return fig


_SHORT = {
    "accelerationX": "x",
    "accelerationY": "y",
    "accelerationZ": "z",
    "acceleration_magnitude": "強さ",
    "lightLevel": "明るさ",
    "soundLevel": "音",
}


def focus_runs(ds: Dataset) -> pd.DataFrame:
    """書き込みごとに「今いじっている条件」だけを残す。

    その書き込みで新しく入った・数字や向きが変わった条件があればそれ。なければ（同じコードを書き込み直したときなど）、
    同じステップの中で直前にいじった条件のうち、まだコードに残っているものを引き継ぐ。ステップが変わったら引き継がない。
    """
    sr = sensing_runs(ds)
    if sr.empty:
        return sr
    rows, focus, step = [], set(), None
    for run_index, part in sr.groupby("run_index", sort=False):
        keys = set(zip(part["sensor"], part["op"], part["value"]))
        changed = set(zip(*[part.loc[part["changed"], c] for c in ("sensor", "op", "value")]))
        if part["step_id"].iloc[0] != step:
            focus, step = set(), part["step_id"].iloc[0]
        focus = changed or (focus & keys)
        rows.append(part[[k in focus for k in zip(part["sensor"], part["op"], part["value"])]])
    return pd.concat(rows, ignore_index=True)


def plot_focus_sequence(ds: Dataset):
    """ステップごとに、書き込み順に「今いじっている条件」のラベルを色で並べる。
    1 マスが書き込み 1 回。いじっている条件が複数あるときはマスを縦に分ける。"""
    fr = focus_runs(ds)
    sr = sensing_runs(ds)
    steps = list(dict.fromkeys(sr["step_id"]))
    width = max(sr.groupby("step_id")["run_index"].nunique())
    fig, ax = plt.subplots(figsize=(1.25 * width + 2.5, 0.95 * len(steps) + 1.2))
    for row, step in enumerate(steps):
        for col, run_index in enumerate(dict.fromkeys(sr.loc[sr["step_id"] == step, "run_index"])):
            run = fr[fr["run_index"] == run_index]
            n = len(run)
            if n == 0:
                ax.add_patch(plt.Rectangle((col + 0.05, row + 0.1), 0.9, 0.78, fill=False, ec="0.75", lw=1, ls="--"))
                ax.text(col + 0.5, row + 0.5, "条件の変更なし", ha="center", va="center", fontsize=8, color="0.5")
            for k, (_, r) in enumerate(run.iterrows()):
                y0 = row + 0.1 + k * 0.8 / n
                ax.add_patch(plt.Rectangle((col + 0.05, y0), 0.9, 0.8 / n - 0.02, color=RUN_LABELS[r["label"]], lw=0))
                ax.text(
                    col + 0.5,
                    y0 + 0.4 / n,
                    f"{_SHORT.get(r['sensor'], r['sensor'])} {r['op']} {r['value']:g}",
                    ha="center",
                    va="center",
                    fontsize=8 if n < 3 else 6.5,
                    color="white",
                )
    ax.set_xlim(0, width)
    ax.set_ylim(len(steps), 0)
    ax.set_yticks([i + 0.5 for i in range(len(steps))], [STEP_LABELS.get(s, s) for s in steps])
    ax.set_xticks([i + 0.5 for i in range(width)], [f"{i + 1} 回目" for i in range(width)], fontsize=8)
    ax.tick_params(length=0)
    ax.spines[:].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in RUN_LABELS.values()]
    ax.legend(
        handles,
        list(RUN_LABELS),
        ncol=len(RUN_LABELS),
        fontsize=8,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
    )
    ax.set_xlabel(
        "ステップ内の書き込み（いじった条件だけ。同じコードの書き込み直しは、直前にいじった条件を引き継ぐ）", fontsize=8
    )
    fig.tight_layout()
    return fig


def sensing_summary(ds: Dataset) -> pd.DataFrame:
    """Per run: how many thresholds there were, how many were reached, and whether changed ones were tried."""
    sr = sensing_runs(ds)
    if sr.empty:
        return sr
    return (
        sr.groupby(["run_index", "t_min", "step_id", "tried_sec"], sort=False)
        .agg(
            conditions=("condition", "size"),
            reached=("reached", "sum"),
            changed=("changed", "sum"),
            changed_untried=("changed", lambda c: int((c & ~sr.loc[c.index, "reached"]).sum())),
            not_reached=("condition", lambda c: ", ".join(c[~sr.loc[c.index, "reached"]])),
            always_true=("condition", lambda c: ", ".join(c[sr.loc[c.index, "state"] == "ほぼ常に成立"])),
        )
        .reset_index()
    )


def plot_sensing(ds: Dataset, steps: list[str] | None = None, sensors: list[str] | None = None):
    """センサーごとに、値を点、そのとき動いていたコードの閾値を横線（実線: 届いた / 点線: 届かなかった）、書き込みを縦線で描く。
    steps を渡すとその区間だけ拡大する。"""
    sensors = sensors or list(SENSOR_LABELS)
    s = ds.sensors
    sr = sensing_runs(ds)
    runs = ds.runs.sort_values("t_sec")
    xlim = None
    if steps:
        b = ds.step_bands[ds.step_bands["step_id"].isin(steps)]
        if len(b):
            xlim = (b["start_min"].min(), b["end_min"].max())
    fig, axes = plt.subplots(len(sensors), 1, figsize=(12, 1.9 * len(sensors) + 0.6), sharex=True)
    axes = np.atleast_1d(axes)
    for i, (ax, col) in enumerate(zip(axes, sensors)):
        _bands(ax, ds, label=i == 0)
        part = s if xlim is None else s[(s["t_min"] >= xlim[0]) & (s["t_min"] <= xlim[1])]
        ax.scatter(part["t_min"], part[col], s=3, color="0.35", lw=0, zorder=2)
        for t in runs["t_min"]:
            ax.axvline(t, color="0.75", lw=0.6, zorder=1)
        if not sr.empty:
            for _, r in sr[sr["sensor"] == col].iterrows():
                start = r["t_min"]
                stop = start + (r["tried_sec"] if pd.notna(r["tried_sec"]) else 0) / 60
                color = "#c0392b" if r["op"] in (">", ">=") else "#2c6fbb"
                ax.hlines(
                    r["value"], start, max(stop, start + 0.05), colors=color, lw=1.6, ls="-" if r["reached"] else ":"
                )
        ax.set_ylabel(SENSOR_LABELS[col], fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    if xlim:
        axes[-1].set_xlim(xlim)
    axes[-1].set_xlabel(
        "経過時間（分）　縦線: 起動（書き込み）／横線: コードの閾値（赤: >、青: <、点線: 届かなかった）"
    )
    fig.tight_layout()
    return fig


def plot_scene(
    ds: Dataset,
    start_min: float,
    end_min: float,
    sensors: list[str],
    title: str | None = None,
    annotate: list[tuple[str, str, float]] | None = None,
    text: bool = True,
):
    """ある場面（時間の区間）を切り出して、プログラムの変化とセンサー値を重ねて描く。

    - 点: センサー値。そのとき動いていたコードの条件を満たした点は色付き
    - 灰色の細線: 書き込まずに書き換えただけの閾値（エディター上の変化）
    - 色付きの太線: 書き込んで動いていた閾値（赤: >、青: <、点線: 届かなかった）とその状態
    - 縦線: 起動（書き込み）、下の短い線: コード変更
    annotate に (センサー, 記号, 数字) を渡すと、その条件だけに説明を付ける（条件が多いとき用）。
    text=False なら、軸ラベル以外の文字（タイトル・ステップ名・数字の説明・凡例）を描かない。
    """
    s = ds.sensors
    s = s[(s["t_min"] >= start_min) & (s["t_min"] <= end_min)]
    sr = sensing_runs(ds)
    sr = sr[(sr["t_min"] >= start_min - 5) & (sr["t_min"] <= end_min)] if not sr.empty else sr
    runs = ds.runs[(ds.runs["t_min"] >= start_min) & (ds.runs["t_min"] <= end_min)]
    snaps = ds.snapshots.dropna(subset=["code_file"]).assign(t_min=lambda d: d["t_sec"] / 60)
    snaps = snaps[snaps["t_min"] <= end_min].sort_values("t_min")
    edits = []
    for i, (_, row) in enumerate(snaps.iterrows()):
        stop = snaps["t_min"].iloc[i + 1] if i + 1 < len(snaps) else end_min
        if stop < start_min:
            continue
        conds = thresholds((ds.path / row["code_file"]).read_text(encoding="utf-8"))
        edits.append((max(row["t_min"], start_min), min(stop, end_min), conds))

    fig, axes = plt.subplots(len(sensors), 1, figsize=(11, 2.6 * len(sensors) + 1.2), sharex=True)
    axes = np.atleast_1d(axes)
    for i, (ax, col) in enumerate(zip(axes, sensors)):
        _bands(ax, ds, label=False)
        if text and i == 0:
            for _, band in ds.step_bands.iterrows():
                a, b = max(band["start_min"], start_min), min(band["end_min"], end_min)
                if b - a > (end_min - start_min) * 0.08:
                    ax.text(
                        a,
                        1.01,
                        STEP_LABELS.get(band["step_id"], band["step_id"]),
                        fontsize=8,
                        color="0.35",
                        transform=ax.get_xaxis_transform(),
                        va="bottom",
                    )
        for t in runs["t_min"]:
            ax.axvline(t, color="0.6", lw=0.8, zorder=1)
        for a, b, conds in edits:
            for c in conds:
                if c["sensor"] == col:
                    light = "#e6a39b" if c["op"] in (">", ">=") else "#9dbbe0"
                    ax.hlines(c["value"], a, b, colors=light, lw=1.2, zorder=2)
        ax.scatter(s["t_min"], s[col], s=4, color="0.55", lw=0, zorder=3)
        for _, r in sr[sr["sensor"] == col].iterrows():
            a = max(r["t_min"], start_min)
            b = min(r["t_min"] + r["tried_sec"] / 60, end_min)
            if b <= a:
                continue
            color = "#c0392b" if r["op"] in (">", ">=") else "#2c6fbb"
            part = s[(s["t_min"] >= a) & (s["t_min"] <= b)]
            hit = part[_satisfies(part[col], r["op"], r["value"])]
            ax.scatter(hit["t_min"], hit[col], s=7, color=color, lw=0, zorder=4)
            ax.hlines(r["value"], a, b, colors=color, lw=2, ls="-" if r["reached"] else ":", zorder=5)
            notable = r["changed"] or r["state"] != "届いた" or r["reached_ratio"] >= 0.5
            picked = annotate is None or (col, r["op"], r["value"]) in annotate
            if text and notable and picked:
                note = f"{r['op']} {r['value']:g}"
                if r["state"] == "届かない":
                    note += f"\n届かない（{'最大' if r['op'] in ('>', '>=') else '最小'} {r['closest']:g}）"
                elif r["reached_ratio"] >= 0.5:
                    note += f"\n成立 {r['reached_ratio']:.0%}"
                ax.annotate(
                    note,
                    (a, r["value"]),
                    xytext=(2, 3),
                    textcoords="offset points",
                    fontsize=8,
                    color=color,
                    zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8),
                )
        levels = [c["value"] for _, _, conds in edits for c in conds if c["sensor"] == col]
        lo, hi = min([s[col].min(), *levels]), max([s[col].max(), *levels])
        pad = (hi - lo) * 0.18 or 1
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_ylabel(SENSOR_LABELS[col], fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    change_t = [a for a, _, _ in edits if a > start_min]
    axes[-1].plot(change_t, [0] * len(change_t), "|", color="0.3", ms=8, transform=axes[-1].get_xaxis_transform())
    axes[-1].set_xlim(start_min, end_min)
    axes[-1].set_xlabel("経過時間（分）")
    if not text:
        fig.tight_layout()
        return fig
    if title:
        axes[0].set_title(title, fontsize=11, loc="left", pad=14)
    fig.tight_layout(rect=(0, 0.5 / (2.6 * len(sensors) + 1.2), 1, 1))
    fig.text(
        0.01,
        0.01,
        "縦線: 書き込み　濃い線: 動いていた数字（赤: >、青: <、点線: 届かない）　薄い線: 書き込まずに書き換えた数字\n"
        "色付きの点: 条件を満たした値　灰色の点: 満たしていない値　下の短い線: コード変更",
        fontsize=8,
        color="0.3",
    )
    return fig


# ---------- plots ----------


def _bands(ax, ds: Dataset, label: bool = True) -> None:
    for i, b in ds.step_bands.reset_index(drop=True).iterrows():
        ax.axvspan(b["start_min"], b["end_min"], color="0.5", alpha=0.12 if i % 2 else 0.05, lw=0)
        if label and b["end_min"] - b["start_min"] > 1.5:
            ax.text(
                b["start_min"] + 0.2,
                1.01,
                b["step_id"].replace("arrange", "AR"),
                transform=ax.get_xaxis_transform(),
                fontsize=8,
                color="0.35",
                va="bottom",
            )


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
    ax.scatter(
        help_rows["t_min"], [top * 1.05] * len(help_rows), marker="D", color="0.5", s=22, label="ヒント・解答", zorder=3
    )
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
