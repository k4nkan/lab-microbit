---
name: log
description: その日の作業を research/log/YYYY-MM-DD.md に進捗ログとしてまとめる。「/log」「今日の進捗まとめて」で使う。
---

# 進捗ログを書く

1. 今日の日付を `date +%F` で確認する。
2. 材料を集める:
   - `git log --since=midnight --stat` と `git status` / `git diff --stat`（未コミットの変更も含める）
   - submodule（`microbit-edit-logger`）にも同様に変更があれば見る
   - この会話でやったこと・決めたこと・詰まったこと
   - 前回のログ（`research/log/` の最新）の「次にやること」
3. `research/log/YYYY-MM-DD.md` を `research/_templates/daily.md` の見出しで書く。既にあれば消さずに追記・統合する。
   - 「やったこと」は研究上の意味がわかる粒度で書く（ファイル名の羅列にしない）。
   - 前回の「次にやること」のうち終わったものは `[x]` にして今日のログに残す。
4. 設計判断が含まれていれば、`research/decisions/` に別ファイルとして残すか提案する。
5. 参加者 ID 以外の参加者情報（氏名・所属など）は書かない。
6. 書いた内容を 3 行程度で報告する。
