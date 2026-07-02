# microbit-edit-logger-local

## 概要

`microbit-edit-logger` をローカル MakeCode で検証するための開発用ツールです。
ローカル MakeCode を起動し、`localhost:8080` の editor UI を許可します。

この directory は公開用 extension 本体ではありません。

## セットアップ

親 workspace から依存関係を入れます。

```bash
cd /Users/kanta/dev/active/lab-microbit
make setup
```

ローカル MakeCode と editor UI を起動します。

```bash
make dev
```

ブラウザで開いた MakeCode の「拡張機能」に次を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```

`EADDRINUSE` が出た場合は、古い server を止めます。

```bash
make stop
```
