#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import pandas as pd
except ImportError as error:
    raise SystemExit(
        f"Missing dependency: {error.name}\n"
        "Run: python3 -m pip install -r tools/requirements.txt"
    ) from error

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "logs" / "20260702.csv"


def load_block_events(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["type"].ne("sensor")].copy()
    df["at"] = pd.to_datetime(df["at"], utc=True, errors="coerce")
    df["totalBlocks"] = pd.to_numeric(df["totalBlocks"], errors="coerce")
    df["eventIndex"] = range(len(df))
    return df


def print_summary(events: pd.DataFrame) -> None:
    summary = pd.DataFrame(
        [
            {"metric": "events", "value": len(events)},
            {"metric": "sessions", "value": events["sessionId"].nunique()},
            {"metric": "start", "value": int(events["type"].eq("start").sum())},
            {"metric": "change", "value": int(events["type"].eq("change").sum())},
            {"metric": "stop", "value": int(events["type"].eq("stop").sum())},
            {"metric": "maxTotalBlocks", "value": int(events["totalBlocks"].max()) if events["totalBlocks"].notna().any() else 0},
        ]
    )
    print(summary.to_string(index=False))


def plot_total_blocks(events: pd.DataFrame) -> bool:
    chart_data = events.dropna(subset=["totalBlocks"])
    if chart_data.empty:
        return False

    fig, ax = plt.subplots(figsize=(8, 4))
    manager = getattr(fig.canvas, "manager", None)
    if manager:
        manager.set_window_title("Block Log")

    ax.plot(chart_data["eventIndex"], chart_data["totalBlocks"], marker="o", linewidth=2)
    ax.set_title("Total Blocks")
    ax.set_xlabel("event index")
    ax.set_ylabel("blocks")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return True


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    events = load_block_events(input_path)

    print(f"block events: {len(events)}")
    print(events["type"].value_counts().to_string())
    print_summary(events)

    if plot_total_blocks(events):
        plt.show()
    else:
        print("totalBlocks data not found")


if __name__ == "__main__":
    main()
