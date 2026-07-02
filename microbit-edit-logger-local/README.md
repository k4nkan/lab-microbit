# microbit-edit-logger-local

`microbit-edit-logger` をローカル MakeCode で動かすための最小起動環境です。

この repository は **MakeCode 本体をローカル起動するためだけ** に使います。拡張機能本体は含めません。

## 役割

```text
microbit-edit-logger
  GitHub に push する MakeCode extension 本体

microbit-edit-logger-local
  ローカル MakeCode を起動し、editor extension URL を許可する検証環境
```

## なぜ2つに分けるか

MakeCode の「拡張機能」画面は GitHub repository URL から package を読み込みます。
一方で editor extension の画面は iframe で外部URLを開くため、MakeCode 側の許可URLに入っていないと動きません。

そのため、MVPでは次の形にします。

```text
拡張機能本体: GitHub に push
MakeCode 実行環境: ローカルで起動
Editor UI: localhost:8080 で配信
```

公式の `https://makecode.microbit.org` では、開発用の `localhost:8080` editor extension は許可されません。

## Setup

```bash
cd /Users/kanta/dev/active/microbit-edit-logger-local
make setup
```

`microbit-edit-logger` 本体 repository は、この repository の隣にある前提で自動検出します。
別の場所にある場合は `EXT_DIR` を指定します。

```bash
EXT_DIR=/path/to/microbit-edit-logger make dev-open
```

## 起動手順

通常はこれだけで起動します。

```bash
cd /Users/kanta/dev/active/microbit-edit-logger-local
make dev-open
```

`make dev-open` は次をまとめて実行します。

- `microbit-edit-logger` の editor UI を `localhost:8080` で配信
- ローカル MakeCode を `localhost:3232` で起動
- `local_token` を検出して、`debugExtensions=1` 付きURLをブラウザで開く
- PXT標準の `/extension.html` を `microbit-edit-logger/editor/extension.html` に差し替える

ブラウザが自動で開かない場合やURLを手で確認したい場合は、次の手順で起動します。

ターミナル1で editor extension UI を配信します。

```bash
cd /Users/kanta/dev/active/microbit-edit-logger-local
make editor
```

ターミナル2でローカル MakeCode を起動します。

```bash
cd /Users/kanta/dev/active/microbit-edit-logger-local
make makecode
```

ブラウザで開きます。

```text
http://localhost:3232/index.html?debugExtensions=1#local_token=...&wsport=3233
```

`local_token` は、`npm run serve` したターミナルに表示されるURLからコピーします。

ターミナル表示例:

```text
http://localhost:3232/#local_token=...&wsport=3233
```

ブラウザで開くURL:

```text
http://localhost:3232/index.html?debugExtensions=1#local_token=...&wsport=3233
```

`#editor` だけになっている場合や、`local_token` が消えている場合は、ローカルAPIが `403 Forbidden` になり、拡張機能検索が失敗します。

MakeCode の「拡張機能」に、GitHub に push 済みの拡張機能 repository URL を貼ります。

```text
https://github.com/k4nkan/microbit-edit-logger
```

末尾に `.git` は付けません。

成功条件:

- `Edit Logger` カテゴリが出る
- editor extension パネルが開ける
- `microbit-edit-logger` 側のターミナルに `GET /extension.html HTTP/1.1 200` が出る
- パネル内の `Start` / `Stop` が押せる

`http://localhost:8080/extension.html` を直接開いた場合はUI確認だけです。コード読み取りは MakeCode 内の `Edit Logger` ボタンから開いた画面でしか動きません。

JSON / CSV export は MakeCode の iframe sandbox により自動ダウンロードがブロックされることがあります。その場合は、Export ボタン後に表示されるテキスト欄からコピーします。

`ask permission` / `query permissions` / `read code` / `write code` が出る場合は、PXT標準のテスト画面が残っています。次を実行して起動し直します。

```bash
make stop-ports
make dev-open
```

## よくある切り分け

`HEAD /extension.html` だけ出る場合は、まだパネルが開けていません。

`この拡張機能は許可されていません` と出る場合は、MakeCode を公式サイトで開いているか、このローカル環境の再起動前です。

`拡張機能がみつかりません` と出る場合は、次を確認します。

- URL末尾に `.git` を付けていない
- URLに `local_token` が残っている
- repository root に `pxt.json` がある
- GitHub に push 済みで、public に読める

`EADDRINUSE` が出る場合は、古い MakeCode server が残っています。

```bash
lsof -nP -iTCP:3232 -sTCP:LISTEN
lsof -nP -iTCP:3233 -sTCP:LISTEN
```

出てきた PID を止めてから `npm run serve` をやり直します。

## GitHub に入れないもの

- `node_modules/`
- `.pxt/`
- `built/`
- `hexcache/`
- `projects/`

この repository に `pxt_modules/` は不要です。
