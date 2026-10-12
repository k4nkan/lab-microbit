# lab-microbit

## 概要

micro:bit / MakeCode editor extension の研究・開発用 workspace です。

- `microbit-edit-logger/`: 公開用 MakeCode extension 本体。submodule として管理します。
- `microbit-edit-logger-local/`: ローカル MakeCode 起動・検証用ツールです。

## セットアップ

submodule を含めて取得します。

```bash
git clone --recurse-submodules https://github.com/k4nkan/lab-microbit.git
cd lab-microbit
```

既に clone 済みで submodule が空の場合は、次を実行します。

```bash
git submodule update --init --recursive
```

依存関係を入れます。

```bash
make setup
```

ローカル MakeCode と editor UI を起動します。

```bash
make dev
```

MakeCode、Edit Logger、問題サイト、APIをまとめて起動する場合は、次を実行します。

```bash
make experiment
```

MakeCodeと問題サイトは、準備ができるとそれぞれブラウザで自動的に開きます。すべて停止する場合は `Ctrl+C` を押します。

### 実験データの流れ

IDのコピーや接続操作は不要です。1台のPCで同時に行う実験は1つ、という前提で動きます。

1. 問題サイトで参加者IDを入力して「開始」を押す（空欄なら `P-XXXX` が自動で付きます）。APIがこれを「現在の実験」として保持します。
2. MakeCodeで Edit Logger を一度開く。ロガーは5秒ごとに現在の実験を確認し、記録を自動で開始します（表示：`実験 P01 に記録中`）。
3. 問題サイトで実験を終了すると、ロガーも自動で停止します。次の参加者で「開始」すると、ロガーは新しい実験として記録し直します。

ロガーのイベントは、時刻で実験に紐付けられます（終了後60秒までは同じ実験に含めます）。APIが止まっていてもロガー内に未送信分として残り、復旧後に自動で再送されます。

保存先（`microbit-research-website/backend/data/exports/`）:

```text
sessions/<開始日時>_<参加者ID>/
├── problem-events.jsonl   # 問題サイトの操作（リアルタイム追記）
├── makecode-events.jsonl  # MakeCodeのコード変更・起動・センサー（リアルタイム追記）
├── session.json           # 実験の概要（終了時・手動保存時に更新）
├── problem-events.json    # ↓ 終了時・「ここまでのログを保存」で作る整形済みJSON
├── makecode-events.json
└── merged.json            # 両方を時刻順に統合
unassigned/makecode-<logger_session_id>.jsonl  # 実験の外で記録されたロガーイベント
```

ブラウザで開いた MakeCode の「拡張機能」に次を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```

ビルド確認だけ行う場合は、次を実行します。

```bash
make build
```

port 競合時は、次でローカル server を止めます。

```bash
make stop
```
