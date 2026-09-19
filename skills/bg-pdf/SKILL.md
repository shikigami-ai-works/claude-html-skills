---
name: bg-pdf
description: 装飾背景（金枠、便箋、レターヘッド、全面テクスチャ）を敷いた A4 の PDF を、HTML を正本にしてヘッドレス Chrome の印刷で作る手順。ユーザーが「金枠の PDF」「背景を指定した PDF」「この画像を背景にした PDF」「1枚ものの案内を PDF で」「賞状、案内状、メニュー表、提案書を PDF で」と言ったとき、または背景画像付きの紙もの（Web 表示と印刷の両対応を含む）を新しく作る、直すときに使う。背景素材の実測、画面と印刷の敷き分け、zoom の補正、枚数の検査を含む。挿絵入りで複数ページの冊子は a4-booklet を使う。
---

# 背景付き A4 PDF（HTML を正本にして Chrome で印刷）

装飾背景を敷いた A4 の紙面を HTML で書き、ヘッドレス Chrome で PDF にする。1枚ものが主な対象。
正本は HTML で、PDF は生成物である。直すのは常に HTML 側で、直したら PDF を出し直す。

要る物は Chrome か Chromium 系のブラウザ。背景素材の縮小と実測には Python の Pillow と NumPy を使う（`pip install pillow numpy`）。

## 手順

### 1. 背景素材を整える

- A4 で使うなら縦横比を 1:1.414 に合わせる。200dpi（1654x2338）あれば PDF で十分。
- 高解像度の原本しか無いときは、縮小して 256 色に減らす。PDF の大きさはほぼ素材の大きさで決まる（実測: 2400px の素材で 3.2MB、200dpi で 256 色にすると 1.9MB。見た目の差は無かった）。

```python
from PIL import Image
Image.open("原本.png").convert("RGB").resize((1654, 2338), Image.LANCZOS) \
     .quantize(colors=256).save("背景.png", optimize=True)
```

### 2. 素材を実測する

枠もの（四隅に装飾があり、辺は直線）は、装飾が紙の端から何 px まで張り出すかを測る。
この値が 9-slice（四隅を伸ばさず辺と中央だけ伸ばす敷き方）のスライス値と、本文の余白を決める。目測ではなく走査する。

```python
from PIL import Image
import numpy as np
img = np.array(Image.open("背景.png").convert("L"))
h, w = img.shape
ink = img < 200          # 装飾と線の画素
e = 80                   # 辺の直線が走る帯。ここを除かないと線が全域に引っかかる
inner = ink.copy()
inner[:, :e] = False; inner[:, w-e:] = False
inner[:e, :] = False; inner[h-e:, :] = False
# 各隅の窓を「角が原点」になるよう反転してから測る。反転しないと
# 右上、左下、右下は窓の中の生の座標が出て、張り出しに見えない大きな数字になる
for name, q, fy, fx in [("TL", inner[:800, :800], False, False),
                        ("TR", inner[:800, w-800:], False, True),
                        ("BL", inner[h-800:, :800], True, False),
                        ("BR", inner[h-800:, w-800:], True, True)]:
    if fy: q = q[::-1, :]
    if fx: q = q[:, ::-1]
    yy, xx = np.where(q)
    print(name, "角からの張り出し(x,y):", xx.max() if len(xx) else 0, yy.max() if len(yy) else 0)
```

スライス値は実測の最大値に 20px ほどの余裕を足す。
全面テクスチャ（切り分ける装飾が無い素材）なら実測は要らず、手順3の 9-slice も要らない。

### 3. HTML の正本を書く

骨格はこの形。画面と印刷で背景の敷き方を分けるのが要点である。

```css
@page{size:A4;margin:0;}
.page{ max-width:780px;margin:0 auto;background-color:紙色;
       position:relative;overflow:hidden;isolation:isolate; }

/* 画面: .page は本文の丈だけ縦に伸びるので、全面敷きだと装飾が間延びする。
   border-image の9分割で、四隅は素材の縮尺のまま、辺の直線と無地の中央だけ伸ばす。
   幅は「.page の実幅 × スライス値 / 素材幅」で、A4 で見たときと同じ縮尺になる */
@media screen{
  .page::before{
    content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
    border:min(15.72vw,123px) solid transparent;      /* 例: 260/1654=15.72% */
    border-image-source:url("背景.png");
    border-image-slice:260 fill;                       /* fill が無いと中央が透ける */
    border-image-width:min(15.72vw,123px);
    border-image-repeat:stretch;
  }
}

/* 印刷: .page を A4 ちょうどに固定するので比率が一致し、全面敷きで歪まない */
@media print{
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  .page{
    max-width:none;width:calc(210mm / .86);height:calc(297mm / .86);
    margin:0;box-shadow:none;zoom:.86;
    background-image:url("背景.png");
    background-size:100% 100%;background-repeat:no-repeat;
  }
}
```

- zoom の割り戻し: 本文が1枚に入りきらないときは zoom で縮めるが、zoom は描画の寸法ごと縮める。`width:210mm` のまま `zoom:.86` にすると紙の 86% の幅にしか出ず、右に白い帯が残る。`210mm / .86` と割り戻して、縮んだ結果が A4 ちょうどになるようにする。mm で指定した余白も同じように割り戻す。
- 本文の余白は、手順2で測った装飾の張り出しより内側に取る。
- 後から入れる値（差出人、日付、URL）は `{{名前}}` で置き、出力の前に残りの数を検査する。
- Google Fonts は使える（手順4の `--virtual-time-budget` が読み込みを待つ）。

### 4. PDF を出す

Windows の PowerShell:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu `
  --user-data-dir="$env:TEMP\chrome-pdf-profile" --virtual-time-budget=9000 `
  --no-pdf-header-footer --print-to-pdf="出力.pdf" "file:///C:/path/to/正本.html"
```

macOS と Linux のシェル（Chrome の場所は環境に合わせる）:

```bash
google-chrome --headless=new --disable-gpu \
  --user-data-dir="/tmp/chrome-pdf-profile" --virtual-time-budget=9000 \
  --no-pdf-header-footer --print-to-pdf="出力.pdf" "file:///path/to/正本.html"
```

`--user-data-dir` は必ず一時の場所に分ける。普段使いの Chrome が起動していると、省略したときにエラーも出さず何も出力しないことがある。出力ファイルの更新時刻が変わったかで確かめる。
古い `--headless`（`=new` なし）は `--print-to-pdf` で何も言わずに失敗することがあるので、`--headless=new` を使う。

### 5. 検査する

- PDF を開いて見た目を確かめる（枠の歪み、文字のはみ出し、置き換え忘れ）。
- 枚数を数える。想定と違えば zoom か余白を直して手順4へ戻る。

```python
import re
n = len(re.findall(rb"/Type\s*/Page[^s]", open("出力.pdf", "rb").read()))
print(n)
```

- `{{ }}` の残りの数が意図どおりかを数える（埋める前なら残っていて正しい。埋めた後は 0）。
