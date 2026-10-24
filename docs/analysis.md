# 実験データの分析

分析用のスクリプトはすべて `tools/` にあります。

| ファイル | 役割 |
| --- | --- |
| `build-dataset.py` | 研究DB → 実験ごとのデータセット（標準ライブラリのみ） |
| `mblog.py` | データセットを pandas で読み込み、指標の計算と図の描画を行う |
| `explore.py` | 探索用スクリプト。`# %%` セルごとに実行でき、図を `tools/out/` に保存 |
| `block-analytics.py` / `sensor-analytics.py` | Edit Logger の Export CSV を直接読む簡易集計（`tools/logs/`） |

## 1. データセットを作る

```bash
make dataset                              # すべての実験を作り直す
python3 tools/build-dataset.py P01        # 参加者ID・フォルダ名・セッションIDで指定（省略すると最新の終了済み実験）
python3 tools/build-dataset.py --all      # すべての実験
```

出力先は `microbit-research-website/backend/data/datasets/<開始日時>_<参加者ID>/` です。`timeline.csv`（全イベントの時刻順一覧）、`steps.csv`（ステップごとの集計）、`runs.csv`（書き込みごとの集計）、`sensors.csv`、`code/`（コードの各版）などが入ります。各列の意味は、フォルダ内の `README.md` にあります。

## 2. 分析する

```bash
make analysis-setup   # 初回のみ：tools/.venv に pandas / matplotlib / ipykernel を入れる
make analysis         # explore.py を実行し、図を tools/out/ に保存
```

VS Code では `tools/explore.py` の `# %%` ごとにセルとして実行できます（インタプリタに `tools/.venv` を選ぶ）。

```python
import mblog
mblog.list_datasets()            # 実験の一覧
ds = mblog.load("P-5165")        # 参加者ID・フォルダ名・セッションID。省略すると最新
ds.steps                         # ステップごとの集計（滞在時間・コード保存・書き込み・ヒントなど）
ds.snapshots                     # コード保存ごとの BLN / スクリプト数 / LOB / CCN / 未接続ブロック
ds.minutes                       # 1分ごとの指標
ds.runs, ds.sensors              # 書き込み（実行）ごと / センサー値
ds.problem, ds.timeline          # 問題サイトの操作 / 全イベントの時刻順一覧
ds.step_bands                    # 各ステップを表示していた時間帯（分）
ds.code(120)                     # 120番目に保存されたコード（main.ts）

mblog.edit_run_cycles(ds)        # 書き込みごとの「直前の保存回数・試した時間・本体の動かし方」
mblog.struggle_minutes(ds)       # 追加・削除は多いのに実行ブロックが増えず、書き込みもない分
mblog.plot_blocks(ds)            # BLN・実行・未接続ブロックの推移（ステップ帯・書き込み・ヒント付き）
mblog.plot_step_time(ds); mblog.plot_sensors(ds)
```

時刻はPCのローカル時刻、`t_sec` / `t_min` は実験開始からの経過時間です。

## コード指標

槇原ら（2022）の Scratch 向け指標を MakeCode に合わせたもの（定義は `build-dataset.py` の `code_metrics`）。

| 指標 | 定義 |
| --- | --- |
| BLN | 置かれているブロックの総数（シャドウ除く、未接続も含む） |
| scripts | 実行されるスクリプト（最初だけ・ずっと・各イベント）の数。SPN の代わり |
| LOB | スクリプトあたりの実行ブロック数の平均 |
| CCN | スクリプトごとの 1 + 条件分岐 + 繰り返し（平均 / 最大） |
