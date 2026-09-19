# html-skills の進み具合

最終更新 2026-09-19

## 済んだこと（2026-09-19）

- `~/.claude/skills` の explain-visually、rosenzu、sekkeizu、bg-pdf、trpg-rulebook を写し、他人の環境で使える形に直した。trpg-rulebook は a4-booklet に改名し、TRPG 以外の冊子にも使える書き方にした。lp-run は営業の流れと結びついているので入れていない
- 元の Skill（`~/.claude/skills` の方）は触っていない
- しき専用の書き方（呼び名、京都弁、`D:\Obsidian` などの場所、社内の Skill 名）を抜いた。検索式は元の Skill で39件拾う陽性対照を取ったうえで、写しでは0件
- Chrome の場所を自動で探す処理を4本の script に入れた（`CHROME_PATH`、各 OS の既定の場所、PATH、Windows では Edge も）
- rosenzu と sekkeizu の見本データを、しきの案件の実データから架空の題材（出版社の制作、図書館の貸出）に差し替えた
- 試走: rosenzu（自己試験、書き出し、4枚撮影）、sekkeizu（自己試験、書き出し、数の突き合わせ、4枚撮影）、explain-visually（試験ページで Mermaid 2枚の描画、Chrome が無いときに止まること）、a4-booklet（タイル、撮影と分割、PDF 2ページ、ZIP）。すべて exit 0
- `claude plugin validate` は通過（author が無い警告1件）。`claude --plugin-dir` で5本が Skill として読み込まれることを確かめた

## 公開の前に決めること（しき）

- 置き場（GitHub の公開リポジトリなど）と公開そのもの
- author の表記（実名を出さない方針。ハンドル名か屋号か）
- explain-visually 以外の許諾（MIT などにするか）

## 残っている手当て

- a4-booklet の `render.ps1` は Windows 専用。macOS と Linux でも撮影と分割をしたいなら、Python へ移す
- macOS と Linux での試走はしていない（Chrome を探す処理は書いたが、実機では未確認）
- bg-pdf は script を持たず、手順と断片のコードだけ。雛形の HTML は入れていない
