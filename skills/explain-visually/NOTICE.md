# 出典と直した所

- 原本: https://github.com/keitakn/engineering-skills の `.claude/skills/explain-visually`
- 取得した commit: b785a355ff83a10515a246026a0595a30ef41827（2026-09-10）
- 許諾: MIT License（同じフォルダの `LICENSE`）。著作権表示は原本のまま残している
- 原本の紹介記事: https://zenn.dev/avaintelligence/articles/dont-outsource-understanding-to-ai

## scripts/verify_page.py の直し

1. Chrome の場所を、環境変数 `CHROME_PATH`、Windows と macOS の既定の場所、PATH の順で探す形にした（Windows では Edge も候補に入る）
2. 打ち切り時の止め方を、Windows では `taskkill /F /T`、それ以外では原本どおり `killpg` にした
3. 標準出力を UTF-8 に固定し、`--dump-dom` の出力も UTF-8 で読むようにした
4. `--shot-dir` を足した（スクリーンショットを HTML と別の場所へ置ける）

## assets/template.html

原本のまま。

## SKILL.md の直し

- 本文を日本語で書き直した
- 出力先を `/tmp/explain-visually/` から、作業中のプロジェクトの `docs/explain/` にした
- 開く手段を `open` から `python -m webbrowser` にした（OS を問わない）
- PR と Issue は、先にファイルへ保存してから対象にする形にした
- Figma の扱い（読むのは MCP 接続から、書くのは許可を取ってから）を足した
- 末尾の理解確認（3問）を出口として足した
