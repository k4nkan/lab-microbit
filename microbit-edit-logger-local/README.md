# microbit-edit-logger-local

## 概要

`microbit-edit-logger` をローカル MakeCode で検証するための開発用ツールです。
ローカル MakeCode を起動し、`localhost:8080` の editor UI を許可します。

この directory は公開用 extension 本体ではありません。

## セットアップ

通常は親 workspace から実行します。

```bash
cd /Users/kanta/dev/active/lab-microbit
make setup
```

ローカル MakeCode と editor UI を起動します。

```bash
make dev-open
```

ブラウザで開いた MakeCode の「拡張機能」に次を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```

手動で起動する場合は、親 workspace から次を使います。

```bash
make editor
make makecode
```

`EADDRINUSE` が出た場合は、古い server を止めます。

```bash
make stop-ports
```
