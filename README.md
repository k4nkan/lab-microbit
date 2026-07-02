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
make dev-open
```

ブラウザで開いた MakeCode の「拡張機能」に次を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```
