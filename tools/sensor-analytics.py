#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
except ImportError as error:
    raise SystemExit(
        f"Missing dependency: {error.name}\n"
        "Run: python3 -m pip install -r tools/requirements.txt"
    ) from error

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "logs" / "20260702.csv"
NUMERIC_COLUMNS = [
    "elapsedMs",
    "accelerationX",
    "accelerationY",
    "accelerationZ",
    "lightLevel",
    "temperature",
    "buttonA",
    "buttonB",
    "logoTouch",
    "soundLevel",
    "compassHeading",
]
SUMMARY_COLUMNS = [
    "plotSec",
    "elapsedMs",
    "accelerationX",
    "accelerationY",
    "accelerationZ",
    "lightLevel",
    "temperature",
    "buttonA",
    "buttonB",
    "logoTouch",
    "soundLevel",
    "compassHeading",
    "accelerationMagnitude",
    "tiltPitchDeg",
    "tiltRollDeg",
]


def load_sensor_events(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    sensors = df[df["type"].eq("sensor")].copy()
    sensors["at"] = pd.to_datetime(sensors["at"], utc=True, errors="coerce")

    for column in NUMERIC_COLUMNS:
        if column not in sensors:
            sensors[column] = pd.NA
        sensors[column] = pd.to_numeric(sensors[column], errors="coerce")

    sensors["plotSec"] = sensors["elapsedMs"] / 1000
    if sensors["plotSec"].isna().all() and sensors["at"].notna().any():
        sensors["plotSec"] = (sensors["at"] - sensors["at"].min()).dt.total_seconds()

    sensors["accelerationMagnitude"] = (
        sensors["accelerationX"].pow(2)
        + sensors["accelerationY"].pow(2)
        + sensors["accelerationZ"].pow(2)
    ).pow(0.5)
    sensors["tiltPitchDeg"] = np.degrees(
        np.arctan2(
            -sensors["accelerationX"],
            np.sqrt(sensors["accelerationY"].pow(2) + sensors["accelerationZ"].pow(2)),
        )
    )
    sensors["tiltRollDeg"] = np.degrees(
        np.arctan2(sensors["accelerationY"], sensors["accelerationZ"])
    )
    return sensors


def metric_value(sensors: pd.DataFrame, column: str, fn: str) -> str | float:
    if column not in sensors or not sensors[column].notna().any():
        return ""
    if fn == "mean":
        return round(float(sensors[column].mean()), 3)
    if fn == "max":
        return round(float(sensors[column].max()), 3)
    if fn == "count":
        return int(sensors[column].notna().sum())
    raise ValueError(fn)


def print_summary(sensors: pd.DataFrame) -> None:
    duration = 0.0
    if sensors["plotSec"].notna().sum() >= 2:
        duration = float(sensors["plotSec"].max() - sensors["plotSec"].min())

    first_time = sensors["at"].dropna().min()
    last_time = sensors["at"].dropna().max()
    summary = pd.DataFrame(
        [
            {"metric": "samples", "value": len(sensors)},
            {"metric": "firstTime", "value": first_time.isoformat() if pd.notna(first_time) else ""},
            {"metric": "lastTime", "value": last_time.isoformat() if pd.notna(last_time) else ""},
            {"metric": "durationSec", "value": round(duration, 3)},
            {"metric": "avgLightLevel", "value": metric_value(sensors, "lightLevel", "mean")},
            {"metric": "avgTemperature", "value": metric_value(sensors, "temperature", "mean")},
            {"metric": "maxSoundLevel", "value": metric_value(sensors, "soundLevel", "max")},
            {"metric": "maxAcceleration", "value": metric_value(sensors, "accelerationMagnitude", "max")},
            {"metric": "compassSamples", "value": metric_value(sensors, "compassHeading", "count")},
            {"metric": "buttonAPressedSamples", "value": int(sensors["buttonA"].eq(1).sum())},
            {"metric": "buttonBPressedSamples", "value": int(sensors["buttonB"].eq(1).sum())},
            {"metric": "logoTouchSamples", "value": int(sensors["logoTouch"].eq(1).sum())},
        ]
    )
    print(summary.to_string(index=False))


def plot_series(
    ax,
    sensors: pd.DataFrame,
    columns: list[str],
    title: str,
    ylabel: str,
    *,
    step: bool = False,
) -> bool:
    has_data = False
    for column in columns:
        chart_data = sensors.dropna(subset=["plotSec", column])
        if chart_data.empty:
            continue
        if step:
            ax.step(chart_data["plotSec"], chart_data[column], where="post", linewidth=1.8, label=column)
        else:
            ax.plot(chart_data["plotSec"], chart_data[column], marker="o", linewidth=1.6, label=column)
        has_data = True

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    if step:
        ax.set_ylim(-0.1, 1.1)
        ax.set_yticks([0, 1])
    if len(columns) > 1:
        ax.legend(loc="best")
    if not has_data:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center", va="center")
    return has_data


def plot_sensor_window(sensors: pd.DataFrame) -> bool:
    fig, axes = plt.subplots(7, 1, figsize=(11, 13), sharex=True)
    manager = getattr(fig.canvas, "manager", None)
    if manager:
        manager.set_window_title("Sensor Log")

    charts = [
        plot_series(axes[0], sensors, ["lightLevel"], "Light", "level"),
        plot_series(axes[1], sensors, ["temperature"], "Temperature", "temp"),
        plot_series(axes[2], sensors, ["soundLevel"], "Sound", "level"),
        plot_series(
            axes[3],
            sensors,
            ["accelerationX", "accelerationY", "accelerationZ"],
            "Acceleration X / Y / Z",
            "acceleration",
        ),
        plot_series(
            axes[4],
            sensors,
            ["tiltPitchDeg", "tiltRollDeg"],
            "Tilt Pitch / Roll",
            "degrees",
        ),
        plot_series(
            axes[5],
            sensors,
            ["buttonA", "buttonB", "logoTouch"],
            "Button / Logo Touch",
            "pressed",
            step=True,
        ),
        plot_series(axes[6], sensors, ["compassHeading"], "Compass", "heading"),
    ]
    axes[-1].set_xlabel("elapsed sec")
    fig.tight_layout()
    return any(charts)


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    sensors = load_sensor_events(input_path)

    print(f"sensor samples: {len(sensors)}")
    if sensors.empty:
        print("sensor data not found")
        return

    print_summary(sensors)
    print(sensors[SUMMARY_COLUMNS].describe().round(2).to_string())

    if plot_sensor_window(sensors):
        plt.show()
    else:
        print("sensor chart data not found")


if __name__ == "__main__":
    main()
