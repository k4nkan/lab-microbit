# セットアップと起動

## 取得

submodule を含めて取得します。

```bash
git clone --recurse-submodules https://github.com/k4nkan/lab-microbit.git
cd lab-microbit
```

既に clone 済みで submodule が空の場合は、次を実行します。

```bash
git submodule update --init --recursive
```

## 依存関係

```bash
make setup            # ロガー・ローカル MakeCode・問題サイトの依存関係
make analysis-setup   # 分析用（tools/.venv に pandas / matplotlib / ipykernel）
```

## 起動

MakeCode、Edit Logger、問題サイト、API をまとめて起動します。

```bash
make experiment
```

MakeCode と問題サイトは、準備ができるとそれぞれブラウザで自動的に開きます。すべて停止する場合は `Ctrl+C` を押します。

ローカル MakeCode と editor UI だけを起動する場合は、次を実行します。

```bash
make dev
```

ブラウザで開いた MakeCode の「拡張機能」に次を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```

## その他

```bash
make build   # 拡張のビルド確認
make stop    # port 競合時にローカル server を止める
```

| サービス | URL |
| --- | --- |
| ローカル MakeCode | http://localhost:3232 |
| editor UI | http://localhost:8080/extension.html |
| 問題サイト（学習者画面） | http://localhost:5173 |
| 問題サイト（管理画面） | http://localhost:5173/admin |
| API 仕様 | http://localhost:8000/docs |

## うまく接続できないとき

| 症状 | 確認・対処 |
| --- | --- |
| 問題サイトが「API: 未接続」 | API（port 8000）が落ちている。`make experiment` のログに `bad interpreter` があれば、下のコマンドで仮想環境を作り直す |
| 起動時に port 使用中のエラー | `make stop` してから `make experiment` |
| 「MakeCode記録: 未接続」 | MakeCode で Edit Logger を開き直す |
| 書き込んでも `boot` やセンサーが記録されない | micro:bit が WebUSB で接続されていない。MakeCode の「ダウンロード」横の「…」から接続する |

```bash
# Python のバージョンを入れ替えたあとなど、API の仮想環境が壊れたとき
cd microbit-research-website/backend
rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
