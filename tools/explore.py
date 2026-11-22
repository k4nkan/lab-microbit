# %% [markdown]
# # 実験データの探索
# VS Code では `# %%` ごとにセルとして実行できます（Python拡張 + ipykernel）。
# スクリプトとして `python tools/explore.py` で実行すると、図を `tools/out/<データセット>/` に保存します。

# %%
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import mblog

pd.set_option("display.width", 160)

print(mblog.list_datasets())
ds = mblog.load()  # 参加者IDを渡すと指定できる: mblog.load("P-5165")
print(ds.name, ds.summary["duration_min"], "分")

OUT = Path(__file__).resolve().parent / "out" / ds.name  # 図はデータセットごとのフォルダに保存
(OUT / "sensing").mkdir(parents=True, exist_ok=True)

# %% ステップごとの集計
print(
    ds.steps[
        [
            "step_id",
            "label",
            "time_on_step_min",
            "code_changes",
            "blocks_added",
            "blocks_removed",
            "boots",
            "hints_opened",
            "answers_opened",
            "result",
        ]
    ]
    .round(1)
    .to_string(index=False)
)

# %% コード指標の推移（槇原ら 2022 の BLN / LOB / CCN）
fig, ax = plt.subplots(figsize=(12, 4))
mblog.plot_blocks(ds, ax)
fig.tight_layout()
fig.savefig(OUT / "blocks.png", dpi=150)

fig, axes = plt.subplots(3, 1, figsize=(12, 6), sharex=True)
for ax, (col, label) in zip(axes, [("scripts", "スクリプト数"), ("lob_avg", "LOB"), ("ccn_avg", "CCN")]):
    ax.step(ds.snapshots["t_min"], ds.snapshots[col], where="post", color="0.1")
    ax.set_ylabel(label)
    ax.spines[["top", "right"]].set_visible(False)
axes[-1].set_xlabel("経過時間（分）")
fig.tight_layout()
fig.savefig(OUT / "metrics.png", dpi=150)

# %% 編集と実行のサイクル
cycles = mblog.edit_run_cycles(ds)
print(cycles.round(1).to_string(index=False))
print(cycles.groupby("step_id", sort=False)[["edits_before", "tried_for_sec", "moving_samples"]].median())

# %% 試行錯誤が続いて前に進んでいない区間（ヒューリスティック）
struggle = mblog.struggle_minutes(ds)
print(struggle[struggle["struggle"]].to_string(index=False))

# %% ステップ滞在時間と実機の操作
fig, ax = plt.subplots(figsize=(8, 4.5))
mblog.plot_step_time(ds, ax)
fig.tight_layout()
fig.savefig(OUT / "steps.png", dpi=150)

fig, ax = plt.subplots(figsize=(12, 3.5))
mblog.plot_sensors(ds, ax)
fig.tight_layout()
fig.savefig(OUT / "sensors.png", dpi=150)

# %% センシング: コードの閾値と実際のセンサー値
# 実行（書き込み）ごとに、そのとき動いていたコードの閾値に、実際の値が届いたかを見る
sensing = mblog.sensing_summary(ds)
if not sensing.empty:
    print(sensing.round(2).to_string(index=False))
    detail = mblog.sensing_runs(ds)
    cols = ["run_index", "step_id", "condition", "closest", "gap", "reached_ratio", "switches", "label", "changed"]
    print(detail[cols].round(2).to_string(index=False))

fig = mblog.plot_sensing(ds)
fig.savefig(OUT / "sensing" / "all.png", dpi=150)
fig = mblog.plot_run_labels(ds)
fig.savefig(OUT / "sensing" / "labels.png", dpi=150)
plt.close(fig)
fig = mblog.plot_focus_sequence(ds)
fig.savefig(OUT / "sensing" / "focus-sequence.png", dpi=150)
plt.close(fig)
for name, steps in {"tutorial": ["T8"], "game": ["G2", "G3"], "arrange": ["arrange"]}.items():
    fig = mblog.plot_sensing(ds, steps=steps)
    fig.savefig(OUT / "sensing" / f"{name}.png", dpi=150)
    plt.close(fig)

# %% 任意の時点のコードを見る
print(ds.code(int(ds.snapshots["snapshot_index"].iloc[-1])))

# %%
if __name__ == "__main__":
    print(f"図を保存しました: {OUT}")
