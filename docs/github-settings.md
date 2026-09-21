# GitHub の画面で入れる設定

リポジトリを push した後に、GitHub の画面で手で入れる。ファイルからは反映されない。

## About 欄（リポジトリの右上の歯車）

Description:

```
Claude Code 用の Skill 集。設計の解説ページ、路線図、業務フローとER図の設計図、背景付きPDF、挿絵入りA4冊子を HTML で作り、ヘッドレス Chrome で描画を確かめてから渡す。
```

Topics:

```
claude-code claude-skills html mermaid pdf japanese
```

## 共有したときの画像

Settings → General → Social preview → Edit → Upload an image で `docs/images/social-preview.png`（1280×640）を選ぶ。

## 版の札

手元の記録に `v0.1.0` の札を付けてある。送るときは `git push origin v0.1.0`。GitHub の Releases で札から版を作ると、`CHANGELOG.md` の 0.1.0 の節をそのまま本文に使える。
