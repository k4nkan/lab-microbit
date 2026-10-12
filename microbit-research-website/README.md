# micro:bit 学習実験用 問題サイト

問題提示・進行管理・操作ログ収集を行うローカル実験用サイトです。MakeCodeロガーは別タブで動かし、終了後に管理画面からJSONを取り込みます。

## セットアップ

```bash
cd microbit-research-website
make setup
```

必要に応じて `frontend/.env.example` を `frontend/.env` にコピーし、APIとMakeCodeのURLを変更します。

## 起動

フロントエンドとバックエンドをまとめて起動します。

```bash
make dev
```

起動完了後、学習者画面 `http://localhost:5173` がブラウザで自動的に開きます。

個別に起動する場合は、ターミナルを2つ使います。

```bash
make backend
```

```bash
make frontend
```

- 学習者画面: http://localhost:5173
- 管理画面: http://localhost:5173/admin
- API仕様: http://localhost:8000/docs
- ログDB: `backend/data/research.db`
- 問題サイト自動保存: `backend/data/exports/problem-site/<session_id>.json`
- MakeCodeロガー自動保存: `backend/data/exports/makecode-logger/<connection_id>/<logger_session_id>.json`

フロントエンドだけでも「開始」ボタンから進行できます。操作ログはブラウザのLocalStorageへ保存され、各ページ下部の終了ボタンからJSONとして出力できます。

APIを含めて起動している場合、問題サイトとMakeCodeロガーのログは上記のJSONへ自動保存されます。問題サイト下部の「ここまでのログを保存」では、実験を終了せずにブラウザへ手動保存できます。

同一LANから使う場合は、`frontend/.env` の `VITE_API_URL` をバックエンドPCのIPに変更し、バックエンド起動時の `CORS_ORIGINS` にフロントのURLを追加してください。認証を持たない実験用構成のため、信頼できるLAN内だけで利用してください。

## 実験手順

1. 学習者画面で「開始」を押す。テスト用参加者IDは自動生成されます。
2. 問題サイト上部の接続IDを、Edit Loggerの接続ID欄へ入力して「接続確認」を押す。
3. 「問題サイトと接続済み」を確認して、Edit LoggerのStartを押す。
4. 問題サイトの順番に課題を進める。
5. 必要に応じて管理画面や自動保存JSONを確認する。

ブラウザから送れなかった問題サイトイベントはLocalStorageへ残り、再接続時に同じ `event_id` で再送されます。API側は主キーで重複を防ぎます。

## ログ上の制約

- ステップ完了は学習者の自己申告で、正解判定ではありません。
- ヒント・解答を開いた記録は、内容を理解したことを意味しません。
- MakeCodeロガーのコード変更は定期スナップショットで、個々のブロック操作ではありません。
- `boot` は手動リセットでも発生し、書き込み操作と常に一致するわけではありません。
- 統合ログは両ログの絶対時刻で整列します。PCの時計がずれている場合、その差は自動補正されません。実験前に各PCの時刻同期を確認してください。

## 確認

```bash
make check
```

