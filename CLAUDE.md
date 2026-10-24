# lab-microbit

micro:bit / MakeCode を使った学習実験の研究リポジトリ。実験環境（ロガー・問題サイト）の開発と、取得ログの分析をここで行う。

研究目的: コード編集ログと実機操作ログを組み合わせると、学習者の制作状況をどこまで把握できるかを検討する（RQ1: 段階的な課題 / RQ2: 自由制作）。

## 研究の概要（自動で読み込む）

@research/00-overview.md

## 必要に応じて読むもの

- 直近の進捗: `research/log/` の新しい日付から数件
- 設計判断の経緯: `research/decisions/`
- 起動・実験の流れ・分析手順: `docs/`（[setup](docs/setup.md) / [experiment](docs/experiment.md) / [analysis](docs/analysis.md)）

## 構成

| パス | 役割 |
| --- | --- |
| `microbit-edit-logger/` | MakeCode 拡張（submodule、公開用）。コード変更・センサー値・boot を記録 |
| `microbit-edit-logger-local/` | ローカル MakeCode の起動・検証用 |
| `microbit-research-website/` | 問題サイト（React/Vite）と API（FastAPI）。教材は `frontend/src/tasks.ts` |
| `tools/` | データセット作成（`build-dataset.py`）と分析（`mblog.py` がローダー、`explore.py` が探索用）。図は `tools/out/` |
| `docs/` | 利用者向けドキュメント。README は入口だけにして、詳細はここに書く |
| `research/` | 研究ノート（Obsidian vault）。進捗・ゼミ・判断・論文・発表構成 |

## よく使うコマンド

```bash
make setup        # 依存関係のインストール
make experiment   # MakeCode・ロガー・問題サイト・API をまとめて起動
make dataset      # 全実験のデータセットを作り直す
make analysis     # explore.py を実行して図を analysis/out/ に保存
make build        # 拡張のビルド確認
make stop         # port 競合時にローカル server を止める
```

## 規約

- ドキュメント・UI・研究ノートは日本語。
- コミットメッセージは Conventional Commits（`feat:` / `fix:` / `chore:` …）で英語。
- 実験データ（`microbit-research-website/backend/data/`）は gitignore 済み。参加者に関する情報をコミットしない。
- このリポジトリは **public**。`research/` は別の private リポジトリ（独立した git）で管理しているため、研究ノートの内容を README やコードコメントに転記しない。研究ノートのコミットは `research/` の中で行う。

## 研究ノートの扱い

- 作業で重要な判断をしたら `research/decisions/YYYY-MM-DD-<題名>.md` に `research/_templates/decision.md` の形式で残す。
- その日の進捗は `/log` で `research/log/YYYY-MM-DD.md` にまとめる。
- 教材（`tasks.ts`）やログ形式を変えたら、`TASK_VERSION` の更新と、どの実験から変わったかを決定記録に書く。
