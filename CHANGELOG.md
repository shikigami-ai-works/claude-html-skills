# 更新の記録

## 0.1.0（2026-09-21）

最初の公開版。

- Skill 5本: explain-visually、rosenzu、sekkeizu、bg-pdf、a4-booklet
- Claude Code のプラグインとマーケットプレイスの定義（`.claude-plugin/`）
- Chrome の場所を自動で探す処理（環境変数 `CHROME_PATH`、各 OS の既定の場所、PATH。Windows では Edge も）
- a4-booklet の撮影と PDF 化を Python の `render.py` にまとめた（OS を問わない）
- README に各 Skill の見本の画像を載せた

動作を確かめた環境は Windows 11 だけである。
