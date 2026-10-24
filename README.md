# lab-microbit

micro:bit / MakeCode を用いたプログラミング学習で、制作ログ（コード編集・実機操作・課題進行）を収集・分析するための研究用 workspace です。

## 構成

| パス | 内容 |
| --- | --- |
| [`microbit-edit-logger/`](https://github.com/k4nkan/microbit-edit-logger) | MakeCode 拡張（submodule）。コード変更・起動・センサー値を記録 |
| `microbit-edit-logger-local/` | ローカル MakeCode の起動・検証用 |
| [`microbit-research-website/`](microbit-research-website/README.md) | 問題サイトと API。課題進行ログとロガーのログを集約 |
| `tools/` | データセット作成と分析（Python） |
| `docs/` | ドキュメント |

## クイックスタート

```bash
git clone --recurse-submodules https://github.com/k4nkan/lab-microbit.git
cd lab-microbit
make setup
make experiment   # MakeCode・ロガー・問題サイト・API をまとめて起動
```

## ドキュメント

- [セットアップと起動](docs/setup.md)
- [実験の進め方とデータの流れ](docs/experiment.md)
- [実験データの分析](docs/analysis.md)
